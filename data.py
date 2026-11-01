import pandas as pd


def fetch(symbol: str, interval: str, period: str):
    """Download OHLC from Yahoo Finance. Replace this with your own loader if you prefer."""
    import yfinance as yf  # imported lazily so tests run without it

    df = yf.download(symbol, interval=interval, period=period, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def closed_only(df, minutes: int, now):
    """Drop the still-forming last candle."""
    if df is None:
        return None
    return df[df.index <= now - pd.Timedelta(minutes=minutes)]


def is_stale(df, minutes: int, now, mult: int = 3) -> bool:
    """True when the market looks closed (weekend for gold) or the feed is behind."""
    if df is None or df.empty:
        return True
    return df.index[-1] + pd.Timedelta(minutes=minutes * mult) < now
