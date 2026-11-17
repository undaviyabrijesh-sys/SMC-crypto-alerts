from __future__ import annotations

# V2 audit: canonical Wilder ATR, explicit risk-rule alignment, and strict split isolation.

import argparse
import hashlib
import io
import zipfile
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

API = "https://fapi.binance.com/fapi/v1/klines"
BAR = pd.Timedelta(minutes=5)
BAR_MS = 5 * 60 * 1000
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
TARGETS_R = (1.5, 2.0, 3.0)
COSTS_BPS = (4, 7, 10, 20)
MAX_HOLD_BARS = 48
PROFILE_BINS = 48


@dataclass
class Profile:
    val: float
    vah: float
    poc: float
    bins: int
    total_volume: float
    total_tpo: int


def sha256_frame(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()


def download_symbol(symbol: str, years: int, data_dir: Path, delay: float = 0.15) -> tuple[pd.DataFrame, dict]:
    """Load official Binance USD-M monthly/daily archives (avoids geo-blocked REST API)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    cache = data_dir / f"{symbol}_5m.csv.gz"
    now = pd.Timestamp.now(tz="UTC")
    expected_start = (now - pd.DateOffset(years=years)).floor("5min")
    if cache.exists():
        cached = pd.read_csv(cache, compression="gzip", parse_dates=["timestamp"])
        cached["timestamp"] = pd.to_datetime(cached.timestamp, utc=True)
        cached = cached.set_index("timestamp").sort_index()
        if not cached.empty and cached.index.min() <= expected_start + pd.Timedelta(days=2) and cached.index.max() >= now.floor("5min") - pd.Timedelta(days=2):
            clean, meta = validate_data(cached, symbol, "Binance public-data archive cache")
            meta["cache_file"] = cache.name
            return clean, meta

    session = requests.Session()
    session.headers.update({"User-Agent": "SaltyQuant-OrderFlowResearch/1.0", "Accept": "application/zip,application/octet-stream,*/*"})
    frames: list[pd.DataFrame] = []
    archive_files, missing_files = [], []

    def read_archive(url: str) -> pd.DataFrame | None:
        for attempt in range(6):
            try:
                response = session.get(url, timeout=60)
                if response.status_code == 404:
                    return None
                if response.status_code in (418, 429, 500, 502, 503, 504):
                    time.sleep(min(20.0, 1 + attempt * 2))
                    continue
                response.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                    names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                    if not names:
                        raise RuntimeError(f"No CSV member inside {url}")
                    with zf.open(names[0]) as fh:
                        chunk = pd.read_csv(fh, header=None)
                    if chunk.empty:
                        return pd.DataFrame()
                    try:
                        int(str(chunk.iloc[0, 0]).strip())
                    except (TypeError, ValueError):
                        with zf.open(names[0]) as fh:
                            chunk = pd.read_csv(fh, header=0)
                    if chunk.shape[1] < 11:
                        raise RuntimeError(f"Unexpected kline column count {chunk.shape[1]} in {url}")
                    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trade_count", "taker_buy_base", "taker_buy_quote", "ignore"]
                    chunk = chunk.iloc[:, :len(cols)]
                    if chunk.shape[1] == 11:
                        cols = cols[:11]
                    chunk.columns = cols[:chunk.shape[1]]
                    return chunk[["open_time", "open", "high", "low", "close", "volume", "taker_buy_base", "trade_count"]]
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(min(20.0, 1 + attempt * 2))
        raise RuntimeError(f"Could not download archive: {url}")

    first_month, current_month = expected_start.to_period("M"), now.to_period("M")
    for period in pd.period_range(first_month, current_month, freq="M"):
        if period == current_month:
            # Daily archives are published after the UTC day closes; today's file is not yet available.
            last_day = now.floor("D") - pd.Timedelta(days=1)
            day = period.start_time.tz_localize("UTC")
            while day <= last_day:
                date_str = day.strftime("%Y-%m-%d")
                url = f"https://data.binance.vision/data/futures/um/daily/klines/{symbol}/5m/{symbol}-5m-{date_str}.zip"
                frame = read_archive(url)
                if frame is None:
                    missing_files.append(url)
                elif not frame.empty:
                    frames.append(frame)
                    archive_files.append(url)
                day += pd.Timedelta(days=1)
                time.sleep(delay)
        else:
            month_str = str(period)
            url = f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/5m/{symbol}-5m-{month_str}.zip"
            frame = read_archive(url)
            if frame is None:
                missing_files.append(url)
                first = period.start_time.tz_localize("UTC")
                end = (period + 1).start_time.tz_localize("UTC")
                day = first
                while day < end:
                    date_str = day.strftime("%Y-%m-%d")
                    daily_url = f"https://data.binance.vision/data/futures/um/daily/klines/{symbol}/5m/{symbol}-5m-{date_str}.zip"
                    day_frame = read_archive(daily_url)
                    if day_frame is not None and not day_frame.empty:
                        frames.append(day_frame)
                        archive_files.append(daily_url)
                    else:
                        missing_files.append(daily_url)
                    day += pd.Timedelta(days=1)
                    time.sleep(delay)
            elif not frame.empty:
                frames.append(frame)
                archive_files.append(url)
            time.sleep(delay)

    if not frames:
        raise RuntimeError(f"No Binance public-data archive candles found for {symbol}")
    raw = pd.concat(frames, ignore_index=True)
    raw["timestamp"] = pd.to_datetime(pd.to_numeric(raw.pop("open_time"), errors="coerce"), unit="ms", utc=True)
    raw = raw.set_index("timestamp").sort_index()
    for col in ("open", "high", "low", "close", "volume", "taker_buy_base", "trade_count"):
        if col in raw:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw = raw[["open", "high", "low", "close", "volume", "taker_buy_base", "trade_count"]]
    raw = raw[(raw.index >= expected_start) & (raw.index + BAR <= now)]
    clean, meta = validate_data(raw, symbol, "Binance public-data USD-M futures archives")
    clean.reset_index().to_csv(cache, index=False, compression="gzip", float_format="%.12g")
    meta.update({"archive_files_downloaded": len(archive_files), "missing_archive_files": len(missing_files),
                 "missing_archive_examples": missing_files[:8], "cache_file": cache.name})
    return clean, meta

def validate_data(raw: pd.DataFrame, symbol: str, source: str) -> tuple[pd.DataFrame, dict]:
    d = raw.copy()
    if not isinstance(d.index, pd.DatetimeIndex):
        d.index = pd.to_datetime(d.index, utc=True, errors="coerce")
    elif d.index.tz is None:
        d.index = d.index.tz_localize("UTC")
    else:
        d.index = d.index.tz_convert("UTC")
    invalid_ts = int(d.index.isna().sum())
    d = d.loc[~d.index.isna()]
    duplicates = int(d.index.duplicated().sum())
    d = d[~d.index.duplicated(keep="last")].sort_index()
    needed = ["open", "high", "low", "close", "volume", "taker_buy_base"]
    for col in needed:
        if col not in d:
            raise ValueError(f"{symbol}: missing field {col}")
        d[col] = pd.to_numeric(d[col], errors="coerce")
    a = d[["open", "high", "low", "close"]].to_numpy(float)
    finite = np.isfinite(a).all(axis=1)
    positive = (d[["open", "high", "low", "close"]] > 0).all(axis=1).to_numpy()
    shape = ((d.high >= d[["open", "close", "low"]].max(axis=1)) & (d.low <= d[["open", "close", "high"]].min(axis=1))).to_numpy()
    volume = d.volume.to_numpy(float)
    taker = d.taker_buy_base.to_numpy(float)
    volume_ok = np.isfinite(volume) & (volume >= 0)
    taker_ok = np.isfinite(taker) & (taker >= 0) & (taker <= volume + 1e-9)
    valid = finite & positive & shape & volume_ok & taker_ok
    invalid_ohlc = int((~(finite & positive & shape)).sum())
    invalid_volume = int((~(volume_ok & taker_ok)).sum())
    d = d.loc[valid, needed + (["trade_count"] if "trade_count" in d else [])].copy()
    if d.empty:
        raise RuntimeError(f"{symbol}: no valid rows after validation")
    d["delta"] = 2.0 * d.taker_buy_base - d.volume
    d["delta_ratio"] = np.divide(d.delta, d.volume, out=np.zeros(len(d), dtype=float), where=d.volume.to_numpy(float) > 0)
    gaps = d.index.to_series().diff().dropna()
    meta = {
        "symbol": symbol, "source": source, "rows": int(len(d)),
        "start_utc": d.index.min().isoformat(), "end_utc": d.index.max().isoformat(),
        "invalid_timestamps": invalid_ts, "duplicates_removed": duplicates,
        "invalid_ohlc_rows": invalid_ohlc, "invalid_volume_or_taker_rows": invalid_volume,
        "zero_volume_bars": int((d.volume == 0).sum()),
        "gap_count": int((gaps != BAR).sum()),
        "largest_gap_minutes": float(gaps.max().total_seconds() / 60) if len(gaps) else 0.0,
        "sha256": sha256_frame(d),
    }
    return d, meta


def value_area(weights: np.ndarray, edges: np.ndarray, fraction: float = 0.70) -> tuple[float, float, float]:
    if len(weights) == 0 or not np.isfinite(weights).all() or float(weights.sum()) <= 0:
        raise ValueError("Profile weights must have a positive finite sum")
    poc_i = int(np.argmax(weights))
    left = right = poc_i
    cumulative = float(weights[poc_i])
    target = float(weights.sum()) * fraction
    while cumulative < target and (left > 0 or right < len(weights) - 1):
        lv = float(weights[left - 1]) if left > 0 else -1.0
        rv = float(weights[right + 1]) if right < len(weights) - 1 else -1.0
        if lv >= rv:
            left -= 1
            cumulative += lv
        else:
            right += 1
            cumulative += rv
    return float(edges[left]), float(edges[right + 1]), float((edges[poc_i] + edges[poc_i + 1]) / 2.0)


def build_day_profile(day: pd.DataFrame, bins: int = PROFILE_BINS) -> tuple[Profile, Profile]:
    """Build a 48-bin candle-volume proxy and a 5m time-at-price/TPO proxy."""
    lo, hi = float(day.low.min()), float(day.high.max())
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi < lo:
        raise ValueError("Invalid daily price range")
    if hi == lo:
        hi = lo + max(abs(lo) * 1e-8, 1e-8)
    edges = np.linspace(lo, hi, bins + 1)
    vp, tpo = np.zeros(bins, dtype=float), np.zeros(bins, dtype=float)
    for candle_low, candle_high, volume in zip(day.low.to_numpy(float), day.high.to_numpy(float), day.volume.to_numpy(float)):
        if candle_high <= candle_low:
            first = last = int(np.clip(np.searchsorted(edges, candle_low, side="right") - 1, 0, bins - 1))
        else:
            first = int(np.clip(np.searchsorted(edges, candle_low, side="right") - 1, 0, bins - 1))
            last = int(np.clip(np.searchsorted(edges, candle_high, side="left") - 1, 0, bins - 1))
            last = max(first, last)
        covered = np.arange(first, last + 1)
        vp[covered] += volume / len(covered)
        tpo[covered] += 1
    vval, vvah, vpoc = value_area(vp, edges)
    tval, tvah, tpoc = value_area(tpo, edges)
    return (Profile(vval, vvah, vpoc, bins, float(vp.sum()), int(tpo.sum())),
            Profile(tval, tvah, tpoc, bins, float(vp.sum()), int(tpo.sum())))


def wilder_atr_prior(f: pd.DataFrame, period: int = 14) -> pd.Series:
    """Canonical Wilder ATR, seeded by the first-period SMA and reset after data gaps."""
    values = np.full(len(f), np.nan, dtype=float)
    if len(f) == 0:
        return pd.Series(values, index=f.index)
    starts = np.r_[0, np.flatnonzero(np.diff(f.index.asi8) != BAR.value) + 1]
    ends = np.r_[starts[1:], len(f)]
    for start, end in zip(starts, ends):
        g = f.iloc[int(start):int(end)]
        prev = g.close.shift(1)
        # Avoid pandas row-wise max semantics for the first bar of each contiguous
        # segment: its prior close is unavailable, so TR must fall back to high-low.
        hl = (g.high - g.low).to_numpy(float)
        hc = (g.high - prev).abs().to_numpy(float)
        lc = (g.low - prev).abs().to_numpy(float)
        hc = np.nan_to_num(hc, nan=-np.inf)
        lc = np.nan_to_num(lc, nan=-np.inf)
        tr = np.maximum(hl, np.maximum(hc, lc))
        if len(tr) < period or not np.isfinite(tr[:period]).all():
            continue
        local = np.full(len(tr), np.nan, dtype=float)
        local[period - 1] = float(np.mean(tr[:period]))
        for k in range(period, len(tr)):
            local[k] = (local[k - 1] * (period - 1) + tr[k]) / period
        values[int(start):int(end)] = local
    return pd.Series(values, index=f.index).shift(1)


def add_features(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    f = d.copy()
    f["atr_prior"] = wilder_atr_prior(f, 14)
    for col in ("vp_val", "vp_vah", "vp_poc", "tpo_val", "tpo_vah", "tpo_poc"):
        f[col] = np.nan
    days = f.index.floor("D")
    profiles: dict[pd.Timestamp, tuple[Profile, Profile]] = {}
    for day_key in pd.unique(days):
        mask = days == day_key
        ix = f.index[mask]
        expected = pd.date_range(day_key, periods=288, freq="5min", tz="UTC")
        if len(ix) != 288 or not ix.equals(expected):
            continue
        vp, tpo = build_day_profile(f.loc[mask])
        profiles[pd.Timestamp(day_key) + pd.Timedelta(days=1)] = (vp, tpo)
    for day_key, (vp, tpo) in profiles.items():
        mask = days == day_key
        f.loc[mask, ["vp_val", "vp_vah", "vp_poc"]] = [vp.val, vp.vah, vp.poc]
        f.loc[mask, ["tpo_val", "tpo_vah", "tpo_poc"]] = [tpo.val, tpo.vah, tpo.poc]
    hourly = f[["open", "high", "low", "close", "volume"]].resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    hourly_count = f.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[hourly_count.eq(12)].copy()
    hourly["ema20"] = hourly.close.ewm(span=20, adjust=False, min_periods=20).mean()
    hourly["ema50"] = hourly.close.ewm(span=50, adjust=False, min_periods=50).mean()
    hourly["regime"] = np.select(
        [(hourly.close > hourly.ema20) & (hourly.ema20 > hourly.ema50),
         (hourly.close < hourly.ema20) & (hourly.ema20 < hourly.ema50)],
        ["bull", "bear"], default="neutral")
    f["regime_1h"] = hourly.regime.reindex(f.index, method="ffill").fillna("neutral")
    return f, {"complete_prior_utc_days": len(profiles), "profile_bins": PROFILE_BINS,
               "bars_without_prior_profile": int(f.vp_val.isna().sum())}


def _candidate(reject_i: int, entry_i: int, side: str, f: pd.DataFrame, day: str, setup: str, signal_i: int | None = None) -> dict[str, Any]:
    row = f.iloc[reject_i]
    atr = float(row.atr_prior)
    stop = float(row.low - 0.10 * atr) if side == "long" else float(row.high + 0.10 * atr)
    return {"reject_i": reject_i, "signal_i": reject_i if signal_i is None else signal_i,
            "entry_i": entry_i, "side": side, "day": day, "stop": stop,
            "atr_at_rejection": atr, "setup": setup}


def build_candidates(f: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """Generate three rule sets. Combined model waits for a later 5m MSS."""
    out = {"VP_ONLY": [], "TPO_DELTA": [], "VP_TPO_DELTA_MSS": []}
    n = len(f)
    cols = ["open", "high", "low", "close", "volume", "delta_ratio", "atr_prior",
            "vp_val", "vp_vah", "tpo_val", "tpo_vah"]
    a = {c: f[c].to_numpy() for c in cols}
    ts = f.index
    highs, lows, closes = a["high"], a["low"], a["close"]
    for i in range(14, n - 2):
        atr = a["atr_prior"][i]
        if not np.isfinite(atr) or atr <= 0 or not np.isfinite(a["vp_val"][i]) or a["volume"][i] <= 0:
            continue
        lo, hi, cl = lows[i], highs[i], closes[i]
        mid, d_ratio = (hi + lo) / 2.0, a["delta_ratio"][i]
        day = ts[i].floor("D").date().isoformat()
        long_vp = lo <= a["vp_val"][i] - 0.05 * atr and cl > a["vp_val"][i] and cl >= mid
        short_vp = hi >= a["vp_vah"][i] + 0.05 * atr and cl < a["vp_vah"][i] and cl <= mid
        if long_vp:
            out["VP_ONLY"].append(_candidate(i, i + 1, "long", f, day, "prior_day_volume_value_reclaim"))
        elif short_vp:
            out["VP_ONLY"].append(_candidate(i, i + 1, "short", f, day, "prior_day_volume_value_reject"))
        long_td = lo <= a["tpo_val"][i] - 0.05 * atr and cl > a["tpo_val"][i] and cl >= mid and d_ratio <= -0.15
        short_td = hi >= a["tpo_vah"][i] + 0.05 * atr and cl < a["tpo_vah"][i] and cl <= mid and d_ratio >= 0.15
        if long_td:
            out["TPO_DELTA"].append(_candidate(i, i + 1, "long", f, day, "tpo_lower_excess_negative_delta"))
        elif short_td:
            out["TPO_DELTA"].append(_candidate(i, i + 1, "short", f, day, "tpo_upper_excess_positive_delta"))
        val_ok = abs(a["vp_val"][i] - a["tpo_val"][i]) <= 0.15 * atr
        vah_ok = abs(a["vp_vah"][i] - a["tpo_vah"][i]) <= 0.15 * atr
        long_combo = val_ok and lo <= min(a["vp_val"][i], a["tpo_val"][i]) - 0.05 * atr and cl > max(a["vp_val"][i], a["tpo_val"][i]) and cl >= mid and d_ratio <= -0.15
        short_combo = vah_ok and hi >= max(a["vp_vah"][i], a["tpo_vah"][i]) + 0.05 * atr and cl < min(a["vp_vah"][i], a["tpo_vah"][i]) and cl <= mid and d_ratio >= 0.15
        if not (long_combo or short_combo):
            continue
        side = "long" if long_combo else "short"
        for j in range(i + 1, min(i + 7, n - 1)):
            if ts[j].floor("D") != ts[i].floor("D"):
                break
            prior_high = np.max(highs[max(0, j - 3):j])
            prior_low = np.min(lows[max(0, j - 3):j])
            if side == "long" and closes[j] > prior_high:
                out["VP_TPO_DELTA_MSS"].append(_candidate(i, j + 1, side, f, day, "vp_tpo_confluence_delta_absorption_mss", signal_i=j))
                break
            if side == "short" and closes[j] < prior_low:
                out["VP_TPO_DELTA_MSS"].append(_candidate(i, j + 1, side, f, day, "vp_tpo_confluence_delta_absorption_mss", signal_i=j))
                break
    for model in out:
        out[model].sort(key=lambda x: x["entry_i"])
    return out


def funding_safe_last_index(index: pd.DatetimeIndex, entry_i: int) -> int:
    t = index[entry_i]
    next_hour = ((t.hour // 8) + 1) * 8
    boundary = t.floor("D") + pd.Timedelta(hours=next_hour)
    if next_hour >= 24:
        boundary += pd.Timedelta(days=1)
    return min(entry_i + MAX_HOLD_BARS - 1, int(index.searchsorted(boundary, side="left") - 1))


def simulate_trade(f: pd.DataFrame, c: dict, target_r: float, cost_bps: float, split_start_i: int, split_end_i: int) -> dict | None:
    ei = int(c["entry_i"])
    # Signal, rejection and entry must all belong to this chronological split.
    for key in ("reject_i", "signal_i", "entry_i"):
        event_i = int(c[key])
        if event_i < split_start_i or event_i >= split_end_i or event_i >= len(f):
            return None
    entry, stop, side = float(f.open.iloc[ei]), float(c["stop"]), c["side"]
    direction = 1.0 if side == "long" else -1.0
    risk = entry - stop if side == "long" else stop - entry
    atr = float(c["atr_at_rejection"])
    if not np.isfinite(risk) or risk <= 0:
        return None
    target = entry + direction * target_r * risk
    last = funding_safe_last_index(f.index, ei)
    if last < ei:
        return None
    exit_price = exit_i = reason = None
    for j in range(ei, last + 1):
        if j > ei and f.index[j] - f.index[j - 1] != BAR:
            return None  # unresolved path across a missing 5m candle is excluded
        o, hi, lo, cl = map(float, (f.open.iloc[j], f.high.iloc[j], f.low.iloc[j], f.close.iloc[j]))
        if side == "long":
            if o <= stop: exit_price, reason = o, "SL_GAP"
            elif o >= target: exit_price, reason = target, "TP_GAP"
            else:
                sh, th = lo <= stop, hi >= target
                if sh and th: exit_price, reason = stop, "SL_AMBIGUOUS_STOP_FIRST"
                elif sh: exit_price, reason = stop, "SL"
                elif th: exit_price, reason = target, "TP"
        else:
            if o >= stop: exit_price, reason = o, "SL_GAP"
            elif o <= target: exit_price, reason = target, "TP_GAP"
            else:
                sh, th = hi >= stop, lo <= target
                if sh and th: exit_price, reason = stop, "SL_AMBIGUOUS_STOP_FIRST"
                elif sh: exit_price, reason = stop, "SL"
                elif th: exit_price, reason = target, "TP"
        if reason:
            exit_i = j
            break
        if j == last:
            exit_price, exit_i, reason = cl, j, "TIME_FUNDING_OR_4H"
    if exit_price is None or exit_i is None or exit_i >= split_end_i:
        # Do not truncate an open trade at a split boundary; exclude the entire trade.
        return None
    gross_r = direction * (float(exit_price) - entry) / risk
    cost_r = (entry + float(exit_price)) * (cost_bps / 10000.0) / risk
    return {"entry_time": f.index[ei].isoformat(), "exit_time": f.index[exit_i].isoformat(),
            "side": side, "setup": c["setup"], "day": c["day"], "entry": entry, "stop": stop,
            "target": target, "exit": float(exit_price), "risk_points": risk, "target_r": target_r,
            "exit_reason": reason, "gross_r": gross_r, "cost_r": cost_r, "net_r": gross_r - cost_r,
            "holding_bars": int(exit_i - ei + 1), "regime_1h": str(f.regime_1h.iloc[ei]),
            "reject_time": f.index[int(c["reject_i"])].isoformat(), "mss_time": f.index[int(c["signal_i"])].isoformat()}


def execute_candidates(f: pd.DataFrame, candidates: list[dict], target_r: float, cost_bps: float,
                       split_start_i: int, split_end_i: int) -> list[dict]:
    trades, busy_until, used_day_side = [], split_start_i - 1, set()
    for c in candidates:
        ei = int(c["entry_i"])
        if ei <= busy_until or ei < split_start_i or ei >= split_end_i:
            continue
        key = (c["day"], c["side"])
        if key in used_day_side:
            continue
        trade = simulate_trade(f, c, target_r, cost_bps, split_start_i, split_end_i)
        if trade is None:
            continue
        trades.append(trade)
        busy_until = int(f.index.get_loc(pd.Timestamp(trade["exit_time"])))
        used_day_side.add(key)
    return trades


def trade_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0, "win_rate_pct": None, "profit_factor": None, "net_r": 0.0,
                "avg_net_r": None, "max_drawdown_r": 0.0, "max_losing_streak": 0, "longs": 0, "shorts": 0,
                "tp_exits": 0, "sl_exits": 0, "time_exits": 0, "positive_active_months_pct": None, "active_months": 0}
    t = pd.DataFrame(trades)
    r = t.net_r.to_numpy(float)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    pf = float(wins / losses) if losses > 0 else None
    equity = np.cumsum(r)
    drawdown = equity - np.maximum.accumulate(np.r_[0.0, equity])[1:]
    streak = maximum_streak = 0
    for x in r:
        if x <= 0:
            streak += 1
            maximum_streak = max(maximum_streak, streak)
        else:
            streak = 0
    t["month"] = pd.to_datetime(t.entry_time, utc=True).dt.strftime("%Y-%m")
    monthly = t.groupby("month").net_r.sum()
    return {"trades": int(len(t)), "win_rate_pct": float((r > 0).mean() * 100), "profit_factor": pf,
            "net_r": float(r.sum()), "avg_net_r": float(r.mean()), "max_drawdown_r": float(drawdown.min()),
            "max_losing_streak": int(maximum_streak), "longs": int((t.side == "long").sum()),
            "shorts": int((t.side == "short").sum()), "tp_exits": int(t.exit_reason.str.startswith("TP").sum()),
            "sl_exits": int(t.exit_reason.str.startswith("SL").sum()), "time_exits": int(t.exit_reason.str.startswith("TIME").sum()),
            "positive_active_months_pct": float((monthly > 0).mean() * 100), "active_months": int(len(monthly))}


def make_splits(index: pd.DatetimeIndex) -> dict[str, tuple[int, int, str, str]]:
    days = pd.Index(index.floor("D").unique()).sort_values()
    if len(days) < 30:
        raise RuntimeError(f"Need at least 30 calendar days; only {len(days)} available")
    n = len(days)
    d1, d2 = max(1, int(math.floor(n * 0.70))), max(2, int(math.floor(n * 0.85)))
    d2 = min(max(d1 + 1, d2), n - 1)
    bounds = [("development", days[0], days[d1]), ("validation", days[d1], days[d2]),
              ("out_of_sample", days[d2], days[-1] + pd.Timedelta(days=1))]
    result = {}
    for name, start_day, end_day in bounds:
        result[name] = (int(index.searchsorted(start_day)), int(index.searchsorted(end_day)),
                        start_day.isoformat(), end_day.isoformat())
    return result


def run_research(label: str, data: pd.DataFrame, data_meta: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    f, feature_meta = add_features(data)
    candidates, splits = build_candidates(f), make_splits(f.index)
    metrics_rows, trade_rows = [], []
    candidate_counts = {k: len(v) for k, v in candidates.items()}
    for model, cand in candidates.items():
        for split_name, (start_i, end_i, start_day, end_day) in splits.items():
            for target_r in TARGETS_R:
                for cost_bps in COSTS_BPS:
                    trades = execute_candidates(f, cand, target_r, cost_bps, start_i, end_i)
                    metrics_rows.append({"symbol": label, "model": model, "split": split_name,
                                         "target_r": target_r, "round_trip_cost_bps": cost_bps,
                                         "split_start_utc": start_day, "split_end_utc_exclusive": end_day,
                                         **trade_metrics(trades)})
                    if target_r == 2.0 and cost_bps == 10:
                        trade_rows.extend({"symbol": label, "model": model, "split": split_name, **x} for x in trades)
    limitations = [
        "Volume Profile is a 48-bin candle-volume allocation proxy, not exchange-native trade-by-price volume.",
        "TPO counts 5-minute candles whose high-low ranges intersect each price bin; this is 5m time-at-price, not standard 30m letter TPO.",
        "Delta is exact taker-buy minus taker-sell base volume aggregated per 5m Binance futures candle, but not delta-at-price or footprint-level absorption.",
        "Absorption uses opposing bar-level delta with rejection/close-location; it is a proxy, not proof of resting liquidity.",
        "Fees are sensitivities only; spread, slippage, market impact and funding cashflows are not modeled. Positions close before 8h funding boundaries."
    ]
    meta = {"symbol": label, "data": data_meta, "features": feature_meta, "candidate_counts": candidate_counts,
            "splits": {k: {"start_i": v[0], "end_i_exclusive": v[1], "start_utc": v[2], "end_utc_exclusive": v[3]} for k, v in splits.items()},
            "primary_metrics": "2R target, 10 bps assumed round-trip cost", "targets_r": TARGETS_R,
            "cost_sensitivity_bps": COSTS_BPS, "data_limitations": limitations}
    return pd.DataFrame(metrics_rows), pd.DataFrame(trade_rows), meta


def fmt(x, digits=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{digits}f}"


def write_outputs(metrics: pd.DataFrame, trades: pd.DataFrame, metas: dict, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(outdir / "metrics.csv", index=False)
    trades.to_csv(outdir / "trades_2R_10bps.csv", index=False)
    if not trades.empty:
        tt = trades.copy()
        tt["month"] = pd.to_datetime(tt.entry_time, utc=True).dt.strftime("%Y-%m")
        tt.groupby(["symbol", "model", "split", "month"], as_index=False).agg(
            trades=("net_r", "size"), net_r=("net_r", "sum"), avg_net_r=("net_r", "mean"),
            wins=("net_r", lambda x: int((x > 0).sum())), losses=("net_r", lambda x: int((x <= 0).sum()))
        ).to_csv(outdir / "monthly_pnl.csv", index=False)
        tt.groupby(["symbol", "model", "split", "regime_1h"], as_index=False).agg(
            trades=("net_r", "size"), net_r=("net_r", "sum"), avg_net_r=("net_r", "mean"),
            win_rate_pct=("net_r", lambda x: float((x > 0).mean() * 100))
        ).to_csv(outdir / "regime_attribution.csv", index=False)
    else:
        pd.DataFrame().to_csv(outdir / "monthly_pnl.csv", index=False)
        pd.DataFrame().to_csv(outdir / "regime_attribution.csv", index=False)
    (outdir / "metadata.json").write_text(json.dumps(metas, indent=2, default=str), encoding="utf-8")
    primary = metrics[(metrics.target_r == 2.0) & (metrics.round_trip_cost_bps == 10)]
    lines = [
        "# BTC & ETH Order-Flow Zone Research — Backtest Results", "",
        f"Generated UTC: {pd.Timestamp.now(tz='UTC').isoformat()}", "",
        "## Scope and data integrity", "",
        "Data: Binance USD-M perpetual 5-minute klines for BTCUSDT and ETHUSDT. Two years requested; current incomplete candle excluded.",
        "Chronological split: 70% development / 15% validation / 15% historical OOS partition by UTC calendar day. The same OOS partition was already inspected in V1; V2 OOS is descriptive only, not a fresh holdout.",
        "Primary comparison: fixed 2R target, assumed 10 bps round-trip cost. Full 1.5R/2R/3R and 4/7/10/20 bps sensitivity is in metrics.csv.",
        "A trade is counted only when its full lifecycle ends inside its assigned split. One open position and at most one trade per side per UTC day per model.", "",
        "## Strategy definitions", "",
        "- **VP_ONLY:** prior complete UTC day's 70% volume-value edge rejection; 5m candle volume is allocated across 48 price bins.",
        "- **TPO_DELTA:** prior complete UTC day's 70% TPO-value edge rejection plus opposing aggressive 5m delta.",
        "- **VP_TPO_DELTA_MSS:** VP/TPO boundary confluence (within 0.15 prior ATR), opposing delta, then a later 5m close through the preceding 3-bar swing; entry next bar open.",
        "Stops are beyond the rejection candle extreme by 0.10 prior ATR; max hold four hours; stop wins ambiguous same-bar stop/target touches.", "",
        "## Primary comparison: 2R / 10 bps round trip", "",
        "| Asset | Model | Split | Trades | Win % | PF | Net R | Max DD R | Max loss streak | Positive active months |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"
    ]
    for _, r in primary.iterrows():
        lines.append(f"| {r.symbol} | {r.model} | {r.split} | {int(r.trades)} | {fmt(r.win_rate_pct)} | {fmt(r.profit_factor)} | {fmt(r.net_r)} | {fmt(r.max_drawdown_r)} | {int(r.max_losing_streak)} | {fmt(r.positive_active_months_pct)}% |")
    lines += ["", "## Data quality and model limitations", ""]
    for sym, meta in metas.items():
        dm, fm = meta["data"], meta["features"]
        lines.append(f"- **{sym}:** {dm['rows']:,} valid bars, {dm['start_utc']} to {dm['end_utc']}; {dm['gap_count']} timestamp gaps; {fm['complete_prior_utc_days']} complete UTC profile days; {fm['bars_without_prior_profile']:,} bars without prior-day profile.")
        lines.extend([f"  - {x}" for x in meta["data_limitations"]])
    lines += ["", "## Interpretation guardrails", "",
              "This is a proxy-based study, not a true tick-level footprint backtest. VP and TPO are not trade-by-price, and Delta is bar-aggregated. Do not describe it as a full footprint model.",
              "OOS is reported once as a final diagnostic and must not be used for tuning. No production rules or live alerts are modified by this experiment.", ""]
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def self_test() -> None:
    edges = np.arange(5, dtype=float)
    val, vah, poc = value_area(np.array([1., 4., 4., 1.]), edges)
    assert poc == 1.5 and val == 1.0 and vah == 3.0, (val, vah, poc)
    ix = pd.date_range("2025-01-01", periods=288, freq="5min", tz="UTC")
    one = pd.DataFrame({"open": 100., "high": 102., "low": 99., "close": 101., "volume": 10., "taker_buy_base": 6., "trade_count": 1}, index=ix)
    vp, tpo = build_day_profile(one)
    assert abs(vp.total_volume - 2880.) < 1e-7 and tpo.total_tpo > 0 and vp.val <= vp.poc <= vp.vah
    two = pd.concat([one, one.set_axis(pd.date_range("2025-01-02", periods=288, freq="5min", tz="UTC"))])
    feat, meta = add_features(two)
    assert feat.vp_val.iloc[:288].isna().all() and feat.vp_val.iloc[288:].notna().all() and meta["complete_prior_utc_days"] == 2
    ix2 = pd.date_range("2025-01-01 04:00", periods=120, freq="5min", tz="UTC")
    assert ix2[funding_safe_last_index(ix2, 40)].strftime("%H:%M") == "07:55"
    fx = pd.DataFrame({"open": [100., 100.], "high": [101., 103.], "low": [99., 97.], "close": [100., 100.],
                       "regime_1h": ["neutral", "neutral"]}, index=pd.date_range("2025-01-01", periods=2, freq="5min", tz="UTC"))
    cand = {"entry_i": 1, "stop": 98., "side": "long", "atr_at_rejection": 3., "day": "2025-01-01", "setup": "test", "reject_i": 0, "signal_i": 0}
    trade = simulate_trade(fx, cand, 1.0, 0, 0, 2)
    assert trade and trade["exit_reason"] == "SL_AMBIGUOUS_STOP_FIRST" and trade["gross_r"] == -1.0
    # Canonical Wilder seed: a constant 2-point true range yields ATR=2 after 14 bars.
    atr_ix = pd.date_range("2025-02-01", periods=20, freq="5min", tz="UTC")
    atr_frame = pd.DataFrame({"open":100.,"high":101.,"low":99.,"close":100.}, index=atr_ix)
    atr_prior = wilder_atr_prior(atr_frame, 14)
    assert abs(float(atr_prior.iloc[14]) - 2.0) < 1e-12
    # A signal/rejection created before the split cannot be carried into the next split.
    split_ix = pd.date_range("2025-02-02 23:45", periods=8, freq="5min", tz="UTC")
    split_frame = pd.DataFrame({"open":100.,"high":101.,"low":99.,"close":100.,"regime_1h":"neutral"}, index=split_ix)
    cross_candidate = {"entry_i":3,"reject_i":2,"signal_i":2,"stop":98.,"side":"long","atr_at_rejection":2.,"day":"2025-02-02","setup":"split_test"}
    assert simulate_trade(split_frame, cross_candidate, 2.0, 0.0, 3, 8) is None
    # A trade whose target is reached only after split end is excluded, not time-exited at the boundary.
    exit_ix = pd.date_range("2025-02-02 02:00", periods=8, freq="5min", tz="UTC")
    exit_frame = pd.DataFrame({"open":100.,"high":101.,"low":99.,"close":100.,"regime_1h":"neutral"}, index=exit_ix)
    cross_candidate = {"entry_i":0,"reject_i":0,"signal_i":0,"stop":98.,"side":"long","atr_at_rejection":2.,"day":"2025-02-02","setup":"split_exit_test"}
    exit_frame.loc[exit_ix[3],"high"] = 105.
    assert simulate_trade(exit_frame, cross_candidate, 2.0, 0.0, 0, 3) is None
    idx3 = pd.date_range("2024-01-01", periods=120 * 288, freq="5min", tz="UTC")
    splits = make_splits(idx3)
    assert splits["development"][1] == splits["validation"][0] and splits["validation"][1] == splits["out_of_sample"][0]
    print("SELF-TEST PASS: value-area tie break, profile conservation, prior-day-only levels, canonical Wilder ATR seed, funding cutoff, stop-first ambiguity, split-event isolation, no split-boundary truncation, chronological split")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=2)
    p.add_argument("--data-dir", type=Path, default=Path("results/orderflow-profile/data"))
    p.add_argument("--output-dir", type=Path, default=Path("results/orderflow-profile/report"))
    p.add_argument("--request-delay", type=float, default=0.15)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.years < 1 or args.years > 5:
        raise ValueError("--years must be between 1 and 5")
    all_m, all_t, metas = [], [], {}
    for label, symbol in SYMBOLS.items():
        print(f"Downloading {label} ({symbol}) 5m futures candles...", flush=True)
        data, dm = download_symbol(symbol, args.years, args.data_dir, args.request_delay)
        print(f"{label}: {len(data):,} valid bars; constructing profiles and signals...", flush=True)
        m, t, meta = run_research(label, data, dm)
        all_m.append(m)
        if not t.empty:
            all_t.append(t)
        metas[label] = meta
        print(f"{label} complete. Candidate counts: {meta['candidate_counts']}", flush=True)
    metrics = pd.concat(all_m, ignore_index=True)
    trades = pd.concat(all_t, ignore_index=True) if all_t else pd.DataFrame()
    write_outputs(metrics, trades, metas, args.output_dir)
    print((args.output_dir / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
