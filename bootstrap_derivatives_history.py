"""Resumable archive builder for Delta funding, mark-price and open-interest history.

The public endpoint stores these as historical candles using prefixed symbols:
FUNDING:<contract>, MARK:<contract>, and OI:<contract>. Funding values can be
negative; this collector preserves raw API values and does not infer their units.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
ENDPOINT = "/v2/history/candles"
USER_AGENT = "SaltyQuantDerivativesArchive/1.0"
MAX_API_CANDLES = 2000
TIMEOUT_SECONDS = 30
SERIES = {
    "funding": {
        "prefix": "FUNDING:", "timeframe": "1h",
        "seconds": 3600, "allow_negative": True, "allow_zero": True,
    },
    "mark": {
        "prefix": "MARK:", "timeframe": "5m",
        "seconds": 300, "allow_negative": False, "allow_zero": False,
    },
    "open_interest": {
        "prefix": "OI:", "timeframe": "1h",
        "seconds": 3600, "allow_negative": False, "allow_zero": True,
    },
}


class DerivativesArchiveError(RuntimeError):
    """Raised when a public derivative-history response cannot be trusted."""


def build_chunks(start_epoch: int, end_epoch: int, step_seconds: int,
                 max_candles: int = MAX_API_CANDLES):
    if end_epoch <= start_epoch:
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


def parse_payload(payload: dict, api_symbol: str, series_name: str,
                  start_epoch: int, end_epoch: int,
                  max_candles: int = MAX_API_CANDLES) -> pd.DataFrame:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise DerivativesArchiveError(f"{api_symbol}: unsuccessful response")
    records = payload.get("result")
    if records is None:
        records = []
    if not isinstance(records, list):
        raise DerivativesArchiveError(f"{api_symbol}: result must be a list")
    if len(records) > max_candles:
        raise DerivativesArchiveError(
            f"{api_symbol}: response has {len(records)} candles; cap={max_candles}"
        )
    columns = ["open", "high", "low", "close", "volume"]
    if not records:
        return pd.DataFrame(columns=columns,
            index=pd.DatetimeIndex([], tz="UTC", name="timestamp"))
    raw = pd.DataFrame(records)
    required = {"time", "open", "high", "low", "close"}
    missing = required.difference(raw.columns)
    if missing:
        raise DerivativesArchiveError(f"{api_symbol}: missing fields {sorted(missing)}")
    stamps = pd.to_numeric(raw["time"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(stamps).all() or not np.equal(stamps, np.floor(stamps)).all():
        raise DerivativesArchiveError(f"{api_symbol}: invalid timestamps")
    for col in ("open", "high", "low", "close"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    if "volume" not in raw:
        raw["volume"] = 0.0
    raw["volume"] = pd.to_numeric(raw["volume"], errors="coerce").fillna(0.0)
    values = raw[columns].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise DerivativesArchiveError(f"{api_symbol}: non-finite OHLCV values")
    spec = SERIES[series_name]
    prices = raw[["open", "high", "low", "close"]]
    if not spec["allow_negative"] and (prices < 0).any().any():
        raise DerivativesArchiveError(f"{api_symbol}: negative values are invalid")
    if not spec["allow_zero"] and (prices <= 0).any().any():
        raise DerivativesArchiveError(f"{api_symbol}: zero values are invalid")
    invalid = (
        (raw["high"] < raw[["open", "close", "low"]].max(axis=1))
        | (raw["low"] > raw[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise DerivativesArchiveError(
            f"{api_symbol}: invalid OHLC rows={int(invalid.sum())}"
        )
    if (raw["volume"] < 0).any():
        raise DerivativesArchiveError(f"{api_symbol}: negative volume")
    index = pd.to_datetime(stamps.astype("int64"), unit="s", utc=True)
    frame = raw[columns].copy()
    frame.index = pd.DatetimeIndex(index, name="timestamp")
    start = pd.to_datetime(int(start_epoch), unit="s", utc=True)
    end = pd.to_datetime(int(end_epoch), unit="s", utc=True)
    return frame[(frame.index >= start) & (frame.index <= end)]


def fetch_chunk(session: requests.Session, api_symbol: str, series_name: str,
                start_epoch: int, end_epoch: int, *, retries: int = 5,
                timeout: int = TIMEOUT_SECONDS,
                sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame:
    if retries < 0:
        raise ValueError("retries cannot be negative")
    spec = SERIES[series_name]
    params = {
        "resolution": spec["timeframe"],
        "symbol": api_symbol,
        "start": str(int(start_epoch)),
        "end": str(int(end_epoch)),
    }
    url = f"{BASE_URL}{ENDPOINT}"
    for attempt in range(retries + 1):
        try:
            response = session.get(url, params=params,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                timeout=timeout)
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
            return parse_payload(response.json(), api_symbol, series_name,
                                 start_epoch, end_epoch)
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status != 429 and status < 500:
                raise
            if attempt >= retries:
                raise
            sleep(min(30.0, 0.5 * (2 ** attempt)))
    raise DerivativesArchiveError(f"Exhausted retries for {api_symbol}")


def atomic_text(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(value, encoding="utf-8")
    os.replace(tmp, path)


def atomic_csv(frame: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    frame.to_csv(tmp, index=True, index_label="timestamp", float_format="%.12g")
    os.replace(tmp, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {
            "schema_version": 1, "venue": "Delta Exchange India",
            "api_base_url": BASE_URL, "api_endpoint": ENDPOINT,
            "series_type": "funding_mark_open_interest", "datasets": {},
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or not isinstance(value.get("datasets"), dict)):
            raise ValueError("unsupported manifest shape")
        return value
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise DerivativesArchiveError(f"Cannot safely resume: {exc}") from exc


def read_progress(path: Path, expected: dict):
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        keys = ("request_count", "empty_chunk_count")
        next_start = value.get("next_start") if isinstance(value, dict) else None
        step = SERIES[expected["series"]]["seconds"]
        aligned = (
            type(next_start) is int
            and (
                next_start == expected["end_epoch"]
                or (next_start - expected["start_epoch"]) % step == 0
            )
        )
        if (isinstance(value, dict)
                and all(value.get(k) == v for k, v in expected.items())
                and type(next_start) is int
                and expected["start_epoch"] <= next_start <= expected["end_epoch"]
                and aligned
                and all(type(value.get(k)) is int and value[k] >= 0 for k in keys)):
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return None


def coverage_metrics(frame: pd.DataFrame, step: int, start: int, end: int):
    expected = max(1, int(math.ceil((end - start) / step)))
    requested_pct = min(100.0, round(100.0 * len(frame) / expected, 4))
    if frame.empty:
        return {
            "requested_expected_candles_estimate": expected,
            "requested_coverage_pct_estimate": requested_pct,
            "expected_candles_in_observed_span": 0,
            "missing_expected_candles": 0, "gap_count": 0,
            "largest_gap_seconds": 0, "observed_coverage_pct": 0.0,
        }
    deltas = frame.index.to_series().diff().dropna().dt.total_seconds()
    observed = int(round((frame.index[-1] - frame.index[0]).total_seconds() / step)) + 1
    gaps = deltas[deltas > step * 1.5]
    return {
        "requested_expected_candles_estimate": expected,
        "requested_coverage_pct_estimate": requested_pct,
        "expected_candles_in_observed_span": observed,
        "missing_expected_candles": max(0, observed - len(frame)),
        "gap_count": int(len(gaps)),
        "largest_gap_seconds": int(gaps.max()) if not gaps.empty else 0,
        "observed_coverage_pct": round(100.0 * len(frame) / observed, 4) if observed else 0.0,
    }


def write_reports(output_dir: Path, manifest: dict):
    atomic_text(output_dir / "manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    rows = list(manifest["datasets"].values())
    if rows:
        report = pd.DataFrame(rows).sort_values(["symbol_alias", "series", "timeframe"])
        tmp = output_dir / "coverage.csv.tmp"
        report.to_csv(tmp, index=False)
        os.replace(tmp, output_dir / "coverage.csv")


def _read_chunks(work_dir: Path):
    frames = []
    for path in sorted(work_dir.glob("chunk_*.csv")):
        part = pd.read_csv(path, index_col=0, parse_dates=True)
        if not part.empty:
            part.index = pd.to_datetime(part.index, utc=True)
            frames.append(part[["open", "high", "low", "close", "volume"]])
    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                            index=pd.DatetimeIndex([], tz="UTC", name="timestamp"))
    return pd.concat(frames)


def download_dataset(symbol_alias: str, series_name: str, start_epoch: int,
                     end_epoch: int, output_dir: Path, *,
                     session: requests.Session | None = None,
                     request_delay: float = 0.25, max_candles: int = MAX_API_CANDLES,
                     retries: int = 5, force: bool = False,
                     sleep: Callable[[float], None] = time.sleep):
    if symbol_alias not in C.SYMBOLS:
        raise ValueError(f"Unknown symbol alias: {symbol_alias}")
    if series_name not in SERIES:
        raise ValueError(f"Unknown series: {series_name}")
    if not math.isfinite(float(request_delay)) or request_delay < 0:
        raise ValueError("request_delay must be finite and non-negative")
    if not 1 <= max_candles <= MAX_API_CANDLES:
        raise ValueError(f"max_candles must be between 1 and {MAX_API_CANDLES}")
    spec = SERIES[series_name]
    contract = C.SYMBOLS[symbol_alias]["delta_symbol"]
    api_symbol = f"{spec['prefix']}{contract}"
    step = spec["seconds"]
    stem = f"{symbol_alias}_{series_name}_{spec['timeframe']}"
    final = Path(output_dir) / f"{stem}.csv"
    work = Path(output_dir) / ".work" / stem
    progress_path = work / "progress.json"
    manifest_path = Path(output_dir) / "manifest.json"
    manifest = load_manifest(manifest_path)
    key = f"{symbol_alias}_{contract}_{series_name}_{spec['timeframe']}"
    old = manifest["datasets"].get(key)
    if not force and final.exists() and old:
        if (old.get("requested_start_epoch") == int(start_epoch)
                and old.get("requested_end_epoch") == int(end_epoch)
                and old.get("sha256") == sha256(final)):
            return old
    if force and work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    expected = {
        "symbol_alias": symbol_alias, "contract_symbol": contract,
        "api_symbol": api_symbol, "series": series_name,
        "timeframe": spec["timeframe"], "start_epoch": int(start_epoch),
        "end_epoch": int(end_epoch), "max_candles": int(max_candles),
    }
    progress = read_progress(progress_path, expected)
    if progress is None:
        for stale in work.glob("chunk_*.csv"):
            stale.unlink()
        progress = {**expected, "next_start": int(start_epoch),
                    "request_count": 0, "empty_chunk_count": 0}
        atomic_text(progress_path, json.dumps(progress, sort_keys=True) + "\n")
    client = session or requests.Session()
    owns = session is None
    try:
        for chunk_start, chunk_end in build_chunks(
                progress["next_start"], end_epoch, step, max_candles):
            frame = fetch_chunk(client, api_symbol, series_name,
                chunk_start, chunk_end, retries=retries, sleep=sleep)
            if not frame.empty:
                atomic_csv(frame, work / f"chunk_{chunk_start}_{chunk_end}.csv")
            else:
                progress["empty_chunk_count"] += 1
            progress["request_count"] += 1
            progress["next_start"] = chunk_end + 1
            atomic_text(progress_path, json.dumps(progress, sort_keys=True) + "\n")
            if request_delay:
                sleep(request_delay)
        combined = _read_chunks(work)
        # Exclude in-progress candle intervals at the archive boundary.
        end = pd.to_datetime(int(end_epoch), unit="s", utc=True)
        start = pd.to_datetime(int(start_epoch), unit="s", utc=True)
        combined = combined[
            (combined.index >= start)
            & (combined.index + pd.Timedelta(seconds=step) <= end)
        ]
        combined = combined.sort_index()
        duplicates = int(combined.index.duplicated(keep="last").sum())
        combined = combined[~combined.index.duplicated(keep="last")]
        atomic_csv(combined, final)
        metadata = {
            "dataset_key": key, "symbol_alias": symbol_alias,
            "contract_symbol": contract, "api_symbol": api_symbol,
            "series": series_name, "timeframe": spec["timeframe"],
            "timeframe_seconds": step, "venue": "Delta Exchange India",
            "api_base_url": BASE_URL, "api_endpoint": ENDPOINT,
            "value_units": "raw API values; no scaling or unit conversion",
            "requested_start_epoch": int(start_epoch),
            "requested_end_epoch": int(end_epoch),
            "requested_start_utc": start.isoformat(),
            "requested_end_utc_exclusive": end.isoformat(),
            "first_candle_utc": combined.index[0].isoformat() if len(combined) else None,
            "last_candle_open_utc": combined.index[-1].isoformat() if len(combined) else None,
            "last_candle_close_utc": (combined.index[-1] + pd.Timedelta(seconds=step)).isoformat() if len(combined) else None,
            "row_count": int(len(combined)), "duplicate_rows_removed": duplicates,
            "empty_chunk_count": int(progress["empty_chunk_count"]),
            "request_count": int(progress["request_count"]),
            "csv_path": final.name, "sha256": sha256(final),
            **coverage_metrics(combined, step, int(start_epoch), int(end_epoch)),
        }
        manifest["datasets"][key] = metadata
        manifest["last_updated_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
        write_reports(Path(output_dir), manifest)
        shutil.rmtree(work, ignore_errors=True)
        return metadata
    finally:
        if owns:
            client.close()


def bootstrap(output_dir: Path, start: pd.Timestamp, end: pd.Timestamp, *,
              symbols: list[str] | None = None, series_names: list[str] | None = None,
              request_delay: float = 0.25, max_candles: int = MAX_API_CANDLES,
              retries: int = 5, force: bool = False):
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    if end <= start:
        raise ValueError("end must be later than start")
    symbols = symbols or list(C.SYMBOLS)
    series_names = series_names or list(SERIES)
    unknown_symbols = set(symbols).difference(C.SYMBOLS)
    unknown_series = set(series_names).difference(SERIES)
    if unknown_symbols or unknown_series:
        raise ValueError(f"Unknown symbols={sorted(unknown_symbols)} series={sorted(unknown_series)}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    start_epoch, end_epoch = int(start.timestamp()), int(end.timestamp())
    results = []
    total = len(symbols) * len(series_names)
    for alias in symbols:
        for name in series_names:
            result = download_dataset(alias, name, start_epoch, end_epoch, output_dir,
                request_delay=request_delay, max_candles=max_candles,
                retries=retries, force=force)
            results.append(result)
            print(f"{result['api_symbol']} {result['timeframe']}: "
                  f"{result['row_count']} rows | observed coverage "
                  f"{result['observed_coverage_pct']}% | gaps {result['gap_count']} | "
                  f"SHA256 {result['sha256'][:12]}...")
    write_reports(output_dir, load_manifest(output_dir / "manifest.json"))
    print(f"Completed {len(results)} of {total} derivative datasets.")
    return results


def build_parser():
    parser = argparse.ArgumentParser(
        description="Archive Delta funding, mark-price and open-interest history."
    )
    parser.add_argument("--output-dir", default="derivatives_history")
    parser.add_argument("--years", type=float, default=3.0)
    parser.add_argument("--start", help="UTC start date/time")
    parser.add_argument("--end", help="UTC end date/time; defaults to current UTC")
    parser.add_argument("--symbols", nargs="+", choices=sorted(C.SYMBOLS), default=list(C.SYMBOLS))
    parser.add_argument("--series", nargs="+", choices=sorted(SERIES), default=list(SERIES))
    parser.add_argument("--request-delay", type=float, default=0.25)
    parser.add_argument("--max-candles-per-request", type=int, default=MAX_API_CANDLES)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not math.isfinite(args.years) or args.years <= 0:
        raise SystemExit("--years must be finite and positive")
    end = pd.Timestamp(args.end) if args.end else pd.Timestamp.now(tz="UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    start = (pd.Timestamp(args.start) if args.start
             else end - pd.Timedelta(days=365.25 * args.years))
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    try:
        bootstrap(Path(args.output_dir), start, end, symbols=args.symbols,
            series_names=args.series, request_delay=args.request_delay,
            max_candles=args.max_candles_per_request,
            retries=args.retries, force=args.force)
    except (DerivativesArchiveError, OSError, ValueError) as exc:
        raise SystemExit(f"Derivative archive failed closed: {exc}") from exc


if __name__ == "__main__":
    main()
