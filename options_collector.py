"""Binance BTC/ETH options market-data collector.

Collects full-chain mark/IV/Greeks/OI snapshots every five minutes and
incrementally backfills hourly traded-option candles for near-ATM contracts.
It is read-only and never places orders.
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = os.environ.get("BINANCE_OPTIONS_API_BASE", "https://eapi.binance.com").rstrip("/")
DATA_DIR = Path(os.environ.get("OPTIONS_DATA_DIR", str(Path(os.environ.get("DATA_DIR", "market_data")) / "binance_options")))
STATE_PATH = DATA_DIR / "collector_state.json"
TIMEOUT = float(os.environ.get("OPTIONS_HTTP_TIMEOUT", "20"))
RETRIES = max(1, int(os.environ.get("OPTIONS_HTTP_RETRIES", "3")))
PAUSE_SECONDS = max(0.0, float(os.environ.get("OPTIONS_REQUEST_PAUSE_SECONDS", "0.08")))
BACKFILL_DAYS = max(30, int(os.environ.get("OPTIONS_BACKFILL_DAYS", "180")))
CONTRACTS_PER_ASSET = max(2, int(os.environ.get("OPTIONS_BACKFILL_CONTRACTS_PER_ASSET", "12")))
BACKFILL_BATCH_PER_ASSET = max(1, int(os.environ.get("OPTIONS_BACKFILL_BATCH_PER_ASSET", "2")))
MAX_EXPIRY_DAYS = max(7, int(os.environ.get("OPTIONS_BACKFILL_MAX_EXPIRY_DAYS", "90")))
SNAPSHOT_MINUTES = max(5, int(os.environ.get("OPTIONS_SNAPSHOT_MINUTES", "5")))

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json", "User-Agent": "SaltyQuantAI-options-collector/1.0"})

SNAPSHOT_FIELDS = [
    "snapshot_time_utc", "underlying", "option_symbol", "expiry_utc", "strike",
    "option_type", "index_price", "mark_price", "bid_iv", "ask_iv", "mark_iv",
    "delta", "gamma", "theta", "vega", "open_interest_contracts", "open_interest_usdt",
    "risk_free_interest",
]
KLINE_FIELDS = [
    "open_time_utc", "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_utc", "close_time_ms", "quote_volume", "trade_count",
    "taker_buy_base_volume", "taker_buy_quote_volume",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_from_ms(value: Any) -> str:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET a public Binance Options endpoint with bounded retry/backoff."""
    url = f"{BASE_URL}{path}"
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            response = SESSION.get(url, params=params or {}, timeout=TIMEOUT)
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = _to_float(response.headers.get("Retry-After"), 0.0) or 0.0
                time.sleep(max(retry_after, min(2 ** attempt, 8)))
                response.raise_for_status()
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("code"), (int, float)) and payload["code"] < 0:
                raise RuntimeError(f"Binance API error {payload.get('code')}: {payload.get('msg')}")
            if PAUSE_SECONDS:
                time.sleep(PAUSE_SECONDS)
            return payload
        except Exception as exc:
            last_error = exc
            if attempt + 1 < RETRIES:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Binance Options request failed: {path} params={params}: {last_error}") from last_error


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot safely read options collector state at {STATE_PATH}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Options collector state at {STATE_PATH} must be a JSON object")
    return payload


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, STATE_PATH)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _append_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> int:
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    return len(rows)


def _contract_metadata(exchange_info: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    by_asset: dict[str, list[dict[str, Any]]] = {"BTC": [], "ETH": []}
    for item in exchange_info.get("optionSymbols", []) or []:
        underlying = item.get("underlying")
        asset = "BTC" if underlying == "BTCUSDT" else "ETH" if underlying == "ETHUSDT" else None
        if asset is None:
            continue
        row = dict(item)
        row["asset"] = asset
        by_symbol[str(item.get("symbol", ""))] = row
        by_asset[asset].append(row)
    return by_symbol, by_asset


def _snapshot_bucket(now: datetime) -> str:
    minute = (now.minute // SNAPSHOT_MINUTES) * SNAPSHOT_MINUTES
    return now.replace(minute=minute, second=0, microsecond=0).isoformat()


def _collect_live_snapshot(now: datetime, state: dict[str, Any], exchange_info: dict[str, Any]) -> dict[str, Any]:
    """Persist one full BTC/ETH chain snapshot (mark/IV/Greeks and per-contract OI)."""
    bucket = _snapshot_bucket(now)
    if state.get("last_live_snapshot_bucket") == bucket:
        return {"status": "already_collected", "bucket": bucket, "rows": 0}

    by_symbol, by_asset = _contract_metadata(exchange_info)
    marks = _get("/eapi/v1/mark")
    if not isinstance(marks, list):
        raise RuntimeError("Unexpected Binance /mark response: expected a list")

    indices: dict[str, float | None] = {}
    for asset in ("BTC", "ETH"):
        index_payload = _get("/eapi/v1/index", {"underlying": f"{asset}USDT"})
        indices[asset] = _to_float(index_payload.get("indexPrice")) if isinstance(index_payload, dict) else None

    expiries: dict[str, set[str]] = {"BTC": set(), "ETH": set()}
    for asset, contracts in by_asset.items():
        for contract in contracts:
            expiry_ms = contract.get("expiryDate")
            if expiry_ms is not None:
                expiries[asset].add(datetime.fromtimestamp(int(expiry_ms) / 1000, tz=timezone.utc).strftime("%y%m%d"))

    oi_by_symbol: dict[str, dict[str, float | None]] = {}
    oi_errors: list[str] = []
    for asset, expiry_dates in expiries.items():
        for expiry in sorted(expiry_dates):
            try:
                oi_rows = _get("/eapi/v1/openInterest", {"underlyingAsset": asset, "expiration": expiry})
                if isinstance(oi_rows, list):
                    for oi in oi_rows:
                        symbol = str(oi.get("symbol", ""))
                        oi_by_symbol[symbol] = {
                            "open_interest_contracts": _to_float(oi.get("sumOpenInterest")),
                            "open_interest_usdt": _to_float(oi.get("sumOpenInterestUsd")),
                        }
            except Exception as exc:
                oi_errors.append(f"{asset} {expiry}: {exc}")

    rows: list[dict[str, Any]] = []
    timestamp = now.isoformat()
    for mark in marks:
        symbol = str(mark.get("symbol", ""))
        meta = by_symbol.get(symbol)
        if not meta:
            continue
        oi = oi_by_symbol.get(symbol, {})
        asset = meta["asset"]
        expiry_ms = meta.get("expiryDate")
        rows.append({
            "snapshot_time_utc": timestamp,
            "underlying": asset,
            "option_symbol": symbol,
            "expiry_utc": _iso_from_ms(expiry_ms) if expiry_ms else "",
            "strike": _to_float(meta.get("strikePrice")),
            "option_type": meta.get("side"),
            "index_price": indices.get(asset),
            "mark_price": _to_float(mark.get("markPrice")),
            "bid_iv": _to_float(mark.get("bidIV")),
            "ask_iv": _to_float(mark.get("askIV")),
            "mark_iv": _to_float(mark.get("markIV")),
            "delta": _to_float(mark.get("delta")),
            "gamma": _to_float(mark.get("gamma")),
            "theta": _to_float(mark.get("theta")),
            "vega": _to_float(mark.get("vega")),
            "open_interest_contracts": oi.get("open_interest_contracts"),
            "open_interest_usdt": oi.get("open_interest_usdt"),
            "risk_free_interest": _to_float(mark.get("riskFreeInterest")),
        })

    if not rows:
        raise RuntimeError("Binance returned no BTC/ETH mark rows; snapshot not marked complete")
    daily_path = DATA_DIR / "snapshots" / f"chain_{now.strftime('%Y-%m-%d')}.csv"
    count = _append_csv(daily_path, rows, SNAPSHOT_FIELDS)
    state["last_live_snapshot_bucket"] = bucket
    state["last_live_snapshot_at"] = timestamp
    state["last_snapshot_row_count"] = count
    state["last_snapshot_oi_errors"] = oi_errors[:20]
    _save_state(state)
    return {"status": "collected", "bucket": bucket, "rows": count, "oi_errors": len(oi_errors)}


def _select_backfill_contracts(by_asset: dict[str, list[dict[str, Any]]], indices: dict[str, float], now: datetime) -> list[str]:
    """Choose active near-ATM contracts from the nearest expiries for manageable history backfill."""
    selected_by_asset: dict[str, list[str]] = {"BTC": [], "ETH": []}
    now_ms = int(now.timestamp() * 1000)
    max_expiry_ms = now_ms + MAX_EXPIRY_DAYS * 86400_000
    for asset in ("BTC", "ETH"):
        spot = _to_float(indices.get(asset))
        if not spot or spot <= 0:
            continue
        candidates = []
        for item in by_asset.get(asset, []):
            if item.get("status") != "TRADING":
                continue
            try:
                expiry_ms = int(item.get("expiryDate"))
                strike = float(item.get("strikePrice"))
            except (TypeError, ValueError):
                continue
            if expiry_ms < now_ms or expiry_ms > max_expiry_ms or strike <= 0:
                continue
            moneyness_distance = abs(strike / spot - 1.0)
            if moneyness_distance > 0.20:
                continue
            candidates.append((moneyness_distance, expiry_ms, strike, str(item.get("symbol", ""))))
        candidates.sort()
        unique_strikes: list[tuple[int, float]] = []
        seen: set[tuple[int, float]] = set()
        for _, expiry_ms, strike, _ in candidates:
            key = (expiry_ms, strike)
            if key not in seen:
                seen.add(key)
                unique_strikes.append(key)
        chosen_keys = set(unique_strikes[: max(1, CONTRACTS_PER_ASSET // 2)])
        for _, expiry_ms, strike, symbol in candidates:
            if (expiry_ms, strike) in chosen_keys and symbol not in selected_by_asset[asset]:
                selected_by_asset[asset].append(symbol)

    selected: list[str] = []
    for index in range(max(len(selected_by_asset["BTC"]), len(selected_by_asset["ETH"]))):
        for asset in ("BTC", "ETH"):
            if index < len(selected_by_asset[asset]):
                selected.append(selected_by_asset[asset][index])
    return selected


def _fetch_hourly_klines(symbol: str, days: int, now: datetime) -> list[list[Any]]:
    start_ms = int((now - timedelta(days=days)).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    cursor = start_ms
    raw_rows: list[list[Any]] = []
    last_open = -1
    while cursor <= end_ms:
        batch = _get("/eapi/v1/klines", {
            "symbol": symbol, "interval": "1h", "startTime": cursor,
            "endTime": end_ms, "limit": 1500,
        })
        if not isinstance(batch, list) or not batch:
            break
        raw_rows.extend(batch)
        try:
            newest_open = int(batch[-1][0])
        except (TypeError, ValueError, IndexError):
            break
        if newest_open <= last_open:
            break
        last_open = newest_open
        if len(batch) < 1500:
            break
        cursor = newest_open + 1
    # Ignore zero-trade placeholder bars; they are not evidence of an executable option price.
    return [row for row in raw_rows if isinstance(row, list) and len(row) >= 12 and
            (_to_float(row[5], 0.0) or 0.0) > 0 and int(_to_float(row[8], 0.0) or 0) > 0]


def _persist_klines(asset: str, symbol: str, raw_rows: list[list[Any]]) -> int:
    rows = []
    for row in raw_rows:
        try:
            volume = _to_float(row[5], 0.0) or 0.0
            trade_count = int(_to_float(row[8], 0.0) or 0)
            # Do not persist synthetic/no-trade placeholder candles as executable history.
            if volume <= 0 or trade_count <= 0:
                continue
            rows.append({
                "open_time_utc": _iso_from_ms(row[0]), "open_time_ms": int(row[0]),
                "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5],
                "close_time_utc": _iso_from_ms(row[6]), "close_time_ms": int(row[6]),
                "quote_volume": row[7], "trade_count": trade_count,
                "taker_buy_base_volume": row[9], "taker_buy_quote_volume": row[10],
            })
        except (TypeError, ValueError, IndexError):
            continue
    if not rows:
        return 0
    path = DATA_DIR / "historical_klines_1h" / asset / f"{symbol}.csv"
    seen: set[int] = set()
    if path.exists():
        try:
            with path.open("r", newline="", encoding="utf-8") as handle:
                for existing in csv.DictReader(handle):
                    try:
                        seen.add(int(existing["open_time_ms"]))
                    except (KeyError, TypeError, ValueError):
                        continue
        except OSError as exc:
            raise RuntimeError(f"Cannot read existing options candle history: {path}") from exc
    new_rows = [row for row in rows if row["open_time_ms"] not in seen]
    new_rows.sort(key=lambda row: row["open_time_ms"])
    return _append_csv(path, new_rows, KLINE_FIELDS)


def _run_history_backfill_batch(now: datetime, state: dict[str, Any], exchange_info: dict[str, Any]) -> dict[str, Any]:
    """Backfill a small contract batch per worker cycle to avoid API bursts/timeouts."""
    queue = state.get("history_backfill_queue")
    cursor = int(state.get("history_backfill_cursor", 0))
    if isinstance(queue, list) and not queue:
        state["history_backfill_completed_at"] = state.get("history_backfill_completed_at") or now.isoformat()
        _save_state(state)
        return {"status": "complete_no_eligible_contracts", "processed": 0, "remaining": 0}
    if not isinstance(queue, list):
        _, by_asset = _contract_metadata(exchange_info)
        indices = {}
        for asset in ("BTC", "ETH"):
            payload = _get("/eapi/v1/index", {"underlying": f"{asset}USDT"})
            indices[asset] = _to_float(payload.get("indexPrice")) if isinstance(payload, dict) else None
        indices = {key: value for key, value in indices.items() if value is not None}
        queue = _select_backfill_contracts(by_asset, indices, now)
        state["history_backfill_queue"] = queue
        state["history_backfill_cursor"] = 0
        state["history_backfill_started_at"] = now.isoformat()
        state["history_backfill_days"] = BACKFILL_DAYS
        _save_state(state)
        cursor = 0

    if cursor >= len(queue):
        state.setdefault("history_backfill_completed_at", now.isoformat())
        _save_state(state)
        return {"status": "complete", "processed": 0, "remaining": 0}

    batch_limit = BACKFILL_BATCH_PER_ASSET * 2
    batch_symbols = queue[cursor:cursor + batch_limit]
    processed = 0
    bars = 0
    errors: list[str] = []
    by_symbol, _ = _contract_metadata(exchange_info)
    for symbol in batch_symbols:
        try:
            raw_rows = _fetch_hourly_klines(symbol, BACKFILL_DAYS, now)
            asset = by_symbol.get(symbol, {}).get("asset") or symbol.split("-", 1)[0]
            saved = _persist_klines(asset, symbol, raw_rows)
            bars += saved
            processed += 1
            print(f"[options-history] {symbol}: saved {saved} non-zero 1h bars", flush=True)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            processed += 1
        if PAUSE_SECONDS:
            time.sleep(PAUSE_SECONDS)

    state["history_backfill_cursor"] = cursor + processed
    state.setdefault("history_backfill_errors", []).extend(errors)
    state["history_backfill_errors"] = state["history_backfill_errors"][-100:]
    remaining = max(0, len(queue) - state["history_backfill_cursor"])
    if remaining == 0:
        state["history_backfill_completed_at"] = now.isoformat()
    _save_state(state)
    return {"status": "running" if remaining else "complete", "processed": processed,
            "bars_saved": bars, "remaining": remaining, "errors": errors}


def _refresh_recent_history(now: datetime, state: dict[str, Any]) -> dict[str, Any] | None:
    """Refresh already-backfilled contracts once per UTC hour."""
    queue = state.get("history_backfill_queue") or []
    cursor = int(state.get("history_backfill_cursor", 0))
    completed_symbols = queue[:cursor]
    hour_bucket = now.replace(minute=0, second=0, microsecond=0).isoformat()
    if not completed_symbols or state.get("last_hourly_history_refresh") == hour_bucket:
        return None
    saved = 0
    errors = []
    for symbol in completed_symbols:
        try:
            recent = _get("/eapi/v1/klines", {
                "symbol": symbol, "interval": "1h",
                "startTime": int((now - timedelta(hours=6)).timestamp() * 1000),
                "endTime": int(now.timestamp() * 1000), "limit": 10,
            })
            asset = symbol.split("-", 1)[0]
            saved += _persist_klines(asset, symbol, recent if isinstance(recent, list) else [])
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
    state["last_hourly_history_refresh"] = hour_bucket
    state["hourly_history_refresh_errors"] = errors[-50:]
    _save_state(state)
    return {"status": "refreshed", "contracts": len(completed_symbols), "new_bars": saved, "errors": len(errors)}


def run_cycle(now: datetime | None = None) -> dict[str, Any]:
    """Collect one live chain snapshot and advance the historical backfill queue."""
    if os.environ.get("OPTIONS_COLLECTOR_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return {"status": "disabled"}
    now = now or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = _load_state()
    exchange_info = _get("/eapi/v1/exchangeInfo")
    if not isinstance(exchange_info, dict):
        raise RuntimeError("Unexpected Binance /exchangeInfo response")

    result: dict[str, Any] = {"snapshot": None, "history_backfill": None, "history_refresh": None}
    try:
        result["snapshot"] = _collect_live_snapshot(now, state, exchange_info)
    except Exception as exc:
        result["snapshot"] = {"status": "error", "error": str(exc)}
        print(f"[options-snapshot-error] {exc}", flush=True)
    try:
        if not state.get("history_backfill_completed_at"):
            result["history_backfill"] = _run_history_backfill_batch(now, state, exchange_info)
        else:
            result["history_refresh"] = _refresh_recent_history(now, state)
    except Exception as exc:
        result["history_backfill"] = {"status": "error", "error": str(exc)}
        print(f"[options-history-error] {exc}", flush=True)
    print(f"[options-collector] {json.dumps(result, default=str)}", flush=True)
    return result


if __name__ == "__main__":
    run_cycle()
