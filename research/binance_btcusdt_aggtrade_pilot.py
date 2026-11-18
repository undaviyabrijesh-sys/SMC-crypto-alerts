#!/usr/bin/env python3
"""Checksum-verified Binance USD-M BTCUSDT September 2026 aggTrades pilot."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
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
EXPECTED_5M_BARS = 30 * 24 * 12
AGG_COLS = ["agg_trade_id", "price", "quantity", "first_trade_id",
            "last_trade_id", "timestamp_ms", "buyer_maker"]
AGG_HEADER = ["agg_trade_id", "price", "quantity", "first_trade_id",
              "last_trade_id", "transact_time", "is_buyer_maker"]
KLINE_COLS = ["open_time_ms", "open", "high", "low", "close", "volume",
              "close_time_ms", "quote_volume", "trade_count",
              "taker_buy_base", "taker_buy_quote", "ignore"]
KLINE_HEADER = ["open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "count", "taker_buy_volume",
                "taker_buy_quote_volume", "ignore"]
KLINE_HEADER_VARIANTS = [
    KLINE_HEADER,
    ["open_time", "open", "high", "low", "close", "volume", "close_time",
     "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume",
     "taker_buy_quote_asset_volume", "ignore"],
]


def parse_checksum(text: str) -> str:
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not match:
        raise ValueError(f"Could not parse SHA-256 from CHECKSUM text: {text[:200]!r}")
    return match.group(1).lower()


def detect_csv_header(fh: Any, expected: list[str]) -> bool:
    first = fh.readline().decode("utf-8-sig").strip().split(",")
    normalized = [x.strip().lower() for x in first]
    variants = [expected]
    if expected == KLINE_HEADER:
        variants = KLINE_HEADER_VARIANTS
    if normalized in variants:
        return True
    fh.seek(0)
    return False


def parse_bool(s: pd.Series) -> np.ndarray:
    v = s.astype(str).str.strip().str.lower()
    mapped = v.map({"true": True, "false": False})
    if mapped.isna().any():
        bad = v[mapped.isna()].head(5).tolist()
        raise ValueError(f"Invalid buyer_maker values: {bad}")
    return mapped.to_numpy(dtype=bool)


def bucket_open_ms(ts_ms: np.ndarray) -> np.ndarray:
    return (ts_ms // BAR_MS) * BAR_MS


def self_test() -> None:
    assert parse_checksum("0123456789abcdef" * 4 + "  file.zip") == "0123456789abcdef" * 4
    s = pd.Series(["true", "false", "TRUE", "False"])
    assert parse_bool(s).tolist() == [True, False, True, False]
    assert bucket_open_ms(np.array([0, 299999, 300000, 600001], dtype=np.int64)).tolist() == [0, 0, 300000, 600000]
    assert detect_csv_header(io.BytesIO(b"agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"), AGG_HEADER)
    assert not detect_csv_header(io.BytesIO(b"1,100.0,0.1,10,10,1788220800000,false\n"), AGG_HEADER)
    print("5 deterministic aggTrade ingestion tests passed")


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
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if not block:
                            continue
                        out.write(block)
                        h.update(block)
                        total += len(block)
            return {"url": url, "path": str(path), "bytes": total, "sha256": h.hexdigest(),
                    "last_modified": response.headers.get("Last-Modified"),
                    "etag": response.headers.get("ETag")}
        except Exception as exc:
            last_error = repr(exc)
            path.unlink(missing_ok=True)
            if attempt + 1 < retries:
                time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"Download failed after {retries} attempts: {url}; {last_error}")


def download_checked_zip(session: requests.Session, url: str, dest: Path) -> tuple[Path, dict[str, Any]]:
    zip_path = dest / Path(url).name
    checksum_path = dest / (Path(url).name + ".CHECKSUM")
    checksum_url = url + ".CHECKSUM"
    zip_meta = download_file(session, url, zip_path)
    checksum_meta = download_file(session, checksum_url, checksum_path)
    checksum_text = checksum_path.read_text(encoding="utf-8", errors="replace")
    expected = parse_checksum(checksum_text)
    actual = zip_meta["sha256"]
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {url}: expected {expected}, got {actual}")
    zip_meta.update({"checksum_url": checksum_url, "checksum_path": str(checksum_path),
                     "checksum_text": checksum_text.strip(), "expected_sha256": expected,
                     "checksum_verified": True, "checksum_download": checksum_meta})
    return zip_path, zip_meta


def csv_member(path: Path) -> tuple[str, dict[str, Any]]:
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"ZIP CRC failure in {path.name}: {bad}")
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected exactly one CSV member in {path.name}; found {names}")
        info = zf.getinfo(names[0])
        return names[0], {"zip_crc_pass": True, "csv_member": names[0],
                          "uncompressed_csv_bytes": info.file_size, "zip_members": zf.namelist()}


def read_aggtrades(path: Path, bucket_acc: dict[str, np.ndarray]) -> dict[str, Any]:
    member, zip_meta = csv_member(path)
    totals = {"rows": 0, "buy_qty": 0.0, "sell_qty": 0.0, "quantity": 0.0,
              "first_agg_id": None, "last_agg_id": None, "first_timestamp_ms": None,
              "last_timestamp_ms": None, "aggregate_id_gaps": 0, "duplicate_ids": 0,
              "id_order_violations": 0, "timestamp_regressions": 0,
              "out_of_month_timestamps": 0, "invalid_numeric_rows": 0}
    prev_id = None
    prev_ts = None
    start_ms, end_ms = int(START.timestamp() * 1000), int(END.timestamp() * 1000)
    dtypes = {"agg_trade_id": "int64", "price": "float64", "quantity": "float64",
              "first_trade_id": "int64", "last_trade_id": "int64",
              "timestamp_ms": "int64", "buyer_maker": "bool"}
    with zipfile.ZipFile(path) as zf, zf.open(member) as fh:
        header_present = detect_csv_header(fh, AGG_HEADER)
        totals["csv_header_present"] = header_present
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
            valid = (np.isfinite(price) & np.isfinite(qty) & (price > 0) & (qty > 0)
                     & (first_id <= last_id))
            if not valid.all():
                bad_count = int((~valid).sum())
                totals["invalid_numeric_rows"] += bad_count
                raise ValueError(f"Invalid aggTrade numeric rows in {path.name}: {bad_count}")
            if np.any((ts < start_ms) | (ts >= end_ms)):
                totals["out_of_month_timestamps"] += int(np.sum((ts < start_ms) | (ts >= end_ms)))
                raise ValueError("AggTrade timestamp falls outside the frozen September 2026 interval")
            if len(ids) > 1:
                diffs = np.diff(ids)
                duplicate_count = int(np.sum(diffs == 0))
                order_count = int(np.sum(diffs < 0))
                totals["duplicate_ids"] += duplicate_count
                totals["id_order_violations"] += duplicate_count + order_count
                totals["aggregate_id_gaps"] += int(np.maximum(diffs - 1, 0).sum())
                totals["timestamp_regressions"] += int(np.sum(np.diff(ts) < 0))
                if duplicate_count or order_count:
                    raise ValueError("Aggregate trade IDs are not strictly increasing within archive order")
                if np.any(np.diff(ts) < 0):
                    raise ValueError("Timestamps regress while aggregate IDs increase")
            if prev_id is not None:
                if int(ids[0]) <= prev_id:
                    totals["duplicate_ids"] += int(ids[0] == prev_id)
                    totals["id_order_violations"] += 1
                    raise ValueError("Aggregate trade IDs are not strictly increasing across chunks")
                totals["aggregate_id_gaps"] += max(int(ids[0]) - prev_id - 1, 0)
                if int(ts[0]) < prev_ts:
                    totals["timestamp_regressions"] += 1
                    raise ValueError("Timestamp regresses across aggregate-trade chunks")
            if totals["first_agg_id"] is None:
                totals["first_agg_id"] = int(ids[0])
                totals["first_timestamp_ms"] = int(ts[0])
            totals["last_agg_id"] = int(ids[-1])
            totals["last_timestamp_ms"] = int(ts[-1])
            buy_mask = ~maker
            buy_qty = np.where(buy_mask, qty, 0.0)
            sell_qty = np.where(maker, qty, 0.0)
            bucket = ((ts - start_ms) // BAR_MS).astype(np.int64)
            if np.any((bucket < 0) | (bucket >= EXPECTED_5M_BARS)):
                raise ValueError("AggTrade timestamp mapped outside expected 5m bucket range")
            bucket_acc["quantity"] += np.bincount(bucket, weights=qty, minlength=EXPECTED_5M_BARS)
            bucket_acc["buy_qty"] += np.bincount(bucket, weights=buy_qty, minlength=EXPECTED_5M_BARS)
            bucket_acc["sell_qty"] += np.bincount(bucket, weights=sell_qty, minlength=EXPECTED_5M_BARS)
            bucket_acc["count"] += np.bincount(bucket, minlength=EXPECTED_5M_BARS).astype(np.int64)
            totals["rows"] += len(chunk)
            totals["quantity"] += float(qty.sum())
            totals["buy_qty"] += float(buy_qty.sum())
            totals["sell_qty"] += float(sell_qty.sum())
            prev_id, prev_ts = int(ids[-1]), int(ts[-1])
    if totals["rows"] == 0:
        raise ValueError("AggTrades archive contains no rows")
    totals["signed_delta_qty"] = totals["buy_qty"] - totals["sell_qty"]
    totals["net_delta_fraction_of_volume"] = totals["signed_delta_qty"] / totals["quantity"]
    totals.update(zip_meta)
    return totals


def read_klines(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    member, zip_meta = csv_member(path)
    with zipfile.ZipFile(path) as zf, zf.open(member) as fh:
        header_present = detect_csv_header(fh, KLINE_HEADER)
        d = pd.read_csv(fh, header=None, names=KLINE_COLS, dtype=str)
    zip_meta["csv_header_present"] = header_present
    if d.shape[1] != 12:
        raise ValueError(f"Unexpected kline column count: {d.shape[1]}")
    for col in ["open_time_ms", "close_time_ms", "trade_count"]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_base", "taker_buy_quote"]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    if d[["open_time_ms", "close_time_ms", "trade_count"]].isna().any().any():
        raise ValueError("Kline archive has invalid integer fields")
    if d[["open", "high", "low", "close", "volume", "taker_buy_base"]].isna().any().any():
        raise ValueError("Kline archive has non-numeric OHLCV fields")
    d["open_time_ms"] = d.open_time_ms.astype(np.int64)
    if d.open_time_ms.duplicated().any():
        raise ValueError("Duplicate kline open timestamps")
    d = d.sort_values("open_time_ms").reset_index(drop=True)
    start_ms, end_ms = int(START.timestamp() * 1000), int(END.timestamp() * 1000)
    if not ((d.open_time_ms >= start_ms) & (d.open_time_ms < end_ms)).all():
        raise ValueError("Kline open timestamp outside frozen September interval")
    expected = np.arange(start_ms, end_ms, BAR_MS, dtype=np.int64)
    missing = np.setdiff1d(expected, d.open_time_ms.to_numpy(np.int64))
    extra = np.setdiff1d(d.open_time_ms.to_numpy(np.int64), expected)
    if len(d) != EXPECTED_5M_BARS or len(missing) or len(extra):
        raise ValueError(f"Kline coverage mismatch: rows={len(d)}, missing={len(missing)}, extra={len(extra)}")
    shape = (d.high >= d[["open", "close", "low"]].max(axis=1)) & (d.low <= d[["open", "close", "high"]].min(axis=1))
    valid = (np.isfinite(d[["open", "high", "low", "close", "volume", "taker_buy_base"]]).all(axis=1)
             & (d[["open", "high", "low", "close"]] > 0).all(axis=1)
             & (d.volume >= 0) & (d.taker_buy_base >= 0)
             & (d.taker_buy_base <= d.volume + 1e-9) & shape)
    if not valid.all():
        raise ValueError(f"Invalid kline rows: {int((~valid).sum())}")
    meta = {"rows": len(d), "expected_rows": EXPECTED_5M_BARS, "missing_buckets": len(missing),
            "extra_buckets": len(extra), "start_utc": START.isoformat(),
            "end_exclusive_utc": END.isoformat(), "total_base_volume": float(d.volume.sum()),
            "total_taker_buy_base": float(d.taker_buy_base.sum()),
            "zero_volume_bars": int((d.volume == 0).sum()), **zip_meta}
    return d, meta


def reconcile(bucket_acc: dict[str, np.ndarray], klines: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    start_ms = int(START.timestamp() * 1000)
    open_times = np.arange(start_ms, start_ms + EXPECTED_5M_BARS * BAR_MS, BAR_MS, dtype=np.int64)
    a = pd.DataFrame({
        "open_time_ms": open_times,
        "agg_volume": bucket_acc["quantity"],
        "agg_taker_buy_base": bucket_acc["buy_qty"],
        "agg_taker_sell_base": bucket_acc["sell_qty"],
        "aggtrade_count": bucket_acc["count"],
    })
    k = klines[["open_time_ms", "volume", "taker_buy_base", "trade_count"]].rename(
        columns={"volume": "kline_volume", "taker_buy_base": "kline_taker_buy_base",
                 "trade_count": "kline_trade_count"})
    d = k.merge(a, on="open_time_ms", how="outer", indicator=True).sort_values("open_time_ms").reset_index(drop=True)
    left_only = int((d["_merge"] == "left_only").sum())
    right_only = int((d["_merge"] == "right_only").sum())
    d["agg_volume"] = d.agg_volume.fillna(0.0)
    d["agg_taker_buy_base"] = d.agg_taker_buy_base.fillna(0.0)
    d["agg_taker_sell_base"] = d.agg_taker_sell_base.fillna(0.0)
    d["aggtrade_count"] = d.aggtrade_count.fillna(0).astype(np.int64)
    d["volume_abs_rel_error"] = np.where(d.kline_volume > 0,
        np.abs(d.agg_volume - d.kline_volume) / d.kline_volume, np.nan)
    d["taker_buy_abs_rel_error"] = np.where(d.kline_taker_buy_base > 0,
        np.abs(d.agg_taker_buy_base - d.kline_taker_buy_base) / d.kline_taker_buy_base, np.nan)
    def rel(a0: float, b0: float) -> float:
        return abs(a0 - b0) / b0 if b0 else math.inf
    kvol, avol = float(d.kline_volume.sum(skipna=True)), float(d.agg_volume.sum())
    kbuy, abuy = float(d.kline_taker_buy_base.sum(skipna=True)), float(d.agg_taker_buy_base.sum())
    v_err, b_err = rel(avol, kvol), rel(abuy, kbuy)
    vm = d.volume_abs_rel_error.dropna().to_numpy(float)
    bm = d.taker_buy_abs_rel_error.dropna().to_numpy(float)
    both = d["_merge"].eq("both")
    active_agg = d.aggtrade_count > 0
    kline_positive = d.kline_volume.fillna(0.0) > 0
    missing_agg_buckets = int((~active_agg & kline_positive).sum())
    agg_only_buckets = int((active_agg & ~kline_positive).sum())
    exact_volume = np.isclose(d.loc[both, "agg_volume"], d.loc[both, "kline_volume"], rtol=1e-8, atol=1e-8)
    exact_buy = np.isclose(d.loc[both, "agg_taker_buy_base"], d.loc[both, "kline_taker_buy_base"], rtol=1e-8, atol=1e-8)
    summary = {
        "kline_buckets": int(len(klines)), "aggtrade_buckets": int(active_agg.sum()),
        "kline_only_buckets": missing_agg_buckets, "aggtrade_only_buckets": agg_only_buckets,
        "unmatched_timestamp_rows": left_only + right_only,
        "matched_buckets": int(both.sum()),
        "agg_total_base_quantity": avol, "kline_total_base_volume": kvol,
        "total_volume_relative_error": v_err,
        "agg_taker_buy_base_quantity": abuy, "kline_taker_buy_base_volume": kbuy,
        "taker_buy_total_relative_error": b_err,
        "volume_per_bar_relative_error_median": float(np.median(vm)) if len(vm) else None,
        "volume_per_bar_relative_error_p95": float(np.quantile(vm, .95)) if len(vm) else None,
        "volume_per_bar_relative_error_max": float(np.max(vm)) if len(vm) else None,
        "taker_buy_per_bar_relative_error_median": float(np.median(bm)) if len(bm) else None,
        "taker_buy_per_bar_relative_error_p95": float(np.quantile(bm, .95)) if len(bm) else None,
        "taker_buy_per_bar_relative_error_max": float(np.max(bm)) if len(bm) else None,
        "volume_exact_match_fraction_1e-8": float(exact_volume.mean()) if len(exact_volume) else 0.0,
        "taker_buy_exact_match_fraction_1e-8": float(exact_buy.mean()) if len(exact_buy) else 0.0,
        "total_volume_tolerance": 0.001, "taker_buy_tolerance": 0.001,
        "total_volume_pass": bool(v_err <= 0.001),
        "taker_buy_pass": bool(b_err <= 0.001),
        "bucket_coverage_pass": bool(missing_agg_buckets == 0 and agg_only_buckets == 0
                                     and left_only == 0 and right_only == 0
                                     and len(klines) == EXPECTED_5M_BARS),
    }
    d["agg_signed_delta_base"] = d.agg_taker_buy_base - d.agg_taker_sell_base
    return d.drop(columns=["_merge"]), summary


def write_report(out: Path, meta: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True, default=str))
    lines = [
        "# Binance USD-M BTCUSDT September 2026 aggTrades pilot",
        "",
        f"- Status: **{meta.get('status')}**",
        f"- Retrieved: {meta.get('retrieved_at_utc')}",
        f"- Requested interval: {START.isoformat()} to {END.isoformat()} (exclusive)",
        f"- Integrity pass: {meta.get('integrity_pass')}",
        f"- Reconciliation pass: {meta.get('reconciliation_pass')}",
        "",
        "## Archive integrity",
    ]
    for key in ["aggtrade_rows", "first_agg_id", "last_agg_id", "first_timestamp_utc",
                "last_timestamp_utc", "aggregate_id_gaps", "duplicate_ids", "id_order_violations",
                "timestamp_regressions", "out_of_month_timestamps", "aggtrade_total_base_quantity",
                "taker_buy_base_quantity", "taker_sell_base_quantity", "signed_delta_base_quantity"]:
        lines.append(f"- {key}: {meta.get(key)}")
    lines += ["", "## 5-minute reconciliation"]
    rec = meta.get("reconciliation", {})
    for key, value in rec.items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## Interpretation", meta.get("interpretation", "No interpretation recorded."),
              "", "## Source files"]
    for key in ["aggtrade_url", "aggtrade_sha256", "aggtrade_expected_sha256",
                "kline_url", "kline_sha256", "kline_expected_sha256"]:
        lines.append(f"- {key}: {meta.get(key)}")
    lines += ["", "No strategy backtest, signal test or trading result was run."]
    (out / "report.md").write_text("\n".join(lines) + "\n")


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    src = out / "source"
    src.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "SaltyQuant-ResearchDataAudit/1.0",
                            "Accept": "application/zip,application/octet-stream,*/*"})
    agg_url = f"{BASE}/monthly/aggTrades/{SYMBOL}/{SYMBOL}-aggTrades-2026-09.zip"
    kline_url = f"{BASE}/monthly/klines/{SYMBOL}/5m/{SYMBOL}-5m-2026-09.zip"
    meta: dict[str, Any] = {
        "status": "running", "symbol": SYMBOL, "market": "Binance USD-M perpetual",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_utc": START.isoformat(), "end_exclusive_utc": END.isoformat(),
        "aggtrade_url": agg_url, "kline_url": kline_url,
        "buyer_maker_convention": "true => buyer is maker, taker is seller; false => taker is buyer",
        "signed_delta_convention": "buy taker base quantity minus sell taker base quantity",
        "strategy_backtest_run": False,
    }
    try:
        agg_path, agg_download = download_checked_zip(session, agg_url, src)
        meta["aggtrade_download"] = agg_download
        meta["aggtrade_sha256"] = agg_download["sha256"]
        meta["aggtrade_expected_sha256"] = agg_download["expected_sha256"]
        bucket_acc = {
            "quantity": np.zeros(EXPECTED_5M_BARS, dtype=float),
            "buy_qty": np.zeros(EXPECTED_5M_BARS, dtype=float),
            "sell_qty": np.zeros(EXPECTED_5M_BARS, dtype=float),
            "count": np.zeros(EXPECTED_5M_BARS, dtype=np.int64),
        }
        agg_stats = read_aggtrades(agg_path, bucket_acc)
        meta.update({
            "aggtrade_rows": agg_stats["rows"], "first_agg_id": agg_stats["first_agg_id"],
            "last_agg_id": agg_stats["last_agg_id"],
            "first_timestamp_utc": pd.to_datetime(agg_stats["first_timestamp_ms"], unit="ms", utc=True).isoformat(),
            "last_timestamp_utc": pd.to_datetime(agg_stats["last_timestamp_ms"], unit="ms", utc=True).isoformat(),
            "aggregate_id_gaps": agg_stats["aggregate_id_gaps"],
            "duplicate_ids": agg_stats["duplicate_ids"],
            "id_order_violations": agg_stats["id_order_violations"],
            "timestamp_regressions": agg_stats["timestamp_regressions"],
            "out_of_month_timestamps": agg_stats["out_of_month_timestamps"],
            "aggtrade_total_base_quantity": agg_stats["quantity"],
            "taker_buy_base_quantity": agg_stats["buy_qty"],
            "taker_sell_base_quantity": agg_stats["sell_qty"],
            "signed_delta_base_quantity": agg_stats["signed_delta_qty"],
            "net_delta_fraction_of_volume": agg_stats["net_delta_fraction_of_volume"],
            "aggtrade_zip_validation": {k: agg_stats[k] for k in ["zip_crc_pass", "csv_member", "uncompressed_csv_bytes", "csv_header_present"]},
        })
        kline_path, kline_download = download_checked_zip(session, kline_url, src)
        meta["kline_download"] = kline_download
        meta["kline_sha256"] = kline_download["sha256"]
        meta["kline_expected_sha256"] = kline_download["expected_sha256"]
        klines, kmeta = read_klines(kline_path)
        meta["kline_metadata"] = kmeta
        meta["kline_zip_validation"] = {k: kmeta[k] for k in ["zip_crc_pass", "csv_member", "uncompressed_csv_bytes", "csv_header_present"]}
        reconciled, rec = reconcile(bucket_acc, klines)
        reconciled["open_time_utc"] = pd.to_datetime(reconciled.open_time_ms, unit="ms", utc=True).astype(str)
        reconciled.to_csv(out / "reconciliation_5m.csv", index=False)
        meta["reconciliation"] = rec
        integrity = bool(agg_download["checksum_verified"] and kline_download["checksum_verified"]
                         and agg_stats["zip_crc_pass"] and agg_stats["duplicate_ids"] == 0
                         and agg_stats["id_order_violations"] == 0
                         and agg_stats["timestamp_regressions"] == 0
                         and agg_stats["out_of_month_timestamps"] == 0
                         and agg_stats["rows"] > 0)
        reconciliation = bool(rec["bucket_coverage_pass"] and rec["total_volume_pass"] and rec["taker_buy_pass"])
        meta["integrity_pass"] = integrity
        meta["reconciliation_pass"] = reconciliation
        meta["status"] = "PASS" if integrity and reconciliation else ("INTEGRITY_PASS_RECONCILIATION_FAIL" if integrity else "INTEGRITY_FAIL")
        meta["interpretation"] = (
            "Ready for a separately preregistered trade-level feature study; this pilot itself contains no strategy result."
            if integrity and reconciliation else
            "Not ready for signal research. Preserve the files and investigate the reported integrity/reconciliation failures; do not replace them with candle-volume proxies."
        )
        write_report(out, meta)
        return 0 if integrity and reconciliation else 2
    except Exception as exc:
        meta["status"] = "FAILED"
        meta["error"] = repr(exc)
        meta["integrity_pass"] = False
        meta["reconciliation_pass"] = False
        meta["interpretation"] = "The frozen data pilot failed before all required checks completed. No market or strategy result is available."
        write_report(out, meta)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=False, default="results/binance-aggtrade-pilot")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return run(Path(args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
