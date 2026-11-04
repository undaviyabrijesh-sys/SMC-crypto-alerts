"""Delta Exchange OHLCV ingestion and rolling raw-data store for visual analysis."""
from pathlib import Path
import os

import pandas as pd
import requests

DATA_DIR = Path(os.environ.get("DATA_DIR", "market_data"))
BASE_URL = "https://api.india.delta.exchange"
HEADERS = {"Accept": "application/json", "User-Agent": "SaltyQuantAI/1.0"}
# All requested windows stay below Delta's 2,000-candle response limit.
PERIODS = {"5m": "4d", "15m": "14d", "1h": "45d", "4h": "120d", "1d": "365d"}
MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
MAX_ROWS = {"5m": 5000, "15m": 6000, "1h": 6000, "4h": 4000, "1d": 3000}


def fetch(symbol: str, interval: str, period: str):
    """Fetch public traded-price OHLCV candles from Delta Exchange; no API key is required."""
    days = int(period[:-1]) if period.endswith("d") else int(period)
    end = int(pd.Timestamp.now(tz="UTC").timestamp())
    start = end - days * 86400
    response = requests.get(
        f"{BASE_URL}/v2/history/candles",
        params={"resolution": interval, "symbol": symbol, "start": start, "end": end},
        headers=HEADERS,
        timeout=25
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("success") is not True:
        raise RuntimeError(f"Delta candle API returned an unsuccessful response for {symbol} {interval}: {payload}")
    candles = payload.get("result") or []
    if not candles:
        return None
    df = pd.DataFrame(candles)
    required = ["time", "open", "high", "low", "close"]
    if not all(col in df.columns for col in required):
        raise ValueError(f"Delta candle response missing required fields for {symbol} {interval}")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df.index = pd.to_datetime(pd.to_numeric(df.pop("time"), errors="coerce"), unit="s", utc=True)
    df = df[["open", "high", "low", "close", "volume"]]
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


def _load_stored(symbol, timeframe):
    path = DATA_DIR / f"{symbol}_{timeframe}.csv"
    if not path.exists():
        return None
    try:
        stored = pd.read_csv(path, index_col=0, parse_dates=True)
        return normalize(stored)
    except Exception as exc:
        print(f"[warn] ignoring unreadable cache {path}: {exc}")
        return None


def _persist(symbol, timeframe, frame):
    """Merge updates into a rolling CSV so Actions cache can carry recent raw candles between runs."""
    if frame is None or frame.empty:
        return _load_stored(symbol, timeframe)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{symbol}_{timeframe}.csv"
    parts = [frame]
    old = _load_stored(symbol, timeframe)
    if old is not None and not old.empty:
        parts.insert(0, old)
    merged = pd.concat(parts)
    merged = merged[~merged.index.duplicated(keep="last")].sort_index().tail(MAX_ROWS[timeframe])
    merged.to_csv(path, float_format="%.10g")
    return merged


def fetch_bundle(cfg, now, fetcher=fetch, symbol="UNKNOWN"):
    """Fetch all five native Delta resolutions and persist rolling OHLCV history."""
    instrument = cfg.get("delta_symbol") or cfg.get("yf")
    frames = {}
    for timeframe, period in PERIODS.items():
        try:
            raw = fetcher(instrument, timeframe, period)
        except Exception as exc:
            print(f"[warn] {symbol} {timeframe} Delta download failed: {exc}")
            raw = None
        frames[timeframe] = closed_only(raw, MINUTES[timeframe], now) if raw is not None else None

    for timeframe, frame in list(frames.items()):
        try:
            frames[timeframe] = _persist(symbol, timeframe, frame)
        except Exception as exc:
            print(f"[warn] {symbol} {timeframe} persistence failed: {exc}")
    return frames


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
