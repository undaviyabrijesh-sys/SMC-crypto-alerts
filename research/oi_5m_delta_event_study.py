#!/usr/bin/env python3
"""Causal Delta 5m OI impulse event study for BTCUSD and ETHUSD.

Descriptive event study only; not a trading strategy or execution backtest.
Downloads public Delta OI/traded-price candles, validates 5m-to-1h OI
aggregation, measures forward price/OI behaviour, and compares the recent
month with Binance USD-M OI and price data where available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

DELTA_BASE = "https://api.india.delta.exchange"
BINANCE_BASE = "https://fapi.binance.com"
DELTA_MAX_CANDLES = 1800
STEP_5M, STEP_1H = 300, 3600
HORIZONS = {"5m": 1, "15m": 3, "1h": 12, "4h": 48}
OI_THRESHOLDS_PCT = (1.0, 2.0, 5.0, 10.0)
COOLDOWNS_BARS = (12, 96)  # 1h and 8h
MAIN_THRESHOLD_PCT, MAIN_COOLDOWN_BARS = 5.0, 12
LOOKBACK_BARS, MIN_LOOKBACK = 288, 72  # prior 24h, current observation excluded


class StudyError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def request_json(session: requests.Session, url: str, params: dict,
                 retries: int = 5, timeout: int = 30) -> tuple[Any, bytes]:
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = session.get(url, params=params,
                headers={"Accept": "application/json", "User-Agent": "SaltyQuantOI5mStudy/1.0"},
                timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= retries:
                    response.raise_for_status()
                try:
                    delay = float(response.headers.get("Retry-After", "0"))
                except (TypeError, ValueError):
                    delay = 0.0
                time.sleep(min(30.0, max(delay, 0.5 * (2 ** attempt))))
                continue
            response.raise_for_status()
            return response.json(), response.content
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status != 429 and status < 500:
                raise
            if attempt >= retries:
                raise
            time.sleep(min(30.0, 0.5 * (2 ** attempt)))
    raise StudyError(f"HTTP retries exhausted: {last_error}")


def fetch_delta_series(session: requests.Session, api_symbol: str, resolution: str,
                       step: int, start_epoch: int, end_epoch: int,
                       output_path: Path, request_delay: float = 0.12) -> dict:
    """Download inclusive Delta chunks and retain only fully closed candles."""
    if end_epoch <= start_epoch:
        raise ValueError("end must be later than start")
    rows, response_hash, requests_count = [], hashlib.sha256(), 0
    cursor, span = int(start_epoch), step * DELTA_MAX_CANDLES - 1
    while cursor < end_epoch:
        chunk_end = min(end_epoch - 1, cursor + span)
        payload, raw = request_json(session, f"{DELTA_BASE}/v2/history/candles", {
            "resolution": resolution, "symbol": api_symbol,
            "start": str(cursor), "end": str(chunk_end)})
        response_hash.update(raw)
        requests_count += 1
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise StudyError(f"Delta unsuccessful payload: {api_symbol} {resolution}")
        data = payload.get("result") or []
        if not isinstance(data, list) or len(data) > DELTA_MAX_CANDLES:
            raise StudyError(f"Delta invalid row count: {api_symbol} {resolution}")
        for item in data:
            try:
                ts = int(item["time"])
                vals = {k: float(item[k]) for k in ("open", "high", "low", "close")}
                volume = float(item.get("volume", 0.0) or 0.0)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise StudyError(f"Malformed Delta candle: {api_symbol} {resolution}") from exc
            if not all(math.isfinite(v) for v in (*vals.values(), volume)) or volume < 0:
                raise StudyError(f"Non-finite Delta candle: {api_symbol} {resolution}")
            if vals["high"] < max(vals["open"], vals["close"], vals["low"]):
                raise StudyError(f"Invalid high bound: {api_symbol} at {ts}")
            if vals["low"] > min(vals["open"], vals["close"], vals["high"]):
                raise StudyError(f"Invalid low bound: {api_symbol} at {ts}")
            if min(vals.values()) < 0 or (api_symbol.startswith("OI:") and min(vals.values()) <= 0):
                raise StudyError(f"Invalid non-positive OHLC: {api_symbol} at {ts}")
            rows.append({"timestamp": ts, **vals, "volume": volume})
        cursor = chunk_end + 1
        if request_delay:
            time.sleep(request_delay)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise StudyError(f"No Delta rows returned: {api_symbol} {resolution}")
    frame["timestamp"] = pd.to_datetime(frame.timestamp, unit="s", utc=True)
    frame = frame.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    start = pd.to_datetime(start_epoch, unit="s", utc=True)
    end = pd.to_datetime(end_epoch, unit="s", utc=True)
    frame = frame[(frame.timestamp >= start) &
                  (frame.timestamp + pd.Timedelta(seconds=step) <= end)]
    if frame.empty:
        raise StudyError(f"No fully closed Delta rows: {api_symbol} {resolution}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False, float_format="%.12g")
    idx = pd.DatetimeIndex(frame.timestamp)
    delta = idx.to_series().diff().dropna().dt.total_seconds()
    return {
        "api_symbol": api_symbol, "resolution": resolution, "step_seconds": step,
        "rows": int(len(frame)), "first_open_utc": idx.min().isoformat(),
        "last_open_utc": idx.max().isoformat(),
        "last_close_utc": (idx.max() + pd.Timedelta(seconds=step)).isoformat(),
        "gap_intervals": int((delta > step * 1.5).sum()),
        "irregular_intervals": int((delta != step).sum()),
        "largest_gap_seconds": int(delta.max()) if len(delta) else 0,
        "csv_sha256": sha256_file(output_path),
        "response_bytes_sha256": response_hash.hexdigest(),
        "request_count": requests_count, "csv_path": str(output_path)}


def load_delta_csv(path: Path, label: str) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["timestamp"])
    d["timestamp"] = pd.to_datetime(d.timestamp, utc=True)
    if d.timestamp.duplicated().any():
        raise StudyError(f"{label}: duplicate timestamps")
    d = d.sort_values("timestamp").set_index("timestamp")
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="raise")
        if not np.isfinite(d[c].to_numpy(float)).all():
            raise StudyError(f"{label}: non-finite {c}")
    if (d[["open", "high", "low", "close"]] <= 0).any().any():
        raise StudyError(f"{label}: non-positive OHLC")
    return d


def aggregate_5m_to_1h(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate only complete, exactly contiguous groups of twelve 5m bars."""
    rows = []
    for hour, g in frame.groupby(frame.index.floor("1h"), sort=True):
        expected = pd.date_range(hour, periods=12, freq="5min", tz="UTC")
        if len(g) != 12 or not g.index.equals(expected):
            continue
        rows.append({"hour_open": hour, "open": float(g.open.iloc[0]),
            "high": float(g.high.max()), "low": float(g.low.min()),
            "close": float(g.close.iloc[-1]), "bars_5m": 12})
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "bars_5m"],
            index=pd.DatetimeIndex([], tz="UTC", name="hour_open"))
    return pd.DataFrame(rows).set_index("hour_open").sort_index()


def aggregation_audit(five: pd.DataFrame, hourly: pd.DataFrame) -> dict:
    agg = aggregate_5m_to_1h(five)
    common = agg.index.intersection(hourly.index)
    comparisons = []
    for t in common:
        a, b = agg.loc[t], hourly.loc[t]
        diffs = {k: (float(a[k]) / float(b[k]) - 1.0) * 100.0
                 for k in ("open", "high", "low", "close") if float(b[k]) != 0}
        comparisons.append({"hour_open_utc": t.isoformat(), "relative_difference_pct": diffs,
            "match_within_0_1pct": all(abs(v) <= 0.1 for v in diffs.values())})
    matched = sum(x["match_within_0_1pct"] for x in comparisons)
    return {"complete_5m_hours": int(len(agg)), "hourly_api_rows": int(len(hourly)),
        "common_hours": int(len(common)), "matches_within_0_1pct": int(matched),
        "match_fraction_pct": round(100 * matched / len(common), 3) if len(common) else None,
        "examples": comparisons[:5] + comparisons[-5:] if comparisons else []}


def build_features(oi: pd.DataFrame, price: pd.DataFrame) -> pd.DataFrame:
    common = oi.index.intersection(price.index)
    if len(common) < 2:
        raise StudyError(f"Too few aligned 5m OI/price rows: {len(common)}")
    d = pd.DataFrame(index=common)
    for k in ("open", "high", "low", "close"):
        d[f"oi_{k}"] = oi.loc[common, k]
        d[f"price_{k}"] = price.loc[common, k]
    d["volume"] = price.loc[common, "volume"]
    d["segment"] = (pd.Series(common, index=common).diff()
                    .ne(pd.Timedelta(minutes=5))).cumsum().astype(int)
    for col in ("oi_pct", "oi_z", "price_ret_5m", "trend24h"):
        d[col] = np.nan
    d["regime24h"] = pd.Series(index=common, dtype="object")
    for name in HORIZONS:
        d[f"fwd_price_{name}_pct"] = np.nan
        d[f"fwd_oi_{name}_pct"] = np.nan
    for _, g in d.groupby("segment", sort=True):
        ix = g.index
        oi_pct = g.oi_close.pct_change()
        roll = oi_pct.rolling(LOOKBACK_BARS, min_periods=MIN_LOOKBACK)
        oi_mean, oi_std = roll.mean().shift(1), roll.std(ddof=0).shift(1).replace(0, np.nan)
        d.loc[ix, "oi_pct"] = oi_pct.to_numpy()
        d.loc[ix, "oi_z"] = ((oi_pct - oi_mean) / oi_std).to_numpy()
        d.loc[ix, "price_ret_5m"] = (g.price_close / g.price_open - 1).to_numpy()
        trend = g.price_close / g.price_close.shift(288) - 1
        d.loc[ix, "trend24h"] = trend.to_numpy()
        regime = pd.Series(np.select([trend > 0.005, trend < -0.005],
            ["uptrend", "downtrend"], default="range"), index=ix, dtype="object")
        regime.loc[trend.isna()] = None
        d.loc[ix, "regime24h"] = regime.to_numpy()
        for name, bars in HORIZONS.items():
            d.loc[ix, f"fwd_price_{name}_pct"] = (
                g.price_close.shift(-bars) / g.price_close - 1).to_numpy() * 100
            d.loc[ix, f"fwd_oi_{name}_pct"] = (
                g.oi_close.shift(-bars) / g.oi_close - 1).to_numpy() * 100
    d["available_time"] = d.index + pd.Timedelta(minutes=5)
    d = d.set_index("available_time", drop=True)
    d.index.name = "available_time"
    return d


def select_events(features: pd.DataFrame, threshold_pct: float,
                  cooldown_bars: int) -> pd.DataFrame:
    """Select using only current OI change, segment and event time, never outcomes."""
    x = features[(features.oi_pct.abs() * 100 >= threshold_pct) & features.split_safe_4h].copy()
    if x.empty:
        return x
    keep, last_by_segment = [], {}
    for t, row in x.sort_index().iterrows():
        seg = int(row.segment)
        last = last_by_segment.get(seg)
        if last is None or (t - last) >= pd.Timedelta(minutes=5 * cooldown_bars):
            keep.append(t)
            last_by_segment[seg] = t
    x = x.loc[keep].copy()
    x["oi_direction"] = np.where(x.oi_pct > 0, "expansion", "contraction")
    x["price_direction"] = np.select([x.price_ret_5m > 0, x.price_ret_5m < 0],
        ["up", "down"], default="flat")
    x["month"] = x.index.strftime("%Y-%m")
    return x


def split_boundaries(index: pd.DatetimeIndex) -> tuple[pd.Timestamp, pd.Timestamp]:
    span = index.max() - index.min()
    return index.min() + 0.70 * span, index.min() + 0.85 * span


def label_splits(features: pd.DataFrame) -> pd.DataFrame:
    a, b = split_boundaries(features.index)
    out = features.copy()
    out["split"] = np.where(out.index <= a, "train",
        np.where(out.index <= b, "validation", "oos"))
    split_end = pd.Series(index=out.index, dtype="datetime64[ns, UTC]")
    split_end.loc[out.split == "train"] = a
    split_end.loc[out.split == "validation"] = b
    split_end.loc[out.split == "oos"] = out.index.max()
    out["split_end"] = split_end
    out["split_safe_4h"] = (out.index + pd.Timedelta(hours=4)) <= split_end.to_numpy()
    return out


def event_metrics(x: pd.DataFrame) -> dict:
    if x.empty:
        return {"events": 0}
    result = {"events": int(len(x)),
        "expansions": int((x.oi_direction == "expansion").sum()),
        "contractions": int((x.oi_direction == "contraction").sum()),
        "mean_oi_change_pct": float(x.oi_pct.mean() * 100),
        "median_abs_oi_change_pct": float(x.oi_pct.abs().median() * 100),
        "mean_same_bar_price_return_pct": float(x.price_ret_5m.mean() * 100)}
    for horizon in HORIZONS:
        p, o = x[f"fwd_price_{horizon}_pct"].dropna(), x[f"fwd_oi_{horizon}_pct"].dropna()
        result[f"n_fwd_{horizon}"] = int(len(p))
        result[f"mean_fwd_price_{horizon}_pct"] = float(p.mean()) if len(p) else None
        result[f"median_fwd_price_{horizon}_pct"] = float(p.median()) if len(p) else None
        result[f"positive_fwd_price_{horizon}_pct"] = float((p > 0).mean() * 100) if len(p) else None
        result[f"mean_fwd_oi_{horizon}_pct"] = float(o.mean()) if len(o) else None
    directional = x[x.price_ret_5m != 0]
    for horizon in ("15m", "1h", "4h"):
        vals = directional[f"fwd_price_{horizon}_pct"].dropna()
        dirs = np.sign(directional.loc[vals.index, "price_ret_5m"])
        result[f"continuation_hit_{horizon}_pct"] = float((np.sign(vals) == dirs).mean() * 100) if len(vals) else None
        result[f"reversal_hit_{horizon}_pct"] = float((np.sign(vals) == -dirs).mean() * 100) if len(vals) else None
    return result


def matched_control_study(features: pd.DataFrame, main_events: pd.DataFrame,
                          threshold_pct: float = MAIN_THRESHOLD_PCT) -> tuple[pd.DataFrame, dict]:
    """Nearest non-event control matched on split, price direction, regime and train-only magnitude decile."""
    train_abs = features.loc[features.split == "train", "price_ret_5m"].abs().dropna()
    if len(train_abs) < 100:
        return pd.DataFrame(), {"matched_pairs": 0, "reason": "insufficient training returns"}
    edges = np.unique(np.quantile(train_abs, np.linspace(0, 1, 11)))
    bins = np.searchsorted(edges[1:-1], features.price_ret_5m.abs().to_numpy(), side="right")
    work = features.copy()
    work["price_bin"] = bins
    work["price_direction"] = np.select([work.price_ret_5m > 0, work.price_ret_5m < 0],
        ["up", "down"], default="flat")
    work["is_event"] = work.oi_pct.abs() * 100 >= threshold_pct
    controls, used, pairs = work[(~work.is_event) & work.split_safe_4h], set(), []
    for t, ev in main_events.sort_index().iterrows():
        if ev.price_direction == "flat" or pd.isna(ev.fwd_price_4h_pct):
            continue
        pool = controls[(controls.split == ev.split)
            & (controls.price_direction == ev.price_direction)
            & (controls.regime24h == ev.regime24h)
            & (controls.price_bin == work.loc[t, "price_bin"])
            & controls.fwd_price_4h_pct.notna()]
        if not pool.empty:
            pool = pool.loc[~pool.index.isin(used)]
        if pool.empty:
            continue
        distances = (pool.index - t).to_series(index=pool.index).abs()
        distances = distances[distances <= pd.Timedelta(hours=24)]
        if distances.empty:
            continue
        ctime = distances.idxmin()
        used.add(ctime)
        row = {"event_time": t, "control_time": ctime, "split": ev.split,
            "oi_direction": ev.oi_direction, "price_direction": ev.price_direction,
            "regime24h": ev.regime24h, "event_oi_pct": ev.oi_pct * 100,
            "control_oi_pct": work.loc[ctime, "oi_pct"] * 100}
        for h in ("15m", "1h", "4h"):
            row[f"event_fwd_{h}_pct"] = ev[f"fwd_price_{h}_pct"]
            row[f"control_fwd_{h}_pct"] = work.loc[ctime, f"fwd_price_{h}_pct"]
            row[f"event_minus_control_{h}_pct"] = row[f"event_fwd_{h}_pct"] - row[f"control_fwd_{h}_pct"]
        pairs.append(row)
    frame = pd.DataFrame(pairs)
    summary = {"matched_pairs": int(len(frame)),
        "matching": "same split, same 5m price direction, same prior-24h regime, same training-defined absolute-return decile; nearest within +/-24h; controls without replacement"}
    for h in ("15m", "1h", "4h"):
        c = f"event_minus_control_{h}_pct"
        summary[f"mean_event_minus_control_{h}_pct"] = float(frame[c].mean()) if len(frame) else None
        summary[f"event_beats_control_{h}_fraction_pct"] = float((frame[c] > 0).mean() * 100) if len(frame) else None
    return frame, summary


def fetch_binance_oi(session: requests.Session, symbol: str,
                     start_ms: int, end_ms: int) -> pd.DataFrame:
    """Fetch <=30d of 1h USD-M OI statistics in <=500-row chunks."""
    rows, cursor, period_ms = [], start_ms, 3600_000
    while cursor < end_ms:
        chunk_end = min(end_ms, cursor + 499 * period_ms)
        payload, _ = request_json(session, f"{BINANCE_BASE}/futures/data/openInterestHist", {
            "symbol": symbol, "period": "1h", "startTime": cursor,
            "endTime": chunk_end, "limit": 500})
        if not isinstance(payload, list):
            raise StudyError(f"Binance OI response not a list: {symbol}")
        if not payload:
            cursor = chunk_end + 1
            continue
        for r in payload:
            rows.append({"timestamp_ms": int(r["timestamp"]),
                "oi_contracts": float(r["sumOpenInterest"]),
                "oi_base": float(r["sumOpenInterestValue"])})
        latest = max(int(r["timestamp"]) for r in payload)
        if latest + 1 <= cursor:
            raise StudyError(f"Binance OI pagination stalled: {symbol}")
        cursor = latest + 1
    if not rows:
        raise StudyError(f"No Binance OI history: {symbol}")
    d = pd.DataFrame(rows).drop_duplicates("timestamp_ms").sort_values("timestamp_ms")
    d["available_time"] = pd.to_datetime(d.timestamp_ms, unit="ms", utc=True).dt.ceil("1h")
    d = d.drop_duplicates("available_time", keep="last").set_index("available_time").sort_index()
    d["oi_base_pct"] = d.oi_base.pct_change()
    return d


def fetch_binance_klines(session: requests.Session, symbol: str,
                         start_ms: int, end_ms: int) -> pd.DataFrame:
    payload, _ = request_json(session, f"{BINANCE_BASE}/fapi/v1/klines", {
        "symbol": symbol, "interval": "1h", "startTime": start_ms,
        "endTime": end_ms, "limit": 1500})
    if not isinstance(payload, list) or not payload:
        raise StudyError(f"No Binance 1h klines: {symbol}")
    rows = []
    for r in payload:
        open_ms = int(r[0])
        rows.append({"available_time": pd.to_datetime(open_ms + 3600_000, unit="ms", utc=True),
            "open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
            "close": float(r[4]), "volume": float(r[5])})
    d = pd.DataFrame(rows).drop_duplicates("available_time").sort_values("available_time").set_index("available_time")
    d["price_pct"] = d.close.pct_change()
    return d


def cross_venue_compare(delta_oi_5m: pd.DataFrame, delta_price_5m: pd.DataFrame,
                        binance_oi: pd.DataFrame, binance_price: pd.DataFrame) -> dict:
    d_oi, d_px = aggregate_5m_to_1h(delta_oi_5m), aggregate_5m_to_1h(delta_price_5m)
    hourly = pd.DataFrame({"oi_close": d_oi.close, "price_close": d_px.close}).dropna()
    d = pd.DataFrame(index=hourly.index + pd.Timedelta(hours=1))
    for _, g in hourly.groupby((hourly.index.to_series().diff()
                                .ne(pd.Timedelta(hours=1))).cumsum()):
        d.loc[g.index + pd.Timedelta(hours=1), "delta_oi_pct"] = g.oi_close.pct_change().to_numpy()
        d.loc[g.index + pd.Timedelta(hours=1), "delta_price_pct"] = g.price_close.pct_change().to_numpy()
    d.index.name = "available_time"
    common = d.join(binance_oi[["oi_base_pct"]], how="inner").join(binance_price[["price_pct"]], how="inner").dropna()
    return {"common_hourly_observations": int(len(common)),
        "binance_oi_rows": int(len(binance_oi)), "binance_price_rows": int(len(binance_price)),
        "delta_oi_binance_oi_pct_corr": float(common.delta_oi_pct.corr(common.oi_base_pct)) if len(common) >= 3 else None,
        "oi_change_sign_agreement_pct": float((np.sign(common.delta_oi_pct) == np.sign(common.oi_base_pct)).mean() * 100) if len(common) else None,
        "delta_price_binance_price_pct_corr": float(common.delta_price_pct.corr(common.price_pct)) if len(common) >= 3 else None,
        "price_change_sign_agreement_pct": float((np.sign(common.delta_price_pct) == np.sign(common.price_pct)).mean() * 100) if len(common) else None,
        "period_start_utc": common.index.min().isoformat() if len(common) else None,
        "period_end_utc": common.index.max().isoformat() if len(common) else None,
        "caveat": "Binance USD-M OI statistics retain only the latest month; this is recent-period context, not two-year independent OI history."}


def run(args) -> dict:
    data_dir, out_dir = Path(args.data_dir), Path(args.output_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC").floor("5min")
    start5, end5 = (now - pd.Timedelta(days=365.25 * args.years)).floor("5min"), now
    start1, end1 = start5.floor("1h"), end5.floor("1h")
    e5s, e5e, e1s, e1e = map(lambda x: int(x.timestamp()), (start5, end5, start1, end1))
    data_meta, frames = {}, {}
    with requests.Session() as session:
        for asset in ("BTC", "ETH"):
            contract = f"{asset}USD"
            specs = (
                ("oi_5m", f"OI:{contract}", "5m", STEP_5M, e5s, e5e),
                ("price_5m", contract, "5m", STEP_5M, e5s, e5e),
                ("oi_1h", f"OI:{contract}", "1h", STEP_1H, e1s, e1e))
            for label, api_symbol, resolution, step, start, end in specs:
                path = data_dir / f"{asset}_{label}.csv"
                data_meta[f"{asset}_{label}"] = fetch_delta_series(
                    session, api_symbol, resolution, step, start, end, path, args.request_delay)
                frames[f"{asset}_{label}"] = load_delta_csv(path, f"{asset} {label}")
        # Binance USD-M OI statistics are documented as latest-one-month only.
        b_end = pd.Timestamp.now(tz="UTC").floor("1h")
        b_start = b_end - pd.Timedelta(days=29)
        b_start_ms, b_end_ms = int(b_start.timestamp() * 1000), int(b_end.timestamp() * 1000)
        binance, binance_errors = {}, {}
        for asset in ("BTC", "ETH"):
            try:
                oi = fetch_binance_oi(session, f"{asset}USDT", b_start_ms, b_end_ms)
                px = fetch_binance_klines(session, f"{asset}USDT", b_start_ms, b_end_ms)
                oi, px = oi[oi.index <= b_end], px[px.index <= b_end]
                binance[asset] = (oi, px)
                for label, frame in ((f"{asset}_BINANCE_OI_1h", oi), (f"{asset}_BINANCE_PRICE_1h", px)):
                    path = data_dir / f"{label}.csv"
                    frame.reset_index().to_csv(path, index=False)
                    data_meta[label] = {"rows": len(frame), "csv_sha256": sha256_file(path),
                        "first_available_utc": frame.index.min().isoformat() if len(frame) else None,
                        "last_available_utc": frame.index.max().isoformat() if len(frame) else None}
            except Exception as exc:
                binance_errors[asset] = f"{type(exc).__name__}: {exc}"

    summaries, monthly, regimes, events_out, pairs_out = [], [], [], [], []
    cross_venue, quality, split_meta = {}, {}, {}
    for asset in ("BTC", "ETH"):
        oi5, px5, oi1 = (frames[f"{asset}_{k}"] for k in ("oi_5m", "price_5m", "oi_1h"))
        quality[asset] = {"oi_5m_rows": len(oi5), "price_5m_rows": len(px5), "oi_1h_rows": len(oi1),
            "oi_5m_gaps": data_meta[f"{asset}_oi_5m"]["gap_intervals"],
            "price_5m_gaps": data_meta[f"{asset}_price_5m"]["gap_intervals"],
            "oi_1h_gaps": data_meta[f"{asset}_oi_1h"]["gap_intervals"],
            "five_to_one_hour_aggregation": aggregation_audit(oi5, oi1)}
        f = label_splits(build_features(oi5, px5))
        if len(f) < 50_000:
            raise StudyError(f"{asset}: fewer than 50,000 aligned 5m rows; refusing shortened sample")
        a, b = split_boundaries(f.index)
        split_meta[asset] = {"train_end_available_utc": a.isoformat(),
            "validation_end_available_utc": b.isoformat(),
            "first_oos_available_utc": (b + pd.Timedelta(minutes=5)).isoformat(),
            "first_available_utc": f.index.min().isoformat(),
            "last_available_utc": f.index.max().isoformat(), "feature_rows": len(f)}
        f.reset_index().to_csv(out_dir / f"{asset.lower()}_features.csv", index=False)
        main_events = pd.DataFrame()
        for threshold in OI_THRESHOLDS_PCT:
            for cooldown in COOLDOWNS_BARS:
                ev = select_events(f, threshold, cooldown)
                for split in ("train", "validation", "oos"):
                    summaries.append({"asset": asset, "threshold_pct": threshold,
                        "cooldown_minutes": cooldown * 5, "split": split,
                        **event_metrics(ev[ev.split == split])})
                if threshold == MAIN_THRESHOLD_PCT and cooldown == MAIN_COOLDOWN_BARS:
                    main_events = ev.copy()
                    events_out.append(main_events.assign(asset=asset).reset_index())
                    for (month, direction), g in ev.groupby(["month", "oi_direction"]):
                        monthly.append({"asset": asset, "month": month, "oi_direction": direction, **event_metrics(g)})
                    for (split, regime, direction), g in ev.groupby(["split", "regime24h", "oi_direction"]):
                        regimes.append({"asset": asset, "split": split, "regime24h": regime,
                            "oi_direction": direction, **event_metrics(g)})
                    pairs, pair_summary = matched_control_study(f, ev)
                    cross_venue[f"{asset}_matched_control"] = pair_summary
                    if not pairs.empty:
                        pairs_out.append(pairs.assign(asset=asset))
        if asset in binance:
            cross_venue[f"{asset}_cross_venue"] = cross_venue_compare(oi5, px5, *binance[asset])
        else:
            cross_venue[f"{asset}_cross_venue"] = {"status": "unavailable", "error": binance_errors.get(asset)}

    pd.DataFrame(summaries).to_csv(out_dir / "event_summary.csv", index=False)
    pd.DataFrame(monthly).to_csv(out_dir / "monthly.csv", index=False)
    pd.DataFrame(regimes).to_csv(out_dir / "regimes.csv", index=False)
    if events_out:
        pd.concat(events_out, ignore_index=True).to_csv(out_dir / "main_5pct_events.csv", index=False)
    if pairs_out:
        pd.concat(pairs_out, ignore_index=True).to_csv(out_dir / "matched_controls.csv", index=False)
    metadata = {"classification": "descriptive event study only; not an executable strategy backtest",
        "venue": "Delta Exchange India OI-prefixed historical candles and traded-price candles",
        "period": {"requested_start_utc": start5.isoformat(), "requested_end_exclusive_utc": end5.isoformat()},
        "symbols": ["BTCUSD", "ETHUSD"], "data": data_meta, "data_quality": quality,
        "splits": split_meta,
        "event_method": {"signal_availability": "5m candle open + 5 minutes; only completed OI and traded-price bars",
            "thresholds_abs_oi_change_pct": list(OI_THRESHOLDS_PCT), "cooldowns_minutes": [60, 480],
            "main_spec": "absolute 5m OI close-to-close change >=5%, 60-minute cooldown; expansion/contraction separated",
            "zscore_context": "prior 288 completed 5m changes, current observation excluded; descriptive only",
            "outcomes": "future traded-price and OI close changes at 5m/15m/1h/4h; no outcome crosses a gap",
            "matching": "nearest non-event controls in same split, same 5m price direction, same prior-24h regime and training-defined absolute-return decile; no reuse; within +/-24h"},
        "cross_venue": cross_venue, "binance_errors": binance_errors,
        "limitations": ["Binance USD-M OI statistics retain only the latest month; cross-venue control is recent-period context, not two-year history.",
            "Delta OI values are treated as base-asset OI based on prior ticker/candle reconciliation; venue-specific OI is not economically identical to Binance aggregate OI.",
            "This is conditional forward behaviour, not a strategy test; no entries, stops, fees, funding, R, PF or trading drawdown.",
            "Matched controls are descriptive and may retain unobserved confounding.",
            "Historical Delta OI sampling remains exchange-specific despite prior live ticker and 5m/1h reconciliation."]}
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str) + "\n")
    md = ["# Delta 5m OI impulse event study — BTC/ETH", "",
        "Classification: descriptive event study only; not a strategy or executable backtest.", "",
        "## Main specification", "- Absolute 5m OI close-to-close change >=5%; 60-minute cooldown.",
        "- Event timestamp is candle open + 5m (close availability).",
        "- Outcomes: future traded-price and OI changes at 5m/15m/1h/4h; gaps are never filled.",
        "- Matched controls: same split/direction/regime and training-only absolute-return decile; nearest within +/-24h.", "",
        "## Data quality"]
    for asset, q in quality.items():
        agg = q["five_to_one_hour_aggregation"]
        md.append(f"- **{asset}:** OI5m {q['oi_5m_rows']:,}; traded price5m {q['price_5m_rows']:,}; OI1h {q['oi_1h_rows']:,}; 5m/1h OI match {agg['matches_within_0_1pct']}/{agg['common_hours']} common hours ({agg['match_fraction_pct']}%); gaps OI5m {q['oi_5m_gaps']}, price5m {q['price_5m_gaps']}, OI1h {q['oi_1h_gaps']}.")
    md += ["", "## Event summaries"]
    for row in summaries:
        if row["threshold_pct"] in (2.0, 5.0) and row["cooldown_minutes"] == 60:
            md.append(f"- {row['asset']} {row['split']} abs-OI>={row['threshold_pct']}%: {row.get('events',0)} events; mean 1h forward price {row.get('mean_fwd_price_1h_pct')}; 1h continuation hit {row.get('continuation_hit_1h_pct')}%; mean 1h OI change {row.get('mean_fwd_oi_1h_pct')}%.")
    md += ["", "## Matched controls and cross-venue", json.dumps(cross_venue, indent=2, default=str), "",
        "## Limitations", "- Binance USD-M OI statistics are limited to the latest month in official docs.",
        "- Venue OI series are not interchangeable; cross-venue results are context, not ground truth.",
        "- No net R, win rate, PF, trading drawdown or losing streak: no trade rules were tested.",
        "- No funding cashflows or transaction costs are applied.", ""]
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    return metadata


def self_test() -> None:
    t0 = pd.Timestamp("2025-01-01T00:00:00Z")
    idx = pd.date_range(t0, periods=600, freq="5min")
    oi_close = 1000 + np.arange(600) * 0.2
    px_close = 50000 + np.arange(600) * 3 + 100 * np.sin(np.arange(600) / 7)
    oi = pd.DataFrame({"open": oi_close - 0.1, "high": oi_close + 0.2,
        "low": oi_close - 0.2, "close": oi_close, "volume": 0.0}, index=idx)
    px = pd.DataFrame({"open": px_close - 1, "high": px_close + 5,
        "low": px_close - 5, "close": px_close, "volume": 10.0}, index=idx)
    f1 = label_splits(build_features(oi, px))
    assert f1.index[0] == idx[0] + pd.Timedelta(minutes=5)
    # Future perturbations must not change historical OI z-scores or events.
    oi2 = oi.copy()
    oi2.iloc[400:, oi2.columns.get_loc("close")] *= 1.2
    f2 = label_splits(build_features(oi2, px))
    pd.testing.assert_series_equal(f1.oi_z.iloc[:400], f2.oi_z.iloc[:400])
    e1, e2 = select_events(f1, 0.01, 12), select_events(f2, 0.01, 12)
    cutoff = idx[400] + pd.Timedelta(minutes=5)
    assert e1.index[e1.index < cutoff].equals(e2.index[e2.index < cutoff])
    for _, g in e1.groupby("segment"):
        assert (g.index.to_series().diff().dropna() >= pd.Timedelta(hours=1)).all()
    split_features = label_splits(build_features(oi, px))
    safe = split_features[split_features.split_safe_4h]
    assert ((safe.index + pd.Timedelta(hours=4)) <= safe.split_end).all()
    # Future returns cannot bridge a missing 5m interval.
    fg = build_features(oi.drop(idx[350]), px.drop(idx[350]))
    assert pd.isna(fg.loc[idx[350], "fwd_price_1h_pct"])
    # A complete 12-bar hour aggregates exactly.
    sample, agg = oi.iloc[:12], aggregate_5m_to_1h(oi.iloc[:12])
    assert len(agg) == 1 and agg.iloc[0].open == sample.open.iloc[0]
    assert agg.iloc[0].high == sample.high.max() and agg.iloc[0].low == sample.low.min()
    assert agg.iloc[0].close == sample.close.iloc[-1]
    print("6 OI 5m causality, cooldown, gap and aggregation tests passed")


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--data-dir", default="results/oi-5m-event-study/data")
    p.add_argument("--output-dir", default="results/oi-5m-event-study/report")
    p.add_argument("--request-delay", type=float, default=0.12)
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.self_test:
        self_test()
        return
    if not math.isfinite(args.years) or args.years <= 0 or args.years > 3:
        raise SystemExit("--years must be >0 and <=3")
    metadata = run(args)
    print(json.dumps({"classification": metadata["classification"],
        "data_quality": metadata["data_quality"], "cross_venue": metadata["cross_venue"]},
        indent=2, default=str))


if __name__ == "__main__":
    main()
