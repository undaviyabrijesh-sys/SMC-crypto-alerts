"""OHLCV ingestion and rolling raw-data store for the visual analysis pipeline."""
from pathlib import Path
import os

import pandas as pd

DATA_DIR = Path(os.environ.get("DATA_DIR", "market_data"))
PERIODS = {"5m": "5d", "15m": "60d", "1h": "60d", "1d": "1y"}
MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
MAX_ROWS = {"5m": 5000, "15m": 6000, "1h": 6000, "4h": 4000, "1d": 3000}


def fetch(symbol: str, interval: str, period: str):
    """Fetch native OHLCV candles. Yahoo is the initial adapter; provider can be swapped later."""
    import yfinance as yf

    df = yf.download(symbol, interval=interval, period=period, progress=False,
                     auto_adjust=False, prepost=True, threads=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    required = ["open", "high", "low", "close"]
    if not all(col in df.columns for col in required):
        raise ValueError(f"OHLC columns missing for {symbol} {interval}")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df = df[required + ["volume"]].apply(pd.to_numeric, errors="coerce").dropna(subset=required)
    df.index = pd.to_datetime(df.index, utc=True)
    return normalize(df)


def normalize(df):
    if df is None or df.empty:
        return None
    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True)
    elif out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    out.index.name = "timestamp"
    out = out[~out.index.duplicated(keep="last")].sort_index()
    for col in ["open", "high", "low", "close"]:
        if col not in out:
            raise ValueError(f"Missing candle field: {col}")
    if "volume" not in out:
        out["volume"] = 0.0
    return out[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce").dropna(
        subset=["open", "high", "low", "close"]
    )


def closed_only(df, minutes: int, now):
    """A candle is usable only after its full interval has elapsed."""
    df = normalize(df) if df is not None else None
    if df is None or df.empty:
        return df
    now = pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    return df[df.index + pd.Timedelta(minutes=minutes) <= now]


def _persist(symbol, timeframe, frame):
    """Merge updates into a rolling CSV so Actions cache can carry recent raw candles between runs."""
    if frame is None or frame.empty:
        return frame
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{symbol}_{timeframe}.csv"
    parts = [frame]
    if path.exists():
        try:
            old = pd.read_csv(path, index_col=0, parse_dates=True)
            old = normalize(old)
            if old is not None and not old.empty:
                parts.insert(0, old)
        except Exception as exc:
            print(f"[warn] ignoring unreadable cache {path}: {exc}")
    merged = pd.concat(parts)
    merged = merged[~merged.index.duplicated(keep="last")].sort_index().tail(MAX_ROWS[timeframe])
    merged.to_csv(path, float_format="%.10g")
    return merged


def _resample_4h(hourly):
    if hourly is None or hourly.empty:
        return None
    rule = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = hourly.resample("4h", label="left", closed="left").agg(rule).dropna(subset=["open", "high", "low", "close"])
    return out


def fetch_bundle(cfg, now, fetcher=fetch, symbol="UNKNOWN"):
    """Fetch all native intervals, derive 4h candles, persist the rolling OHLCV history."""
    raw = {}
    for interval, period in PERIODS.items():
        try:
            raw[interval] = fetcher(cfg["yf"], interval, period)
        except Exception as exc:
            print(f"[warn] {symbol} {interval} download failed: {exc}")
            raw[interval] = None

    closed = {
        "5m": closed_only(raw.get("5m"), 5, now),
        "15m": closed_only(raw.get("15m"), 15, now),
        "1h": closed_only(raw.get("1h"), 60, now),
        "1d": closed_only(raw.get("1d"), 1440, now),
    }
    closed["4h"] = closed_only(_resample_4h(closed["1h"]), 240, now)

    stored = {}
    for tf, frame in closed.items():
        try:
            stored[tf] = _persist(symbol, tf, frame) if frame is not None and not frame.empty else frame
        except Exception as exc:
            print(f"[warn] {symbol} {tf} persistence failed: {exc}")
            stored[tf] = frame
    return stored


def freshness(frames, now):
    """Return (usable, reason). Freshness uses candle close time, not its opening timestamp."""
    now = pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    limits = {"5m": 15, "15m": 35, "1h": 150, "4h": 540, "1d": 3 * 1440}
    for tf in ["5m", "15m", "1h", "4h", "1d"]:
        frame = frames.get(tf)
        if frame is None or frame.empty:
            return False, f"missing {tf} candles"
        close_time = frame.index[-1] + pd.Timedelta(minutes=MINUTES[tf])
        age = (now - close_time).total_seconds() / 60
        if age > limits[tf]:
            return False, f"{tf} feed stale ({age:.0f} min since last close)"
        if age < -2:
            return False, f"{tf} timestamp is unexpectedly in the future"
    return True, "fresh"
