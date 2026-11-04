"""Live Delta Exchange OHLCV integration smoke test. No credentials or orders required."""
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

import config as C
import data


def check_symbol(symbol, cfg, now):
    frames = data.fetch_bundle(cfg, now, symbol=symbol)
    usable, reason = data.freshness(frames, now)
    if not usable:
        raise AssertionError(f"{symbol}: production freshness check rejected the feed: {reason}")

    results = []
    for timeframe, frame in frames.items():
        if frame is None or frame.empty:
            raise AssertionError(f"{symbol} {timeframe}: no closed candles")
        if frame.index.tz is None or str(frame.index.tz) != "UTC":
            raise AssertionError(f"{symbol} {timeframe}: timestamps are not UTC-aware")
        if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
            raise AssertionError(f"{symbol} {timeframe}: timestamps are not unique and sorted")
        if (frame.index + pd.Timedelta(minutes=data.MINUTES[timeframe]) > now).any():
            raise AssertionError(f"{symbol} {timeframe}: forming/future candle passed the closed-bar filter")
        invalid = (
            (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
            | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
            | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
        )
        if invalid.any():
            raise AssertionError(f"{symbol} {timeframe}: {int(invalid.sum())} OHLC invariant violations")
        close_time = frame.index[-1] + pd.Timedelta(minutes=data.MINUTES[timeframe])
        age = (now - close_time).total_seconds() / 60
        results.append({
            "symbol": symbol,
            "contract": cfg["delta_symbol"],
            "timeframe": timeframe,
            "rows": len(frame),
            "last_close_time_utc": close_time.isoformat(),
            "age_after_close_minutes": round(age, 1),
            "last_close": float(frame["close"].iloc[-1])
        })
    return results


def main():
    now = pd.Timestamp.now(tz="UTC")
    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=len(C.SYMBOLS)) as pool:
        futures = {
            pool.submit(check_symbol, symbol, cfg, now): symbol
            for symbol, cfg in C.SYMBOLS.items()
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results.extend(future.result())
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")

    for row in sorted(results, key=lambda x: (x["symbol"], data.MINUTES[x["timeframe"]])):
        print(
            f"PASS {row['symbol']} {row['contract']} {row['timeframe']}: "
            f"{row['rows']} closed candles; latest close {row['last_close']}; "
            f"last candle closed {row['age_after_close_minutes']} min ago"
        )
    if errors:
        for error in errors:
            print("FAIL " + error)
        raise SystemExit(f"Delta production-feed smoke test failed: {len(errors)} of {len(C.SYMBOLS)} symbols failed")
    print(f"PASS: production closed-bar and freshness checks passed for all {len(results)} symbol/timeframe combinations.")


if __name__ == "__main__":
    main()
