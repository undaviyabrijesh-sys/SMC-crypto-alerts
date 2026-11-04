"""Live public Delta Exchange data smoke test. Does not require credentials or place orders."""
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

import config as C
import data


def check_one(symbol, config, timeframe, period):
    frame = data.fetch(config["delta_symbol"], timeframe, period)
    if frame is None or frame.empty:
        raise AssertionError(f"{symbol} {timeframe}: API returned no OHLCV candles")
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise AssertionError(f"{symbol} {timeframe}: missing columns {required - set(frame.columns)}")
    if frame.index.tz is None or str(frame.index.tz) != "UTC":
        raise AssertionError(f"{symbol} {timeframe}: timestamps are not UTC-aware")
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise AssertionError(f"{symbol} {timeframe}: timestamps are not unique and sorted")
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    if invalid.any():
        raise AssertionError(f"{symbol} {timeframe}: {int(invalid.sum())} OHLC invariant violations")
    now = pd.Timestamp.now(tz="UTC")
    age_min = (now - (frame.index[-1] + pd.Timedelta(minutes=data.MINUTES[timeframe]))).total_seconds() / 60
    return {
        "symbol": symbol,
        "contract": config["delta_symbol"],
        "timeframe": timeframe,
        "rows": len(frame),
        "last_candle_open_utc": frame.index[-1].isoformat(),
        "age_after_close_minutes": round(age_min, 1),
        "last_close": float(frame["close"].iloc[-1])
    }


def main():
    tasks = []
    for symbol, config in C.SYMBOLS.items():
        for timeframe, period in data.PERIODS.items():
            tasks.append((symbol, config, timeframe, period))

    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(check_one, symbol, config, timeframe, period): (symbol, timeframe)
            for symbol, config, timeframe, period in tasks
        }
        for future in as_completed(futures):
            symbol, timeframe = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append(f"{symbol} {timeframe}: {exc}")

    for row in sorted(results, key=lambda x: (x["symbol"], data.MINUTES[x["timeframe"]])):
        print(
            f"PASS {row['symbol']} {row['contract']} {row['timeframe']}: "
            f"{row['rows']} candles; latest close {row['last_close']}; "
            f"closed {row['age_after_close_minutes']} min ago"
        )
    if errors:
        for error in errors:
            print("FAIL " + error)
        raise SystemExit(f"Delta feed smoke test failed: {len(errors)} of {len(tasks)} requests failed")
    print(f"PASS: Delta public OHLCV feed returned valid candles for all {len(results)} symbol/timeframe combinations.")


if __name__ == "__main__":
    main()
