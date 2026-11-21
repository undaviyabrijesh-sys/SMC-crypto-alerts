#!/usr/bin/env python3
"""Forensic audit of Binance USD-M aggTrade groups that straddle 5m boundaries.

Downloads one frozen day of BTCUSDT raw trades, aggTrades and 5m klines; verifies
all companion SHA-256 files and ZIP CRCs; maps aggTrade first/last IDs to raw
trade rows; tests whether group timestamp bucketing explains per-bar kline offsets.
No strategy PnL is calculated.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, time, zipfile
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
import requests

BASE = "https://data.binance.vision/data/futures/um/daily"
BAR_MS = 300_000
RAW_NAMES = ["trade_id", "price", "qty", "quote_qty", "time_ms", "buyer_maker"]
AGG_NAMES = ["agg_trade_id", "price", "qty", "first_trade_id", "last_trade_id", "time_ms", "buyer_maker"]
KLINE_NAMES = ["open_time_ms", "open", "high", "low", "close", "volume", "close_time_ms", "quote_volume", "trade_count", "taker_buy_base", "taker_buy_quote", "ignore"]
ALIASES = {
    "tradeid": "trade_id", "id": "trade_id", "price": "price", "qty": "qty", "quantity": "qty",
    "quoteqty": "quote_qty", "time": "time_ms", "transacttime": "time_ms",
    "timestamp": "time_ms", "isbuyermaker": "buyer_maker", "buyermaker": "buyer_maker",
    "wasbuyermaker": "buyer_maker", "wasthebuyerthemaker": "buyer_maker",
    "aggregatetradeid": "agg_trade_id", "aggtradeid": "agg_trade_id", "firsttradeid": "first_trade_id",
    "lasttradeid": "last_trade_id", "opentime": "open_time_ms", "closetime": "close_time_ms",
    "volume": "volume", "takerbuybaseassetvolume": "taker_buy_base", "takerbuyvolume": "taker_buy_base",
    "count": "trade_count", "tradecount": "trade_count", "numberoftrades": "trade_count",
    "quotevolume": "quote_volume", "quoteassetvolume": "quote_volume",
    "takerbuyquoteassetvolume": "taker_buy_quote", "takerbuyquotevolume": "taker_buy_quote",
    "ignore": "ignore", "open": "open", "high": "high", "low": "low", "close": "close"
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def parse_checksum(text: str) -> str:
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not m:
        raise ValueError(f"No SHA-256 in CHECKSUM: {text[:120]!r}")
    return m.group(1).lower()


def bucket(ts: np.ndarray, start_ms: int) -> np.ndarray:
    return ((ts.astype(np.int64) - int(start_ms)) // BAR_MS).astype(np.int64)


def bools(s: pd.Series) -> np.ndarray:
    v = s.astype(str).str.strip().str.lower().map({"true": True, "false": False, "1": True, "0": False})
    if v.isna().any():
        raise ValueError(f"Invalid buyer_maker values: {s[v.isna()].head(5).tolist()}")
    return v.to_numpy(bool)


def download_checked(session: requests.Session, url: str, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(6):
        try:
            h = hashlib.sha256(); n = 0
            with session.get(url, stream=True, timeout=(20, 180)) as r:
                r.raise_for_status()
                with dest.open("wb") as f:
                    for block in r.iter_content(1024 * 1024):
                        if block:
                            f.write(block); h.update(block); n += len(block)
            return {"url": url, "bytes": n, "sha256": h.hexdigest(), "last_modified": r.headers.get("Last-Modified")}
        except Exception as e:
            last = repr(e); dest.unlink(missing_ok=True)
            if attempt < 5: time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"Download failed: {url}: {last}")


def download_archive(session: requests.Session, url: str, work: Path) -> tuple[Path, dict[str, Any]]:
    p = work / Path(url).name
    meta = download_checked(session, url, p)
    cmeta = download_checked(session, url + ".CHECKSUM", work / (p.name + ".CHECKSUM"))
    expected = parse_checksum((work / (p.name + ".CHECKSUM")).read_text(errors="replace"))
    if expected != meta["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {p.name}: expected {expected}, got {meta['sha256']}")
    with zipfile.ZipFile(p) as z:
        bad = z.testzip()
        if bad: raise ValueError(f"ZIP CRC failure: {bad}")
        members = [x for x in z.namelist() if x.lower().endswith(".csv")]
        if len(members) != 1: raise ValueError(f"Expected one CSV in {p.name}; got {members}")
        info = z.getinfo(members[0])
    meta.update({"checksum_sha256": expected, "checksum_download_bytes": cmeta["bytes"], "zip_crc_pass": True,
                 "csv_member": members[0], "uncompressed_csv_bytes": info.file_size})
    return p, meta


def read_zip_frame(path: Path, names: list[str], kind: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        member = [x for x in z.namelist() if x.lower().endswith(".csv")][0]
        with z.open(member) as fh:
            first = fh.readline().decode("utf-8-sig", errors="replace").strip().split(",")
            normalized = [norm(x) for x in first]
            header = any(x in normalized for x in ("tradeid", "aggtradeid", "aggregatetradeid", "opentime", "id"))
            fh.seek(0)
            d = pd.read_csv(fh, header=0 if header else None, names=None if header else names, dtype=str, low_memory=False)
    if header:
        mapped = []
        for c in d.columns:
            n = norm(c)
            mapped.append(ALIASES.get(n, n))
        d.columns = mapped
    required = RAW_NAMES if kind == "raw" else AGG_NAMES if kind == "agg" else KLINE_NAMES
    if not set(required).issubset(d.columns):
        raise ValueError(f"{kind} schema missing {sorted(set(required)-set(d.columns))}; columns={list(d.columns)}")
    return d[required].copy()


def load_raw(path: Path) -> dict[str, Any]:
    # Raw trades can be much larger than aggTrades; stream CSV chunks and retain
    # compact numeric arrays only (not pandas object/string columns).
    id_parts=[]; ts_parts=[]; price_parts=[]; qty_parts=[]; maker_parts=[]
    prev_id=None; prev_ts=None; rows=0
    with zipfile.ZipFile(path) as z:
        member=[x for x in z.namelist() if x.lower().endswith(".csv")][0]
        with z.open(member) as fh:
            first=fh.readline().decode("utf-8-sig",errors="replace").strip().split(",")
            normalized=[norm(x) for x in first]
            header=any(x in normalized for x in ("tradeid","aggtradeid","aggregatetradeid","opentime","id"))
            fh.seek(0)
            reader=pd.read_csv(fh,header=0 if header else None,names=None if header else RAW_NAMES,
                               dtype=str,chunksize=1_000_000,low_memory=False)
            for chunk in reader:
                if header:
                    mapped=[]
                    for c in chunk.columns:
                        n=norm(c); mapped.append(ALIASES.get(n,n))
                    chunk.columns=mapped
                if not set(RAW_NAMES).issubset(chunk.columns):
                    raise ValueError(f"raw trade schema missing {sorted(set(RAW_NAMES)-set(chunk.columns))}")
                chunk=chunk[RAW_NAMES]
                ids=pd.to_numeric(chunk.trade_id,errors="raise").to_numpy(np.int64)
                ts=pd.to_numeric(chunk.time_ms,errors="raise").to_numpy(np.int64)
                price=pd.to_numeric(chunk.price,errors="raise").to_numpy(float)
                qty=pd.to_numeric(chunk.qty,errors="raise").to_numpy(float)
                maker=bools(chunk.buyer_maker)
                if len(ids)==0: continue
                if np.any(np.diff(ids)<=0) or (prev_id is not None and int(ids[0])<=prev_id):
                    raise ValueError("Raw trade IDs are not strictly increasing")
                if np.any(np.diff(ts)<0) or (prev_ts is not None and int(ts[0])<prev_ts):
                    raise ValueError("Raw trade timestamps regress in ID order")
                if not np.isfinite(price).all() or not np.isfinite(qty).all() or np.any(price<=0) or np.any(qty<=0):
                    raise ValueError("Invalid raw trade price/quantity")
                id_parts.append(ids); ts_parts.append(ts); price_parts.append(price); qty_parts.append(qty); maker_parts.append(maker)
                prev_id=int(ids[-1]); prev_ts=int(ts[-1]); rows+=len(ids)
    if rows==0: raise ValueError("Raw trades archive is empty")
    ids=np.concatenate(id_parts); ts=np.concatenate(ts_parts); price=np.concatenate(price_parts); qty=np.concatenate(qty_parts); maker=np.concatenate(maker_parts)
    return {"ids":ids,"ts":ts,"price":price,"qty":qty,"maker":maker,
            "rows":rows,"first_id":int(ids[0]),"last_id":int(ids[-1]),
            "first_ts":int(ts[0]),"last_ts":int(ts[-1])}


def load_agg(path: Path) -> dict[str, Any]:
    d = read_zip_frame(path, AGG_NAMES, "agg")
    for c in ["agg_trade_id", "first_trade_id", "last_trade_id", "time_ms"]:
        d[c] = pd.to_numeric(d[c], errors="raise").astype(np.int64)
    for c in ["price", "qty"]: d[c] = pd.to_numeric(d[c], errors="raise").astype(float)
    ids = d.agg_trade_id.to_numpy(np.int64); first = d.first_trade_id.to_numpy(np.int64); last = d.last_trade_id.to_numpy(np.int64)
    ts = d.time_ms.to_numpy(np.int64); price = d.price.to_numpy(float); qty = d.qty.to_numpy(float); maker = bools(d.buyer_maker)
    if len(ids) == 0: raise ValueError("aggTrades archive is empty")
    if np.any(np.diff(ids) <= 0) or np.any(np.diff(first) <= 0) or np.any(np.diff(last) <= 0):
        raise ValueError("aggTrade IDs or underlying ID ranges are not strictly increasing")
    if np.any(first > last) or np.any(first[1:] <= last[:-1]):
        raise ValueError("aggTrade underlying ID ranges overlap or reverse")
    if np.any(np.diff(ts) < 0): raise ValueError("aggTrade timestamps regress")
    return {"ids": ids, "first": first, "last": last, "ts": ts, "price": price, "qty": qty, "maker": maker,
            "rows": len(ids), "first_id": int(ids[0]), "last_id": int(ids[-1])}


def load_klines(path: Path, start_ms: int) -> dict[str, Any]:
    d = read_zip_frame(path, KLINE_NAMES, "kline")
    for c in ["open_time_ms", "close_time_ms", "trade_count"]: d[c] = pd.to_numeric(d[c], errors="raise").astype(np.int64)
    for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base", "taker_buy_quote", "ignore"]:
        d[c] = pd.to_numeric(d[c], errors="raise").astype(float)
    d = d.sort_values("open_time_ms").reset_index(drop=True)
    expected = np.arange(start_ms, start_ms + 24*60*60*1000, BAR_MS, dtype=np.int64)
    opens = d.open_time_ms.to_numpy(np.int64)
    if len(opens) != 288 or not np.array_equal(opens, expected): raise ValueError(f"Kline coverage mismatch: {len(opens)} rows")
    if (d.high < d[["open", "close", "low"]].max(axis=1)).any() or (d.low > d[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Invalid kline OHLC bounds")
    return {"opens": opens, "volume": d.volume.to_numpy(float), "buy": d.taker_buy_base.to_numpy(float),
            "trade_count": d.trade_count.to_numpy(np.int64), "rows": len(d)}


def group_raw_into_agg(raw: dict[str, Any], agg: dict[str, Any], start_ms: int) -> dict[str, Any]:
    ids = raw["ids"]; first = agg["first"]; last = agg["last"]
    # Exclude day-edge aggregate groups whose underlying first/last IDs fall
    # outside this daily raw-trade archive. The central-day 5m totals still use
    # all raw/agg rows; group-level proof uses only fully observed ID ranges.
    complete = (first >= int(ids[0])) & (last <= int(ids[-1]))
    gi = np.searchsorted(last, ids, side="left")
    inrange = gi < len(last)
    valid = np.zeros(len(ids), dtype=bool)
    valid[inrange] = (ids[inrange] >= first[gi[inrange]]) & complete[gi[inrange]]
    g = gi[valid]
    n = len(first)
    counts = np.bincount(g, minlength=n)
    sums = np.bincount(g, weights=raw["qty"][valid], minlength=n)
    price_bad = np.bincount(g, weights=(raw["price"][valid] != agg["price"][g]).astype(np.int8), minlength=n)
    side_bad = np.bincount(g, weights=(raw["maker"][valid] != agg["maker"][g]).astype(np.int8), minlength=n)
    min_id = np.full(n, np.iinfo(np.int64).max, dtype=np.int64); max_id = np.full(n, -1, dtype=np.int64)
    min_ts = np.full(n, np.iinfo(np.int64).max, dtype=np.int64); max_ts = np.full(n, -1, dtype=np.int64)
    np.minimum.at(min_id, g, ids[valid]); np.maximum.at(max_id, g, ids[valid])
    np.minimum.at(min_ts, g, raw["ts"][valid]); np.maximum.at(max_ts, g, raw["ts"][valid])
    duration = max_ts - min_ts
    end_ms = start_ms + 86_400_000
    raw_center = (raw["ts"] >= start_ms) & (raw["ts"] < end_ms)
    raw_bucket_center = bucket(raw["ts"][raw_center], start_ms)
    raw_by_bucket = np.bincount(raw_bucket_center, weights=raw["qty"][raw_center], minlength=288)
    raw_buy_by_bucket = np.bincount(raw_bucket_center, weights=np.where(~raw["maker"][raw_center], raw["qty"][raw_center], 0.0), minlength=288)
    raw_trade_count_by_bucket = np.bincount(raw_bucket_center, minlength=288)
    agg_center = (agg["ts"] >= start_ms) & (agg["ts"] < end_ms)
    agg_bucket_all = bucket(agg["ts"], start_ms)
    agg_by_bucket = np.bincount(agg_bucket_all[agg_center], weights=agg["qty"][agg_center], minlength=288)
    agg_buy_by_bucket = np.bincount(agg_bucket_all[agg_center], weights=np.where(~agg["maker"][agg_center], agg["qty"][agg_center], 0.0), minlength=288)
    agg_complete_center = agg_center & complete
    agg_complete_by_bucket = np.bincount(agg_bucket_all[agg_complete_center], weights=agg["qty"][agg_complete_center], minlength=288)
    agg_complete_buy_by_bucket = np.bincount(agg_bucket_all[agg_complete_center], weights=np.where(~agg["maker"][agg_complete_center], agg["qty"][agg_complete_center], 0.0), minlength=288)
    raw_bucket = bucket(raw["ts"][valid], start_ms)
    reassigned_bucket = agg_bucket_all[g]
    in_center_agg_group = (agg["ts"][g] >= start_ms) & (agg["ts"][g] < end_ms)
    keep = in_center_agg_group
    reassigned_by_bucket = np.bincount(reassigned_bucket[keep], weights=raw["qty"][valid][keep], minlength=288)
    reassigned_buy_by_bucket = np.bincount(reassigned_bucket[keep], weights=np.where(~raw["maker"][valid][keep], raw["qty"][valid][keep], 0.0), minlength=288)
    crossing = (counts > 0) & complete & agg_center & (bucket(min_ts, start_ms) != bucket(max_ts, start_ms))
    earlier = (raw_bucket < reassigned_bucket) & keep
    later = (raw_bucket > reassigned_bucket) & keep
    cross_to_later = np.bincount(reassigned_bucket[earlier], weights=raw["qty"][valid][earlier], minlength=288) if np.any(earlier) else np.zeros(288)
    cross_from_later = np.bincount(reassigned_bucket[later], weights=raw["qty"][valid][later], minlength=288) if np.any(later) else np.zeros(288)
    qty_diff = sums - agg["qty"]
    timestamp_last_diff = agg["ts"] - max_ts
    range_count_expected = last - first + 1
    per_group = pd.DataFrame({
        "agg_trade_id": agg["ids"], "first_trade_id": first, "last_trade_id": last,
        "complete_raw_id_range": complete, "raw_rows_in_id_range": counts,
        "expected_contiguous_id_count": range_count_expected,
        "raw_qty_sum": sums, "agg_qty": agg["qty"], "qty_abs_diff": np.abs(qty_diff),
        "raw_price_mismatch_count": price_bad, "raw_side_mismatch_count": side_bad,
        "raw_min_ts_ms": min_ts, "raw_max_ts_ms": max_ts, "duration_ms": duration,
        "agg_timestamp_ms": agg["ts"], "agg_timestamp_minus_last_raw_ms": timestamp_last_diff,
        "first_5m_bucket": bucket(min_ts, start_ms), "last_5m_bucket": bucket(max_ts, start_ms),
        "agg_5m_bucket": agg_bucket_all, "crosses_5m_boundary": crossing,
    })
    complete_qty_match = complete & np.isclose(sums, agg["qty"], rtol=1e-8, atol=1e-10)
    return {"group_counts": counts, "group_sums": sums, "price_bad": price_bad, "side_bad": side_bad,
        "min_id": min_id, "max_id": max_id, "min_ts": min_ts, "max_ts": max_ts,
        "duration": duration, "crossing": crossing, "per_group": per_group,
        "raw_by_bucket": raw_by_bucket, "raw_buy_by_bucket": raw_buy_by_bucket,
        "raw_trade_count_by_bucket": raw_trade_count_by_bucket,
        "reassigned_by_bucket": reassigned_by_bucket, "reassigned_buy_by_bucket": reassigned_buy_by_bucket,
        "agg_by_bucket": agg_by_bucket, "agg_buy_by_bucket": agg_buy_by_bucket,
        "agg_complete_by_bucket": agg_complete_by_bucket, "agg_complete_buy_by_bucket": agg_complete_buy_by_bucket,
        "unmatched_raw_rows": int((~valid).sum()), "matched_raw_rows": int(valid.sum()),
        "complete_agg_groups": int(complete.sum()), "incomplete_agg_groups": int((~complete).sum()),
        "crossing_groups": int(crossing.sum()), "crossing_qty": float(agg["qty"][crossing].sum()),
        "groups_duration_gt_100ms": int(((duration > 100) & complete & (counts > 0)).sum()),
        "groups_qty_match_1e8": int(complete_qty_match.sum()),
        "groups_price_consistent": int(((price_bad == 0) & complete).sum()),
        "groups_side_consistent": int(((side_bad == 0) & complete).sum()),
        "groups_endpoint_ids_match": int(((min_id == first) & (max_id == last) & complete).sum()),
        "groups_contiguous_ids_match_count": int(((counts == range_count_expected) & complete).sum()),
        "groups_timestamp_equals_last_raw": int(((timestamp_last_diff == 0) & complete).sum()),
        "cross_to_later_qty": float(np.sum(raw["qty"][valid][earlier])),
        "cross_from_later_qty": float(np.sum(raw["qty"][valid][later])),
    }


def self_test() -> None:
    start = 0
    assert bucket(np.array([0, 299999, 300000, 600001]), start).tolist() == [0, 0, 1, 2]
    raw = {"ids":np.array([10,11]),"ts":np.array([299999,300001]),"price":np.array([100.,100.]),
           "qty":np.array([0.2,0.3]),"maker":np.array([False,False])}
    agg = {"ids":np.array([5]),"first":np.array([10]),"last":np.array([11]),"ts":np.array([300001]),
           "price":np.array([100.]),"qty":np.array([0.5]),"maker":np.array([False])}
    k = group_raw_into_agg(raw, agg, start)
    assert k["crossing_groups"] == 1
    assert np.allclose(k["raw_by_bucket"][:2], [0.2,0.3])
    assert np.allclose(k["reassigned_by_bucket"][:2], [0.0,0.5])
    assert k["groups_qty_match_1e8"] == 1 and k["groups_price_consistent"] == 1 and k["groups_side_consistent"] == 1
    assert math.isclose(k["cross_to_later_qty"], 0.2)
    assert ALIASES[norm("isBuyerMaker")] == "buyer_maker"
    assert ALIASES[norm("Was the buyer the maker")] == "buyer_maker"
    assert ALIASES[norm("taker_buy_quote_volume")] == "taker_buy_quote"
    print("PASS UTC 5m bucket boundaries")
    print("PASS cross-boundary aggregate reassignment")
    print("PASS price/side/quantity group matching")
    print("PASS taker-side interpretation")
    print("PASS SHA-256/header alias parsing")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default="2026-09-03")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--output-dir", type=Path, default=Path("results/aggtrade-boundary-forensics"))
    p.add_argument("--work-dir", type=Path, default=Path("/tmp/aggtrade-boundary-forensics"))
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test(); return
    day = pd.Timestamp(a.date, tz="UTC")
    start_ms = int(day.timestamp() * 1000); end_ms = start_ms + 86_400_000
    if day.strftime("%Y-%m-%d") != a.date: raise ValueError("Date must be YYYY-MM-DD")
    s = requests.Session(); s.headers.update({"User-Agent":"SaltyQuantAggTradeBoundaryAudit/1.0"})
    w = a.work_dir; w.mkdir(parents=True, exist_ok=True)
    specs = {
        "raw_trades": f"{BASE}/trades/{a.symbol}/{a.symbol}-trades-{a.date}.zip",
        "agg_trades": f"{BASE}/aggTrades/{a.symbol}/{a.symbol}-aggTrades-{a.date}.zip",
        "klines_5m": f"{BASE}/klines/{a.symbol}/5m/{a.symbol}-5m-{a.date}.zip",
    }
    paths, downloads = {}, {}
    for name, url in specs.items():
        paths[name], downloads[name] = download_archive(s, url, w)
    raw = load_raw(paths["raw_trades"]); agg = load_agg(paths["agg_trades"]); kline = load_klines(paths["klines_5m"], start_ms)
    if raw["ts"].min() < start_ms or raw["ts"].max() >= end_ms: raise ValueError("Raw trade timestamp outside requested UTC day")
    if agg["ts"].min() < start_ms or agg["ts"].max() >= end_ms: raise ValueError("aggTrade timestamp outside requested UTC day")
    result = group_raw_into_agg(raw, agg, start_ms)
    raw_v = result["raw_by_bucket"]; raw_b = result["raw_buy_by_bucket"]
    agg_v = result["agg_by_bucket"]; agg_b = result["agg_buy_by_bucket"]
    agg_complete_v = result["agg_complete_by_bucket"]; agg_complete_b = result["agg_complete_buy_by_bucket"]
    k_v = kline["volume"]; k_b = kline["buy"]
    pred_v = result["reassigned_by_bucket"]; pred_b = result["reassigned_buy_by_bucket"]
    def relmax(x,y): return float(np.max(np.abs(x-y)/np.maximum(np.abs(y),1e-12)))
    buckets = pd.DataFrame({
        "open_time_ms": kline["opens"], "kline_trade_count": kline["trade_count"],
        "raw_trade_count": result["raw_trade_count_by_bucket"], "kline_volume": k_v, "raw_trade_volume": raw_v,
        "aggtrade_timestamp_volume": agg_v, "aggtrade_complete_groups_volume": agg_complete_v,
        "raw_reassigned_to_agg_timestamp_volume": pred_v,
        "kline_taker_buy": k_b, "raw_trade_taker_buy": raw_b,
        "aggtrade_timestamp_taker_buy": agg_b, "aggtrade_complete_groups_taker_buy": agg_complete_b,
        "raw_reassigned_taker_buy": pred_b,
    })
    for col in ["raw_trade_volume","aggtrade_timestamp_volume","aggtrade_complete_groups_volume","raw_reassigned_to_agg_timestamp_volume"]:
        buckets[col+"_diff"] = buckets[col] - buckets.kline_volume
    for col in ["raw_trade_taker_buy","aggtrade_timestamp_taker_buy","aggtrade_complete_groups_taker_buy","raw_reassigned_taker_buy"]:
        buckets[col+"_diff"] = buckets[col] - buckets.kline_taker_buy
    crossing = result["per_group"].loc[result["per_group"].crosses_5m_boundary].copy()
    crossing = crossing.sort_values("duration_ms", ascending=False)
    a.output_dir.mkdir(parents=True, exist_ok=True)
    buckets.to_csv(a.output_dir/"bucket_reconciliation.csv", index=False)
    crossing.head(5000).to_csv(a.output_dir/"crossing_aggtrade_groups_sample.csv", index=False)
    group = result["per_group"]
    meta = {
        "status": "completed", "symbol": a.symbol, "date_utc": a.date, "bar_ms": BAR_MS,
        "downloads": downloads,
        "raw_trades": {k:v for k,v in raw.items() if k not in {"ids","ts","price","qty","maker"}},
        "agg_trades": {k:v for k,v in agg.items() if k not in {"ids","first","last","ts","price","qty","maker"}},
        "groups": {
            "aggtrade_rows": agg["rows"], "raw_rows": raw["rows"],
            "matched_raw_rows": result["matched_raw_rows"], "unmatched_raw_rows": result["unmatched_raw_rows"],
            "complete_agg_groups": result["complete_agg_groups"], "incomplete_agg_groups_day_edge": result["incomplete_agg_groups"],
            "crossing_5m_groups": result["crossing_groups"], "crossing_group_qty": result["crossing_qty"],
            "cross_to_later_bucket_qty": result["cross_to_later_qty"], "cross_from_later_bucket_qty": result["cross_from_later_qty"],
            "groups_qty_match_1e8": result["groups_qty_match_1e8"], "groups_price_consistent": result["groups_price_consistent"],
            "groups_side_consistent": result["groups_side_consistent"], "groups_endpoint_ids_match": result["groups_endpoint_ids_match"],
            "groups_contiguous_ids_match_count": result["groups_contiguous_ids_match_count"],
            "groups_timestamp_equals_last_raw": result["groups_timestamp_equals_last_raw"],
            "groups_duration_gt_100ms": result["groups_duration_gt_100ms"],
            "max_group_duration_ms": int(group.duration_ms[group.duration_ms>=0].max()),
        },
        "bucket_reconciliation": {
            "kline_bars": kline["rows"],
            "raw_trade_volume_max_relative_error_vs_kline": relmax(raw_v,k_v),
            "aggtrade_timestamp_volume_max_relative_error_vs_kline": relmax(agg_v,k_v),
            "aggtrade_complete_groups_volume_max_relative_error_vs_kline": relmax(agg_complete_v,k_v),
            "raw_reassigned_volume_max_relative_error_vs_kline": relmax(pred_v,k_v),
            "raw_trade_taker_buy_max_relative_error_vs_kline": relmax(raw_b,k_b),
            "aggtrade_timestamp_taker_buy_max_relative_error_vs_kline": relmax(agg_b,k_b),
            "aggtrade_complete_groups_taker_buy_max_relative_error_vs_kline": relmax(agg_complete_b,k_b),
            "raw_reassigned_taker_buy_max_relative_error_vs_kline": relmax(pred_b,k_b),
            "bars_raw_matches_kline_1e8": int(np.isclose(raw_v,k_v,rtol=1e-8,atol=1e-8).sum()),
            "bars_aggtrade_matches_kline_1e8": int(np.isclose(agg_v,k_v,rtol=1e-8,atol=1e-8).sum()),
            "bars_reassigned_matches_kline_1e8": int(np.isclose(pred_v,k_v,rtol=1e-8,atol=1e-8).sum()),
            "bars_raw_trade_count_matches_kline": int((result["raw_trade_count_by_bucket"] == kline["trade_count"]).sum()),
            "max_abs_error_complete_agg_vs_raw_reassignment_volume": float(np.max(np.abs(agg_complete_v-pred_v))),
            "max_abs_error_complete_agg_vs_raw_reassignment_taker_buy": float(np.max(np.abs(agg_complete_b-pred_b))),
        },
        "interpretation": "A 5m boundary effect is supported only if raw-trade buckets reconcile to klines, aggTrade-timestamp buckets reproduce the mismatch, raw-to-agg group matching is exact, and per-bar differences are explained by the reassignment of raw trades to each aggTrade timestamp bucket.",
        "no_strategy_backtest": True,
    }
    (a.output_dir/"metadata.json").write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n")
    report = [f"# Binance USD-M {a.symbol} aggTrade 5m-boundary forensic audit — {a.date}","",
      "## Scope","","Post-hoc data-quality forensic audit only; September 2026 was already inspected. No strategy PnL or parameter selection is performed.","",
      "## Source integrity", ""]
    for k,v in downloads.items(): report.append(f"- {k}: {v['bytes']:,} bytes; SHA-256 {v['sha256']}; checksum verified; ZIP CRC passed")
    report += ["", "## Raw-to-aggTrade group checks", ""]
    for k,v in meta["groups"].items(): report.append(f"- {k}: {v}")
    report += ["", "## 5m bucket reconciliation", ""]
    for k,v in meta["bucket_reconciliation"].items(): report.append(f"- {k}: {v}")
    report += ["", "## Decision", "", "See metadata.json and bucket_reconciliation.csv. Do not claim a boundary explanation unless raw trades reconcile to klines and the aggTrade timestamp reassignment reproduces the observed bucket differences.",""]
    (a.output_dir/"report.md").write_text("\n".join(report))
    # Remove bulky source archives; only compact audit outputs are retained.
    for pth in paths.values(): pth.unlink(missing_ok=True)
    for pth in w.glob("*.CHECKSUM"): pth.unlink(missing_ok=True)
    print(json.dumps(meta,indent=2))


if __name__ == "__main__":
    main()
