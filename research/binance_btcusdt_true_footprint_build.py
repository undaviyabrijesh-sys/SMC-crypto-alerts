#!/usr/bin/env python3
"""Build exact-price BTCUSDT 5m footprint, daily volume profile and 30m TPO from Binance aggTrades."""
# Frozen one-month data feature pilot; no strategy PnL is computed in this module.
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

BASE = "https://data.binance.vision/data/futures/um"
SYMBOL = "BTCUSDT"
START = pd.Timestamp("2026-09-01T00:00:00Z")
END = pd.Timestamp("2026-10-01T00:00:00Z")
BAR_MS = 300_000
PERIOD_30M_MS = 1_800_000
DAY_MS = 86_400_000
EXPECTED_5M_BARS = 8_640
AGG_HEADER = ["agg_trade_id", "price", "quantity", "first_trade_id",
              "last_trade_id", "transact_time", "is_buyer_maker"]
AGG_COLS = ["agg_trade_id", "price", "quantity", "first_trade_id",
            "last_trade_id", "timestamp_ms", "buyer_maker"]
KLINE_HEADER_VARIANTS = [
    ["open_time", "open", "high", "low", "close", "volume", "close_time",
     "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"],
    ["open_time", "open", "high", "low", "close", "volume", "close_time",
     "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume",
     "taker_buy_quote_asset_volume", "ignore"],
]
KLINE_COLS = ["open_time_ms", "open", "high", "low", "close", "volume",
              "close_time_ms", "quote_volume", "trade_count",
              "taker_buy_base", "taker_buy_quote", "ignore"]


def detect_header(fh: Any, variants: list[list[str]]) -> bool:
    first = fh.readline().decode("utf-8-sig").strip().split(",")
    normalized = [x.strip().lower() for x in first]
    if normalized in variants:
        return True
    fh.seek(0)
    return False


def parse_checksum(text: str) -> str:
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not m:
        raise ValueError("Unable to parse SHA-256 from CHECKSUM")
    return m.group(1).lower()


def download_file(session: requests.Session, url: str, path: Path, retries: int = 6) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(retries):
        try:
            h = hashlib.sha256()
            total = 0
            with session.get(url, stream=True, timeout=(20, 180)) as response:
                response.raise_for_status()
                with path.open("wb") as out:
                    for block in response.iter_content(1024 * 1024):
                        if block:
                            out.write(block)
                            h.update(block)
                            total += len(block)
            return {"url": url, "path": str(path), "bytes": total, "sha256": h.hexdigest(),
                    "last_modified": response.headers.get("Last-Modified")}
        except Exception as exc:
            last_error = repr(exc)
            path.unlink(missing_ok=True)
            if attempt + 1 < retries:
                time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"Download failed: {url}; {last_error}")


def download_checked(session: requests.Session, url: str, folder: Path) -> tuple[Path, dict[str, Any]]:
    p = folder / Path(url).name
    checksum_p = folder / (Path(url).name + ".CHECKSUM")
    dm = download_file(session, url, p)
    cm = download_file(session, url + ".CHECKSUM", checksum_p)
    checksum_text = checksum_p.read_text(encoding="utf-8", errors="replace").strip()
    expected = parse_checksum(checksum_text)
    if dm["sha256"] != expected:
        raise ValueError(f"SHA-256 mismatch for {p.name}: expected {expected}, got {dm['sha256']}")
    dm.update({"checksum_url": url + ".CHECKSUM", "checksum_path": str(checksum_p),
               "checksum_text": checksum_text, "expected_sha256": expected,
               "checksum_verified": True, "checksum_download": cm})
    return p, dm


def csv_member(path: Path) -> tuple[str, dict[str, Any]]:
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failure: {bad}")
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"Expected one CSV member, found {members}")
        info = zf.getinfo(members[0])
        return members[0], {"zip_crc_pass": True, "csv_member": members[0],
                            "uncompressed_csv_bytes": info.file_size}


def value_area(profile: pd.DataFrame, weight_col: str, fraction: float = 0.70) -> dict[str, float]:
    d = profile.sort_values("price").reset_index(drop=True)
    w = d[weight_col].to_numpy(float)
    if len(w) == 0 or not np.isfinite(w).all() or float(w.sum()) <= 0:
        raise ValueError(f"Invalid profile weights for {weight_col}")
    total = float(w.sum())
    poc = int(np.argmax(w))
    left = right = poc
    cumulative = float(w[poc])
    target = total * fraction
    while cumulative < target and (left > 0 or right < len(w) - 1):
        lv = float(w[left - 1]) if left > 0 else -1.0
        rv = float(w[right + 1]) if right < len(w) - 1 else -1.0
        if lv >= rv:  # deterministic tie-break: lower price first
            left -= 1
            cumulative += lv
        else:
            right += 1
            cumulative += rv
    return {"poc": float(d.price.iloc[poc]), "val": float(d.price.iloc[left]),
            "vah": float(d.price.iloc[right]), "covered_share": cumulative / total,
            "poc_share": float(w[poc] / total), "total_weight": total}


def self_test() -> None:
    assert detect_header(__import__("io").BytesIO((",".join(AGG_HEADER) + "\n").encode()), [AGG_HEADER])
    assert detect_header(__import__("io").BytesIO((",".join(KLINE_HEADER_VARIANTS[0]) + "\n").encode()), KLINE_HEADER_VARIANTS)
    x = np.array([0, 299999, 300000, 1800000], dtype=np.int64)
    assert ((x // BAR_MS) * BAR_MS).tolist() == [0, 0, 300000, 1800000]
    p = pd.DataFrame({"price": [100.0, 100.1, 100.2], "volume": [70.0, 20.0, 10.0]})
    va = value_area(p, "volume")
    assert va["poc"] == 100.0 and va["covered_share"] >= 0.70
    # TPO counts distinct 30m periods, not 5m bars.
    toy = pd.DataFrame({"day": [0, 0, 0], "price": [100.0, 100.0, 100.0],
                        "period": [0, 0, 1800000]})
    assert len(toy.drop_duplicates(["day", "price", "period"])) == 2
    print("5 deterministic footprint/TPO/value-area tests passed")


def read_klines(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    member, zmeta = csv_member(path)
    with zipfile.ZipFile(path) as zf, zf.open(member) as fh:
        header = detect_header(fh, KLINE_HEADER_VARIANTS)
        d = pd.read_csv(fh, header=None, names=KLINE_COLS, dtype=str)
    zmeta["csv_header_present"] = header
    for c in ["open_time_ms", "close_time_ms", "trade_count"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ["open", "high", "low", "close", "volume", "taker_buy_base"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if d[["open_time_ms", "close_time_ms", "trade_count"]].isna().any().any():
        raise ValueError("Kline archive has invalid integer fields")
    if d[["open", "high", "low", "close", "volume", "taker_buy_base"]].isna().any().any():
        raise ValueError("Kline archive has invalid OHLCV fields")
    d["open_time_ms"] = d.open_time_ms.astype(np.int64)
    if d.open_time_ms.duplicated().any():
        raise ValueError("Duplicate kline timestamps")
    d = d.sort_values("open_time_ms").reset_index(drop=True)
    start_ms, end_ms = int(START.timestamp() * 1000), int(END.timestamp() * 1000)
    expected = np.arange(start_ms, end_ms, BAR_MS, dtype=np.int64)
    if not np.array_equal(d.open_time_ms.to_numpy(np.int64), expected):
        raise ValueError("Kline archive does not contain exactly 8,640 ordered September bars")
    shape = (d.high >= d[["open", "close", "low"]].max(axis=1)) & (d.low <= d[["open", "close", "high"]].min(axis=1))
    valid = ((d[["open", "high", "low", "close"]] > 0).all(axis=1)
             & (d.volume >= 0) & (d.taker_buy_base >= 0)
             & (d.taker_buy_base <= d.volume + 1e-9) & shape)
    if not valid.all():
        raise ValueError("Invalid kline OHLCV rows")
    return d, {"rows": len(d), "zip_crc_pass": True, "csv_header_present": header,
               "csv_member": member, "total_base_volume": float(d.volume.sum()),
               "total_taker_buy_base": float(d.taker_buy_base.sum()),
               "zero_volume_bars": int((d.volume == 0).sum())}


def build_levels(agg_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    member, zmeta = csv_member(agg_path)
    stats = {"rows": 0, "first_id": None, "last_id": None, "first_ts": None, "last_ts": None,
             "id_gaps": 0, "duplicate_ids": 0, "id_order_violations": 0,
             "timestamp_regressions": 0, "out_of_month": 0,
             "total_qty": 0.0, "buy_qty": 0.0, "sell_qty": 0.0}
    start_ms, end_ms = int(START.timestamp() * 1000), int(END.timestamp() * 1000)
    dtypes = {"agg_trade_id": "int64", "price": "float64", "quantity": "float64",
              "first_trade_id": "int64", "last_trade_id": "int64",
              "timestamp_ms": "int64", "buyer_maker": "bool"}
    partials: list[pd.DataFrame] = []
    prev_id = prev_ts = None
    with zipfile.ZipFile(agg_path) as zf, zf.open(member) as fh:
        header = detect_header(fh, [AGG_HEADER])
        reader = pd.read_csv(fh, header=None, names=AGG_COLS, dtype=dtypes,
                             chunksize=1_000_000, low_memory=False)
        for chunk in reader:
            ids = chunk.agg_trade_id.to_numpy(np.int64)
            ts = chunk.timestamp_ms.to_numpy(np.int64)
            price = chunk.price.to_numpy(float)
            qty = chunk.quantity.to_numpy(float)
            first_id = chunk.first_trade_id.to_numpy(np.int64)
            last_id = chunk.last_trade_id.to_numpy(np.int64)
            maker = chunk.buyer_maker.to_numpy(bool)
            if not np.isfinite(price).all() or not np.isfinite(qty).all() or np.any(price <= 0) or np.any(qty <= 0) or np.any(first_id > last_id):
                raise ValueError("Invalid aggTrade numeric/price/quantity/underlying-ID row")
            if np.any((ts < start_ms) | (ts >= end_ms)):
                stats["out_of_month"] += int(np.sum((ts < start_ms) | (ts >= end_ms)))
                raise ValueError("Out-of-month aggTrade timestamp")
            if len(ids) > 1:
                dif = np.diff(ids)
                stats["duplicate_ids"] += int(np.sum(dif == 0))
                stats["id_order_violations"] += int(np.sum(dif <= 0))
                stats["id_gaps"] += int(np.maximum(dif - 1, 0).sum())
                stats["timestamp_regressions"] += int(np.sum(np.diff(ts) < 0))
                if np.any(dif <= 0) or np.any(np.diff(ts) < 0):
                    raise ValueError("AggTrade ID/timestamp ordering failure")
            if prev_id is not None:
                if ids[0] <= prev_id:
                    stats["duplicate_ids"] += int(ids[0] == prev_id)
                    stats["id_order_violations"] += 1
                    raise ValueError("AggTrade IDs not increasing across chunks")
                stats["id_gaps"] += max(int(ids[0]) - prev_id - 1, 0)
                if ts[0] < prev_ts:
                    stats["timestamp_regressions"] += 1
                    raise ValueError("AggTrade timestamp regressed across chunks")
            if stats["first_id"] is None:
                stats["first_id"], stats["first_ts"] = int(ids[0]), int(ts[0])
            stats["last_id"], stats["last_ts"] = int(ids[-1]), int(ts[-1])
            buy_mask = ~maker
            bar = ((ts // BAR_MS) * BAR_MS).astype(np.int64)
            tmp = pd.DataFrame({
                "bar_open_ms": bar, "price": price, "qty": qty,
                "buy_qty": np.where(buy_mask, qty, 0.0),
                "sell_qty": np.where(maker, qty, 0.0),
                "aggtrade_count": np.ones(len(chunk), dtype=np.int64),
            })
            g = tmp.groupby(["bar_open_ms", "price"], sort=False, observed=True).agg(
                total_qty=("qty", "sum"), taker_buy_qty=("buy_qty", "sum"),
                taker_sell_qty=("sell_qty", "sum"), aggtrade_count=("aggtrade_count", "sum")
            ).reset_index()
            partials.append(g)
            stats["rows"] += len(chunk)
            stats["total_qty"] += float(qty.sum())
            stats["buy_qty"] += float(qty[buy_mask].sum())
            stats["sell_qty"] += float(qty[maker].sum())
            prev_id, prev_ts = int(ids[-1]), int(ts[-1])
    if not partials:
        raise ValueError("No aggTrade rows")
    partial = pd.concat(partials, ignore_index=True)
    levels = partial.groupby(["bar_open_ms", "price"], as_index=False, sort=True).agg(
        total_qty=("total_qty", "sum"), taker_buy_qty=("taker_buy_qty", "sum"),
        taker_sell_qty=("taker_sell_qty", "sum"), aggtrade_count=("aggtrade_count", "sum"))
    levels["delta_qty"] = levels.taker_buy_qty - levels.taker_sell_qty
    levels["day_open_ms"] = (levels.bar_open_ms // DAY_MS) * DAY_MS
    levels["period30m_open_ms"] = (levels.bar_open_ms // PERIOD_30M_MS) * PERIOD_30M_MS
    stats.update(zmeta)
    stats["csv_header_present"] = header
    stats["signed_delta_qty"] = stats["buy_qty"] - stats["sell_qty"]
    return levels, stats


def build_daily_profiles(levels: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = levels.groupby(["day_open_ms", "price"], as_index=False, sort=True).agg(
        volume=("total_qty", "sum"), taker_buy=("taker_buy_qty", "sum"),
        taker_sell=("taker_sell_qty", "sum"), delta=("delta_qty", "sum"))
    tpo = levels[["day_open_ms", "price", "period30m_open_ms"]].drop_duplicates()
    tpo = tpo.groupby(["day_open_ms", "price"], as_index=False, sort=True).size()
    tpo = tpo.rename(columns={"size": "tpo_30m_count"})
    daily = daily.merge(tpo, on=["day_open_ms", "price"], how="left", validate="one_to_one")
    daily["tpo_30m_count"] = daily.tpo_30m_count.astype(np.int64)
    summaries = []
    for day, group in daily.groupby("day_open_ms", sort=True):
        vp = value_area(group, "volume", 0.70)
        tp = value_area(group, "tpo_30m_count", 0.70)
        summaries.append({
            "day_open_ms": int(day),
            "day_utc": pd.to_datetime(day, unit="ms", utc=True).strftime("%Y-%m-%d"),
            "total_volume": float(group.volume.sum()),
            "taker_buy": float(group.taker_buy.sum()),
            "taker_sell": float(group.taker_sell.sum()),
            "net_delta": float(group.delta.sum()),
            "net_delta_ratio": float(group.delta.sum() / group.volume.sum()),
            "volume_poc": vp["poc"], "volume_val": vp["val"], "volume_vah": vp["vah"],
            "volume_value_area_share": vp["covered_share"], "volume_poc_share": vp["poc_share"],
            "tpo_poc": tp["poc"], "tpo_val": tp["val"], "tpo_vah": tp["vah"],
            "tpo_value_area_share": tp["covered_share"], "tpo_poc_share": tp["poc_share"],
            "tpo_period_price_counts": int(group.tpo_30m_count.sum()),
            "max_tpo_30m_count_at_price": int(group.tpo_30m_count.max()),
            "price_levels": int(len(group)),
        })
    return daily, pd.DataFrame(summaries)


def write_report(out: Path, meta: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True, default=str))
    lines = [
        "# BTCUSDT September 2026 true footprint / VP / TPO feature build",
        "",
        f"- Status: **{meta.get('status')}**",
        f"- Retrieved: {meta.get('retrieved_at_utc')}",
        f"- AggTrade rows: {meta.get('aggtrade_rows')}",
        f"- 5m price-level rows: {meta.get('price_level_rows')}",
        f"- Daily profile days: {meta.get('daily_profile_days')}",
        f"- Integrity / reconciliation / profile validation: {meta.get('integrity_pass')} / {meta.get('reconciliation_pass')} / {meta.get('profile_validation_pass')}",
        "",
        "## Trade-level data",
    ]
    for k in ["aggtrade_total_base_quantity", "taker_buy_base_quantity", "taker_sell_base_quantity",
              "signed_delta_base_quantity", "first_agg_id", "last_agg_id",
              "aggregate_id_gaps", "duplicate_ids", "id_order_violations", "timestamp_regressions"]:
        lines.append(f"- {k}: {meta.get(k)}")
    lines += ["", "## 5m reconciliation"]
    for k, v in meta.get("reconciliation", {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Exact-price footprint outputs"]
    for k, v in meta.get("feature_summary", {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "No strategy signal, entry, stop, target, fee, funding or PnL was tested."]
    (out / "report.md").write_text("\n".join(lines) + "\n")


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    src = out / "source"
    src.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "SaltyQuant-TrueFootprintBuild/1.0",
                            "Accept": "application/zip,application/octet-stream,*/*"})
    agg_url = f"{BASE}/monthly/aggTrades/{SYMBOL}/{SYMBOL}-aggTrades-2026-09.zip"
    kline_url = f"{BASE}/monthly/klines/{SYMBOL}/5m/{SYMBOL}-5m-2026-09.zip"
    meta: dict[str, Any] = {
        "status": "running", "symbol": SYMBOL, "market": "Binance USD-M perpetual",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_utc": START.isoformat(), "end_exclusive_utc": END.isoformat(),
        "aggtrade_url": agg_url, "kline_url": kline_url,
        "price_level_definition": "exact aggTrade price; no coarser rounding",
        "aggressor_side": "buyer_maker=false => taker buy; true => taker sell",
        "tpo_definition": "count of distinct UTC 30-minute periods per day and exact traded price",
        "strategy_backtest_run": False,
    }
    try:
        agg_path, ad = download_checked(session, agg_url, src)
        meta["aggtrade_download"] = ad
        meta["aggtrade_sha256"] = ad["sha256"]
        meta["aggtrade_expected_sha256"] = ad["expected_sha256"]
        levels, astats = build_levels(agg_path)
        meta.update({
            "aggtrade_rows": astats["rows"], "first_agg_id": astats["first_id"],
            "last_agg_id": astats["last_id"],
            "first_timestamp_utc": pd.to_datetime(astats["first_ts"], unit="ms", utc=True).isoformat(),
            "last_timestamp_utc": pd.to_datetime(astats["last_ts"], unit="ms", utc=True).isoformat(),
            "aggregate_id_gaps": astats["id_gaps"], "duplicate_ids": astats["duplicate_ids"],
            "id_order_violations": astats["id_order_violations"],
            "timestamp_regressions": astats["timestamp_regressions"],
            "out_of_month_timestamps": astats["out_of_month"],
            "aggtrade_total_base_quantity": astats["total_qty"],
            "taker_buy_base_quantity": astats["buy_qty"], "taker_sell_base_quantity": astats["sell_qty"],
            "signed_delta_base_quantity": astats["signed_delta_qty"],
            "aggtrade_zip_validation": {k: astats[k] for k in ["zip_crc_pass", "csv_member", "uncompressed_csv_bytes", "csv_header_present"]},
        })
        kl_path, kd = download_checked(session, kline_url, src)
        meta["kline_download"] = kd
        meta["kline_sha256"] = kd["sha256"]
        meta["kline_expected_sha256"] = kd["expected_sha256"]
        kl, km = read_klines(kl_path)
        meta["kline_metadata"] = km
        bar = levels.groupby("bar_open_ms", as_index=False).agg(
            agg_volume=("total_qty", "sum"), agg_taker_buy=("taker_buy_qty", "sum"),
            agg_taker_sell=("taker_sell_qty", "sum"), agg_delta=("delta_qty", "sum"),
            price_levels=("price", "nunique"), aggtrade_count=("aggtrade_count", "sum"))
        recon = kl[["open_time_ms", "volume", "taker_buy_base"]].merge(
            bar, left_on="open_time_ms", right_on="bar_open_ms", how="outer", indicator=True)
        unmatched = int((recon["_merge"] != "both").sum())
        vrel = np.abs(recon.agg_volume - recon.volume) / recon.volume
        brel = np.abs(recon.agg_taker_buy - recon.taker_buy_base) / recon.taker_buy_base
        rec = {
            "kline_bars": int(len(kl)), "aggtrade_bars": int(bar.bar_open_ms.nunique()),
            "unmatched_bars": unmatched,
            "total_volume_relative_error": float(abs(bar.agg_volume.sum() - kl.volume.sum()) / kl.volume.sum()),
            "taker_buy_relative_error": float(abs(bar.agg_taker_buy.sum() - kl.taker_buy_base.sum()) / kl.taker_buy_base.sum()),
            "volume_per_bar_relative_error_p95": float(vrel.quantile(.95)),
            "volume_per_bar_relative_error_max": float(vrel.max()),
            "taker_buy_per_bar_relative_error_p95": float(brel.quantile(.95)),
            "taker_buy_per_bar_relative_error_max": float(brel.max()),
            "volume_pass": bool(abs(bar.agg_volume.sum() - kl.volume.sum()) / kl.volume.sum() <= .001),
            "taker_buy_pass": bool(abs(bar.agg_taker_buy.sum() - kl.taker_buy_base.sum()) / kl.taker_buy_base.sum() <= .001),
            "coverage_pass": bool(unmatched == 0 and len(kl) == EXPECTED_5M_BARS),
        }
        meta["reconciliation"] = rec
        recon.drop(columns=["_merge"]).to_csv(out / "reconciliation_5m.csv", index=False)
        levels["delta_qty"] = levels.taker_buy_qty - levels.taker_sell_qty
        bar_totals = bar[["bar_open_ms", "agg_volume", "agg_delta"]]
        levels = levels.merge(bar_totals, on="bar_open_ms", how="left", validate="many_to_one")
        levels["price_level_volume_share"] = levels.total_qty / levels.agg_volume
        levels["price_level_delta_ratio"] = levels.delta_qty / levels.total_qty
        levels["bar_delta_ratio"] = levels.agg_delta / levels.agg_volume
        levels["bar_open_utc"] = pd.to_datetime(levels.bar_open_ms, unit="ms", utc=True).astype(str)
        levels["price"] = levels.price.astype(float)
        levels.to_csv(out / "footprint_5m_price_levels.csv.gz", index=False,
                      compression={"method": "gzip", "compresslevel": 1}, float_format="%.12g")
        daily, summaries = build_daily_profiles(levels[["bar_open_ms", "day_open_ms", "period30m_open_ms",
            "price", "total_qty", "taker_buy_qty", "taker_sell_qty", "delta_qty"]].copy())
        daily["day_utc"] = pd.to_datetime(daily.day_open_ms, unit="ms", utc=True).astype(str)
        daily.to_csv(out / "daily_true_vp_tpo_by_price.csv.gz", index=False,
                     compression={"method": "gzip", "compresslevel": 1}, float_format="%.12g")
        summaries.to_csv(out / "daily_true_vp_tpo_summary.csv", index=False, float_format="%.12g")
        bar["bar_open_utc"] = pd.to_datetime(bar.bar_open_ms, unit="ms", utc=True).astype(str)
        bar.to_csv(out / "bar_delta_5m.csv", index=False, float_format="%.12g")
        tpo_ok = bool(daily.tpo_30m_count.between(1, 48).all())
        daily_ok = bool(daily.day_open_ms.nunique() == 30 and len(summaries) == 30)
        va_ok = bool((summaries.volume_value_area_share >= .70).all()
                     and ((summaries.volume_value_area_share < 1.0 - 1e-12) | (summaries.volume_poc_share >= .70)).all()
                     and (summaries.tpo_value_area_share >= .70).all()
                     and ((summaries.tpo_value_area_share < 1.0 - 1e-12) | (summaries.tpo_poc_share >= .70)).all())
        key_unique = not levels.duplicated(["bar_open_ms", "price"]).any()
        sums_ok = bool(abs(levels.total_qty.sum() - astats["total_qty"]) / astats["total_qty"] <= 1e-10
                       and abs(levels.taker_buy_qty.sum() - astats["buy_qty"]) / astats["buy_qty"] <= 1e-10
                       and abs(levels.taker_sell_qty.sum() - astats["sell_qty"]) / astats["sell_qty"] <= 1e-10
                       and np.allclose(levels.delta_qty, levels.taker_buy_qty - levels.taker_sell_qty, rtol=0, atol=1e-12))
        integrity = bool(ad["checksum_verified"] and kd["checksum_verified"]
                         and astats["zip_crc_pass"] and km["zip_crc_pass"]
                         and astats["duplicate_ids"] == 0 and astats["id_order_violations"] == 0
                         and astats["timestamp_regressions"] == 0 and astats["out_of_month"] == 0)
        reconciliation = bool(rec["volume_pass"] and rec["taker_buy_pass"] and rec["coverage_pass"])
        profile_validation = bool(tpo_ok and daily_ok and va_ok and key_unique and sums_ok)
        meta["integrity_pass"] = integrity
        meta["reconciliation_pass"] = reconciliation
        meta["profile_validation_pass"] = profile_validation
        meta["price_level_rows"] = int(len(levels))
        meta["daily_profile_days"] = int(len(summaries))
        meta["feature_summary"] = {
            "unique_price_levels": int(levels.price.nunique()),
            "bars_with_footprint": int(levels.bar_open_ms.nunique()),
            "mean_price_levels_per_5m_bar": float(bar.price_levels.mean()),
            "median_price_levels_per_5m_bar": float(bar.price_levels.median()),
            "max_price_levels_per_5m_bar": int(bar.price_levels.max()),
            "max_tpo_30m_count_at_one_price": int(daily.tpo_30m_count.max()),
            "daily_volume_value_area_share_min": float(summaries.volume_value_area_share.min()),
            "daily_tpo_value_area_share_min": float(summaries.tpo_value_area_share.min()),
            "price_level_key_unique": bool(key_unique),
            "price_level_quantity_sums_match": bool(sums_ok),
            "tpo_count_range_1_to_48": bool(tpo_ok),
            "daily_profiles_30_days": bool(daily_ok),
            "value_area_70pct_check": bool(va_ok),
        }
        meta["status"] = "PASS" if integrity and reconciliation and profile_validation else "FAIL"
        meta["interpretation"] = (
            "Exact-price trade-level volume-at-price, aggressor delta and 30m TPO features were reconstructed and validated for this one-month pilot. This is a data feature result, not a strategy edge."
            if meta["status"] == "PASS" else
            "Feature build failed at least one frozen validation. Do not use the outputs for strategy research until the failure is explained."
        )
        write_report(out, meta)
        return 0 if meta["status"] == "PASS" else 2
    except Exception as exc:
        meta["status"] = "FAILED"
        meta["error"] = repr(exc)
        meta["integrity_pass"] = False
        meta["reconciliation_pass"] = False
        meta["profile_validation_pass"] = False
        meta["interpretation"] = "The frozen feature build failed. No strategy result is available."
        write_report(out, meta)
        return 2


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="results/binance-true-footprint")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return 0
    return run(Path(a.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
