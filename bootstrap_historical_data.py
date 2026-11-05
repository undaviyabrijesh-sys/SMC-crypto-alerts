"""Resumable historical OHLCV archive builder for Delta Exchange India.

Downloads public traded-price candles only. It does not access account data or place orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import requests

import config as C

BASE_URL = "https://api.india.delta.exchange"
CANDLES_PATH = "/v2/history/candles"
USER_AGENT = "SaltyQuantHistoricalResearch/1.0"
TIMEFRAME_SECONDS = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}
DEFAULT_TIMEFRAMES = tuple(TIMEFRAME_SECONDS)
MAX_API_CANDLES = 2000
REQUEST_TIMEOUT_SECONDS = 30


class HistoricalDataError(RuntimeError):
    """Raised when an archive request or its returned data is unsafe to use."""


def to_utc_timestamp(value) -> pd.Timestamp:
    """Parse a timestamp as UTC; naive values are interpreted as UTC."""
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError("timestamp must be valid")
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def build_chunks(start_epoch: int, end_epoch: int, step_seconds: int,
                 max_candles: int = MAX_API_CANDLES):
    """Yield inclusive, adjacent query windows with no more than max_candles slots."""
    if int(end_epoch) <= int(start_epoch):
        raise ValueError("end must be later than start")
    if step_seconds <= 0:
        raise ValueError("step_seconds must be positive")
    if not 1 <= int(max_candles) <= MAX_API_CANDLES:
        raise ValueError(f"max_candles must be between 1 and {MAX_API_CANDLES}")

    cursor = int(start_epoch)
    end_exclusive = int(end_epoch)
    span = step_seconds * int(max_candles) - 1
    while cursor < end_exclusive:
        chunk_end = min(end_exclusive - 1, cursor + span)
        yield cursor, chunk_end
        cursor = chunk_end + 1


def parse_candle_payload(payload: dict, symbol: str, timeframe: str,
                         start_epoch: int, end_epoch: int,
                         max_candles: int = MAX_API_CANDLES) -> pd.DataFrame:
    """Parse and strictly validate one Delta historical-candle response."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise HistoricalDataError(
            f"Delta returned an unsuccessful candle response for {symbol} {timeframe}"
        )
    records = payload.get("result")
    if records is None:
        records = []
    if not isinstance(records, list):
        raise HistoricalDataError("Delta candle result must be a list")
    if len(records) > max_candles:
        raise HistoricalDataError(
            f"Delta returned {len(records)} candles; request cap is {max_candles}"
        )
    if not records:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                             index=pd.DatetimeIndex([], tz="UTC", name="timestamp"))

    raw = pd.DataFrame(records)
    required = {"time", "open", "high", "low", "close"}
    missing = required.difference(raw.columns)
    if missing:
        raise HistoricalDataError(f"Delta candle response missing fields: {sorted(missing)}")

    timestamps = pd.to_numeric(raw["time"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(timestamps).all():
        raise HistoricalDataError("Delta returned invalid candle timestamps")
    if not np.equal(timestamps, np.floor(timestamps)).all():
        raise HistoricalDataError("Delta returned fractional-second candle timestamps")

    for column in ("open", "high", "low", "close"):
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    if "volume" not in raw:
        raw["volume"] = 0.0
        missing_volume_rows = len(raw)
    else:
        missing_volume_rows = int(raw["volume"].isna().sum())
        raw["volume"] = pd.to_numeric(raw["volume"], errors="coerce").fillna(0.0)

    numeric = raw[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise HistoricalDataError("Delta returned non-finite OHLCV values")
    prices = raw[["open", "high", "low", "close"]]
    if (prices <= 0).any().any():
        raise HistoricalDataError("Delta returned non-positive OHLC prices")
    invalid_ohlc = (
        (raw["high"] < raw[["open", "close", "low"]].max(axis=1))
        | (raw["low"] > raw[["open", "close", "high"]].min(axis=1))
    )
    if invalid_ohlc.any():
        raise HistoricalDataError(
            f"Delta returned {int(invalid_ohlc.sum())} invalid OHLC candle(s)"
        )
    if (raw["volume"] < 0).any():
        raise HistoricalDataError("Delta returned negative volume")

    index = pd.to_datetime(timestamps.astype("int64"), unit="s", utc=True)
    frame = raw[["open", "high", "low", "close", "volume"]].copy()
    frame.index = pd.DatetimeIndex(index, name="timestamp")
    start = pd.to_datetime(int(start_epoch), unit="s", utc=True)
    end = pd.to_datetime(int(end_epoch), unit="s", utc=True)
    frame = frame[(frame.index >= start) & (frame.index <= end)]
    frame.attrs["missing_volume_rows"] = missing_volume_rows
    return frame


def fetch_chunk(session: requests.Session, symbol: str, timeframe: str,
                start_epoch: int, end_epoch: int, *,
                max_candles: int = MAX_API_CANDLES,
                retries: int = 5,
                timeout: int = REQUEST_TIMEOUT_SECONDS,
                sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame:
    """Fetch one bounded public API window with conservative retry/backoff."""
    if retries < 0:
        raise ValueError("retries cannot be negative")
    params = {
        "resolution": timeframe,
        "symbol": symbol,
        "start": str(int(start_epoch)),
        "end": str(int(end_epoch)),
    }
    url = f"{BASE_URL}{CANDLES_PATH}"
    for attempt in range(retries + 1):
        try:
            response = session.get(
                url,
                params=params,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                timeout=timeout,
            )
            status = int(getattr(response, "status_code", 200))
            if status == 429 or status >= 500:
                if attempt >= retries:
                    response.raise_for_status()
                retry_after = getattr(response, "headers", {}).get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else 0.0
                except (TypeError, ValueError):
                    delay = 0.0
                sleep(min(30.0, max(delay, 0.5 * (2 ** attempt))))
                continue
            response.raise_for_status()
            payload = response.json()
            return parse_candle_payload(
                payload, symbol, timeframe, start_epoch, end_epoch, max_candles
            )
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status != 429 and status < 500:
                raise
            if attempt >= retries:
                raise
            sleep(min(30.0, 0.5 * (2 ** attempt)))
    raise HistoricalDataError(f"Exhausted retries for {symbol} {timeframe}")


def atomic_write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)


def atomic_write_csv(frame: pd.DataFrame, path: Path, *,
                     index: bool = True, index_label: str = "timestamp"):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    frame.to_csv(
        temp_path, index=index, index_label=index_label if index else None,
        float_format="%.10g",
    )
    os.replace(temp_path, path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_progress(path: Path, expected: dict):
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if all(state.get(key) == value for key, value in expected.items()):
            next_start = state.get("next_start")
            counters = ("request_count", "empty_chunk_count", "missing_volume_rows")
            if (isinstance(next_start, int)
                    and expected["start_epoch"] <= next_start <= expected["end_epoch"]
                    and all(isinstance(state.get(key), int) and state[key] >= 0
                            for key in counters)):
                return state
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _read_chunk_files(work_dir: Path):
    frames = []
    for path in sorted(work_dir.glob("chunk_*.csv")):
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        if not frame.empty:
            frame.index = pd.to_datetime(frame.index, utc=True)
            frames.append(frame[["open", "high", "low", "close", "volume"]])
    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                            index=pd.DatetimeIndex([], tz="UTC", name="timestamp"))
    return pd.concat(frames)


def _coverage_metrics(frame: pd.DataFrame, step_seconds: int,
                      requested_start_epoch: int, requested_end_epoch: int):
    count = int(len(frame))
    requested_expected = max(
        1, int(np.ceil((requested_end_epoch - requested_start_epoch) / step_seconds))
    )
    requested_coverage = round(100.0 * count / requested_expected, 4)
    if count == 0:
        return {
            "requested_expected_candles": requested_expected,
            "requested_coverage_pct": requested_coverage,
            "expected_candles_in_observed_span": 0,
            "missing_expected_candles": 0,
            "gap_count": 0,
            "largest_gap_seconds": 0,
            "observed_coverage_pct": 0.0,
        }
    deltas = frame.index.to_series().diff().dropna().dt.total_seconds()
    expected = int(round((frame.index[-1] - frame.index[0]).total_seconds()
                         / step_seconds)) + 1
    missing = max(0, expected - count)
    gaps = deltas[deltas > step_seconds * 1.5]
    largest_gap = int(deltas.max()) if not deltas.empty else 0
    return {
        "requested_expected_candles": requested_expected,
        "requested_coverage_pct": requested_coverage,
        "expected_candles_in_observed_span": expected,
        "missing_expected_candles": missing,
        "gap_count": int(len(gaps)),
        "largest_gap_seconds": largest_gap,
        "observed_coverage_pct": round(100.0 * count / expected, 4) if expected else 0.0,
    }


def _load_manifest(path: Path):
    if not path.exists():
        return {"schema_version": 1, "venue": "Delta Exchange India",
                "api_endpoint": CANDLES_PATH, "datasets": {}}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1 or not isinstance(manifest.get("datasets"), dict):
            raise ValueError("unsupported manifest schema")
        return manifest
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HistoricalDataError(f"Cannot safely resume: manifest is unreadable: {exc}") from exc


def _write_reports(output_dir: Path, manifest: dict):
    atomic_write_text(
        output_dir / "manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    rows = list(manifest.get("datasets", {}).values())
    if rows:
        report = pd.DataFrame(rows).sort_values(["symbol_alias", "timeframe"])
        atomic_write_csv(report, output_dir / "coverage.csv", index=False)


def download_dataset(symbol_alias: str, contract_symbol: str, timeframe: str,
                     start_epoch: int, end_epoch: int, output_dir: Path, *,
                     session: requests.Session | None = None,
                     request_delay: float = 0.2,
                     max_candles: int = MAX_API_CANDLES,
                     retries: int = 5,
                     force: bool = False,
                     sleep: Callable[[float], None] = time.sleep):
    """Download/resume one symbol/timeframe archive, then atomically publish its CSV."""
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if request_delay < 0:
        raise ValueError("request_delay cannot be negative")
    if not 1 <= max_candles <= MAX_API_CANDLES:
        raise ValueError(f"max_candles must be between 1 and {MAX_API_CANDLES}")
    step = TIMEFRAME_SECONDS[timeframe]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{symbol_alias}_{timeframe}"
    final_path = output_dir / f"{stem}.csv"
    work_dir = output_dir / ".work" / stem
    progress_path = work_dir / "progress.json"
    expected = {
        "symbol_alias": symbol_alias,
        "contract_symbol": contract_symbol,
        "timeframe": timeframe,
        "start_epoch": int(start_epoch),
        "end_epoch": int(end_epoch),
        "max_candles": int(max_candles),
    }

    manifest_path = output_dir / "manifest.json"
    manifest = _load_manifest(manifest_path)
    dataset_key = f"{symbol_alias}_{contract_symbol}_{timeframe}"
    previous = manifest.get("datasets", {}).get(dataset_key)
    if not force and final_path.exists() and previous:
        same_request = (
            previous.get("requested_start_epoch") == int(start_epoch)
            and previous.get("requested_end_epoch") == int(end_epoch)
        )
        if same_request and previous.get("sha256") == file_sha256(final_path):
            return previous

    if force and work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    progress = _read_progress(progress_path, expected)
    if progress is None:
        for stale in work_dir.glob("chunk_*.csv"):
            stale.unlink()
        progress = {**expected, "next_start": int(start_epoch),
                    "request_count": 0, "empty_chunk_count": 0,
                    "missing_volume_rows": 0}
        atomic_write_text(progress_path, json.dumps(progress, sort_keys=True) + "\n")

    client = session or requests.Session()
    owns_session = session is None
    cursor = int(progress["next_start"])
    try:
        for chunk_start, chunk_end in build_chunks(cursor, end_epoch, step, max_candles):
            frame = fetch_chunk(
                client, contract_symbol, timeframe, chunk_start, chunk_end,
                max_candles=max_candles, retries=retries, sleep=sleep,
            )
            if not frame.empty:
                chunk_path = work_dir / f"chunk_{chunk_start}_{chunk_end}.csv"
                atomic_write_csv(frame, chunk_path)
                progress["missing_volume_rows"] += int(
                    frame.attrs.get("missing_volume_rows", 0)
                )
            else:
                progress["empty_chunk_count"] += 1
            progress["request_count"] += 1
            progress["next_start"] = chunk_end + 1
            atomic_write_text(progress_path, json.dumps(progress, sort_keys=True) + "\n")
            if request_delay:
                sleep(request_delay)

        combined = _read_chunk_files(work_dir)
        if combined.empty:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise HistoricalDataError(
                f"No historical candles returned for {symbol_alias} {timeframe}; "
                "the empty checkpoint was cleared so a later retry starts cleanly"
            )
        if not isinstance(combined.index, pd.DatetimeIndex):
            combined.index = pd.to_datetime(combined.index, utc=True)
        combined.index = pd.to_datetime(combined.index, utc=True)
        combined = combined.sort_index()
        start = pd.to_datetime(int(start_epoch), unit="s", utc=True)
        end = pd.to_datetime(int(end_epoch), unit="s", utc=True)
        combined = combined[(combined.index >= start) & (combined.index < end)]
        duplicate_count = int(combined.index.duplicated(keep="last").sum())
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        if combined.empty:
            raise HistoricalDataError(f"No in-range candles for {symbol_alias} {timeframe}")

        atomic_write_csv(combined, final_path)
        metrics = _coverage_metrics(combined, step, int(start_epoch), int(end_epoch))
        metadata = {
            "dataset_key": dataset_key,
            "symbol_alias": symbol_alias,
            "contract_symbol": contract_symbol,
            "venue": "Delta Exchange India",
            "price_type": "traded_price",
            "timeframe": timeframe,
            "timeframe_seconds": step,
            "requested_start_epoch": int(start_epoch),
            "requested_end_epoch": int(end_epoch),
            "requested_start_utc": pd.to_datetime(int(start_epoch), unit="s", utc=True).isoformat(),
            "requested_end_utc_exclusive": pd.to_datetime(int(end_epoch), unit="s", utc=True).isoformat(),
            "first_candle_utc": combined.index[0].isoformat(),
            "last_candle_open_utc": combined.index[-1].isoformat(),
            "last_candle_close_utc": (combined.index[-1] + pd.Timedelta(seconds=step)).isoformat(),
            "row_count": int(len(combined)),
            "duplicate_rows_removed": duplicate_count,
            "missing_volume_rows_defaulted_to_zero": int(progress["missing_volume_rows"]),
            "request_count": int(progress["request_count"]),
            "empty_chunk_count": int(progress["empty_chunk_count"]),
            "csv_path": final_path.name,
            "sha256": file_sha256(final_path),
            **_coverage_metrics(combined, step, int(start_epoch), int(end_epoch)),
        }
        manifest.setdefault("datasets", {})[dataset_key] = metadata
        manifest["last_updated_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
        _write_reports(output_dir, manifest)
        shutil.rmtree(work_dir, ignore_errors=True)
        return metadata
    finally:
        if owns_session:
            client.close()


def bootstrap(output_dir: Path, start: pd.Timestamp, end: pd.Timestamp, *,
              symbols: list[str] | None = None,
              timeframes: list[str] | None = None,
              request_delay: float = 0.2,
              max_candles: int = MAX_API_CANDLES,
              retries: int = 5,
              force: bool = False):
    """Build all selected archives sequentially, keeping request rate conservative."""
    start = to_utc_timestamp(start)
    end = to_utc_timestamp(end)
    if end <= start:
        raise ValueError("end must be later than start")
    selected_symbols = symbols or list(C.SYMBOLS)
    selected_timeframes = timeframes or list(DEFAULT_TIMEFRAMES)
    unknown_symbols = set(selected_symbols).difference(C.SYMBOLS)
    unknown_timeframes = set(selected_timeframes).difference(TIMEFRAME_SECONDS)
    if unknown_symbols:
        raise ValueError(f"Unknown symbol aliases: {sorted(unknown_symbols)}")
    if unknown_timeframes:
        raise ValueError(f"Unknown timeframes: {sorted(unknown_timeframes)}")

    start_epoch, end_epoch = int(start.timestamp()), int(end.timestamp())
    total = len(selected_symbols) * len(selected_timeframes)
    completed = []
    for alias in selected_symbols:
        contract = C.SYMBOLS[alias]["delta_symbol"]
        for timeframe in selected_timeframes:
            print(f"Downloading {alias} ({contract}) {timeframe}...")
            result = download_dataset(
                alias, contract, timeframe, start_epoch, end_epoch, output_dir,
                request_delay=request_delay, max_candles=max_candles,
                retries=retries, force=force,
            )
            completed.append(result)
            print(
                f"  {result['row_count']} candles | coverage "
                f"{result['observed_coverage_pct']}% | gaps {result['gap_count']} | "
                f"sha256 {result['sha256'][:12]}..."
            )
    print(f"Completed {len(completed)} of {total} requested datasets.")
    print(f"Manifest: {Path(output_dir) / 'manifest.json'}")
    print(f"Coverage: {Path(output_dir) / 'coverage.csv'}")
    return completed


def build_parser():
    parser = argparse.ArgumentParser(
        description="Bootstrap resumable historical BTC/ETH/Gold OHLCV from Delta India."
    )
    parser.add_argument("--output-dir", default=os.environ.get("HISTORICAL_DATA_DIR", "historical_data"))
    parser.add_argument("--years", type=float, default=3.0,
                        help="History depth when --start is omitted (default: 3 years).")
    parser.add_argument("--start", help="UTC start date/time, e.g. 2023-11-05 or ISO-8601.")
    parser.add_argument("--end", help="UTC end date/time; defaults to current UTC time.")
    parser.add_argument("--symbols", nargs="+", choices=sorted(C.SYMBOLS),
                        default=list(C.SYMBOLS))
    parser.add_argument("--timeframes", nargs="+", choices=sorted(TIMEFRAME_SECONDS),
                        default=list(DEFAULT_TIMEFRAMES))
    parser.add_argument("--request-delay", type=float, default=0.2)
    parser.add_argument("--max-candles-per-request", type=int, default=MAX_API_CANDLES)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--force", action="store_true",
                        help="Ignore completed archives and rebuild selected datasets.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.years <= 0:
        raise SystemExit("--years must be positive")
    end = to_utc_timestamp(args.end or pd.Timestamp.now(tz="UTC"))
    start = to_utc_timestamp(args.start) if args.start else end - pd.Timedelta(days=365.25 * args.years)
    try:
        bootstrap(
            Path(args.output_dir), start, end, symbols=args.symbols,
            timeframes=args.timeframes, request_delay=args.request_delay,
            max_candles=args.max_candles_per_request, retries=args.retries,
            force=args.force,
        )
    except (ValueError, HistoricalDataError, requests.RequestException) as exc:
        raise SystemExit(f"Historical data bootstrap failed: {exc}") from exc


if __name__ == "__main__":
    main()
