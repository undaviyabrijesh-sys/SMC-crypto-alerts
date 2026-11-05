"""Probe Delta's public historical FUNDING, MARK and OI candle series.

This is a small connectivity/schema check, not a persistent archive or a
backtest. Funding values may be negative; never coerce them to positive prices.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config as C

BASE_URL = "https://api.india.delta.exchange"
ENDPOINT = "/v2/history/candles"
SERIES = {
    "funding": ("FUNDING:", "1h", True),
    "mark": ("MARK:", "5m", False),
    "open_interest": ("OI:", "1h", False),
}


def validate_payload(payload, label, *, allow_negative):
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError(f"{label}: unsuccessful API response")
    records = payload.get("result")
    if not isinstance(records, list):
        raise ValueError(f"{label}: result must be a list")
    if not records:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                            index=pd.DatetimeIndex([], tz="UTC", name="timestamp"))
    frame = pd.DataFrame(records)
    required = {"time", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{label}: missing fields {sorted(missing)}")
    stamps = pd.to_numeric(frame["time"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(stamps).all() or not np.equal(stamps, np.floor(stamps)).all():
        raise ValueError(f"{label}: invalid timestamps")
    for col in ("open", "high", "low", "close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "volume" not in frame:
        frame["volume"] = 0.0
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    values = frame[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{label}: non-finite values")
    prices = frame[["open", "high", "low", "close"]]
    if not allow_negative and (prices <= 0).any().any():
        raise ValueError(f"{label}: non-positive values are invalid")
    if (frame["volume"] < 0).any():
        raise ValueError(f"{label}: negative volume")
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise ValueError(f"{label}: invalid OHLC rows={int(invalid.sum())}")
    frame.index = pd.to_datetime(stamps.astype("int64"), unit="s", utc=True)
    frame.index.name = "timestamp"
    if frame.index.has_duplicates:
        raise ValueError(f"{label}: duplicate timestamps")
    frame = frame.sort_index()[["open", "high", "low", "close", "volume"]]
    return frame


def probe(session, symbol, series_name, start_epoch, end_epoch):
    prefix, timeframe, allow_negative = SERIES[series_name]
    label = f"{series_name}:{symbol}"
    response = session.get(
        f"{BASE_URL}{ENDPOINT}",
        params={
            "resolution": timeframe,
            "symbol": f"{prefix}{C.SYMBOLS[symbol]['delta_symbol']}",
            "start": str(int(start_epoch)),
            "end": str(int(end_epoch)),
        },
        headers={"Accept": "application/json", "User-Agent": "SaltyQuantDerivativesProbe/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    frame = validate_payload(response.json(), label, allow_negative=allow_negative)
    sample = frame.tail(3).reset_index()
    if not sample.empty:
        sample["timestamp"] = sample["timestamp"].astype(str)
    return {
        "series": series_name,
        "symbol_alias": symbol,
        "contract_symbol": C.SYMBOLS[symbol]["delta_symbol"],
        "api_symbol": f"{prefix}{C.SYMBOLS[symbol]['delta_symbol']}",
        "timeframe": timeframe,
        "allow_negative_values": allow_negative,
        "row_count": int(len(frame)),
        "first_timestamp_utc": frame.index[0].isoformat() if len(frame) else None,
        "last_timestamp_utc": frame.index[-1].isoformat() if len(frame) else None,
        "sample": sample.to_dict(orient="records"),
        "status": "available" if len(frame) else "empty",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=3.0)
    parser.add_argument("--output", default="derivatives_history_pilot.json")
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args(argv)
    if not math.isfinite(args.days) or not 0 < args.days <= 30:
        raise SystemExit("--days must be greater than 0 and at most 30")
    if not math.isfinite(args.delay) or args.delay < 0:
        raise SystemExit("--delay must be finite and non-negative")
    end = int(pd.Timestamp.now(tz="UTC").timestamp())
    start = end - int(args.days * 86400)
    session = requests.Session()
    results = []
    try:
        for symbol in C.SYMBOLS:
            for series_name in SERIES:
                item = probe(session, symbol, series_name, start, end)
                results.append(item)
                print(f"{item['api_symbol']} {item['timeframe']}: "
                      f"{item['row_count']} candles ({item['status']})")
                if args.delay:
                    time.sleep(args.delay)
    finally:
        session.close()
    output = {
        "source": "Delta Exchange India public GET /v2/history/candles",
        "requested_days": args.days,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "results": results,
    }
    Path(args.output).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(f"Report: {args.output}")
    if not any(item["status"] == "available" for item in results):
        raise SystemExit("All derivatives history series returned empty data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
