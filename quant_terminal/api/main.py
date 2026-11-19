"""Read-only FastAPI adapter for the existing Salty Quant engines and persisted state.

The adapter deliberately does not fetch market data, run strategies, mutate state,
submit orders, or send alerts. Run it on loopback unless an explicit API token is set.
"""
from __future__ import annotations

import csv
import hmac
import ipaddress
import json
import os
import platform
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request

import config
import data
import quant_supervisor

ROOT = Path(__file__).resolve().parents[2]
API_VERSION = "0.1.0"
TIMEFRAME_MINUTES = dict(data.MINUTES)
FRESHNESS_LIMIT_MINUTES = {"5m": 15, "15m": 35, "1h": 150, "4h": 540, "1d": 3 * 1440, "1w": 21 * 1440}


def _path_from_env(name: str, default: str) -> Path:
    raw = Path(os.environ.get(name, default)).expanduser()
    return raw if raw.is_absolute() else ROOT / raw


DATA_DIR = _path_from_env("DATA_DIR", "market_data")
STATE_PATH = _path_from_env("STATE_PATH", "state.json")
SIGNALS_PATH = _path_from_env("QUANT_RESEARCH_PATH", "research/quant_signals.jsonl")
LEDGER_PATH = _path_from_env("QUANT_RESEARCH_LEDGER", "research/RESEARCH_LEDGER.md")
DISCOVERY_DIR = _path_from_env("QUANT_DISCOVERY_DIR", "quant_discovery")

app = FastAPI(
    title="Salty Quant Read-only API",
    version=API_VERSION,
    description="Read-only view of persisted market, research, backtest and paper state.",
)


@app.middleware("http")
async def local_or_token_only(request: Request, call_next):
    """No CORS and no public unauthenticated access to local research/paper state."""
    token = os.environ.get("QUANT_API_TOKEN", "")
    if token:
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {token}"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"status": "unavailable", "reason": "unauthorized"}, status_code=401)
    else:
        host = request.client.host if request.client else ""
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "testclient"
        if not loopback:
            from fastapi.responses import JSONResponse
            return JSONResponse({"status": "unavailable", "reason": "local_only_api"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _now_utc(value: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    stamp = pd.Timestamp(value) if value is not None else pd.Timestamp.now(tz="UTC")
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _read_frame(symbol: str, timeframe: str) -> pd.DataFrame | None:
    path = DATA_DIR / f"{symbol}_{timeframe}.csv"
    if not path.is_file():
        return None
    try:
        return data.normalize(pd.read_csv(path, index_col=0, parse_dates=True))
    except Exception:
        return None


def _timeframe_status(frame: pd.DataFrame | None, timeframe: str, now: pd.Timestamp) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {"status": "unavailable", "reason": "no persisted candles", "last_closed_at": None, "age_minutes": None, "rows": 0}
    close_at = frame.index[-1] + pd.Timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    age = (now - close_at).total_seconds() / 60.0
    recent = frame.index[-15:]
    continuity_ok = len(recent) == 15 and bool(
        recent.to_series().diff().dropna().eq(pd.Timedelta(minutes=TIMEFRAME_MINUTES[timeframe])).all()
    )
    reasons = []
    if age < -2:
        reasons.append("last candle closes in the future")
    if age > FRESHNESS_LIMIT_MINUTES[timeframe]:
        reasons.append("last closed candle exceeds freshness limit")
    if not continuity_ok:
        reasons.append("fewer than 15 contiguous recent candles")
    return {
        "status": "stale" if reasons else "live",
        "reason": "; ".join(reasons) if reasons else None,
        "last_closed_at": close_at.isoformat(),
        "age_minutes": round(age, 2),
        "rows": int(len(frame)),
    }


def build_market_snapshot(now: datetime | pd.Timestamp | None = None, symbols: list[str] | None = None) -> dict[str, Any]:
    stamp = _now_utc(now)
    requested = symbols or list(config.SYMBOLS)
    unknown = sorted(set(requested).difference(config.SYMBOLS))
    if unknown:
        raise ValueError(f"Unknown symbols: {', '.join(unknown)}")
    markets = []
    for symbol in requested:
        cfg = config.SYMBOLS[symbol]
        frames = {tf: _read_frame(symbol, tf) for tf in TIMEFRAME_MINUTES}
        # Enforce closed-candle semantics again at read time, even though data.py
        # normally persists only closed bars.
        for tf, frame in list(frames.items()):
            if frame is not None and not frame.empty:
                frames[tf] = frame[frame.index + pd.Timedelta(minutes=TIMEFRAME_MINUTES[tf]) <= stamp]
        statuses = {tf: _timeframe_status(frames[tf], tf, stamp) for tf in TIMEFRAME_MINUTES}
        primary = statuses["5m"]
        frame = frames["5m"]
        latest = frame.iloc[-1] if frame is not None and not frame.empty else None
        markets.append({
            "symbol": symbol,
            "instrument": cfg.get("delta_symbol", symbol),
            "kind": cfg.get("kind", "unknown"),
            "venue": "Delta Exchange India",
            "status": primary["status"],
            "reason": primary["reason"],
            "last_price": float(latest.close) if latest is not None else None,
            "last_volume": float(latest.volume) if latest is not None else None,
            "last_closed_5m_candle_open": frame.index[-1].isoformat() if latest is not None else None,
            "age_minutes": primary["age_minutes"],
            "timeframes": statuses,
            "all_timeframes_fresh": all(item["status"] == "live" for item in statuses.values()),
        })
    overall = "unavailable" if not markets or all(m["status"] == "unavailable" for m in markets) else (
        "live" if all(m["status"] == "live" for m in markets) else "stale"
    )
    return {"status": overall, "as_of": stamp.isoformat(), "source": "local persisted Delta public OHLCV cache", "markets": markets}


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "not_created"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "unreadable"
    if not isinstance(value, dict):
        return None, "invalid_shape"
    return value, None


def _safe_position(item: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "signal_id", "sym", "dir", "entry", "sl", "tp", "rr", "setup_type",
        "strategy_id", "quality_score", "score_type", "triggered_at", "status", "entry_source",
    )
    return {key: item.get(key) for key in allowed if key in item}


def _paper_snapshot() -> tuple[dict[str, Any] | None, str | None]:
    state, error = _read_json_object(STATE_PATH)
    if error:
        return None, error
    assert state is not None
    if not isinstance(state.get("positions", {}), dict) or not isinstance(state.get("trade_history", []), list):
        return None, "invalid_shape"
    return state, None


def _tail_jsonl(path: Path, limit: int = 1000) -> tuple[list[dict[str, Any]], int, str | None]:
    if not path.is_file():
        return [], 0, "not_created"
    rows: deque[str] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as handle:
            rows.extend(handle)
    except (OSError, UnicodeError):
        return [], 0, "unreadable"
    parsed, malformed = [], 0
    for line in rows:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                parsed.append(item)
            else:
                malformed += 1
        except json.JSONDecodeError:
            malformed += 1
    return parsed, malformed, None


def _record_status(timestamp: Any, now: pd.Timestamp, max_age_minutes: int = 20) -> str:
    try:
        age = (now - _now_utc(timestamp)).total_seconds() / 60
    except Exception:
        return "unavailable"
    return "live" if -2 <= age <= max_age_minutes else "stale"


def build_scanner_snapshot(now: datetime | pd.Timestamp | None = None, limit: int = 50) -> dict[str, Any]:
    stamp = _now_utc(now)
    records, malformed, error = _tail_jsonl(SIGNALS_PATH)
    if error:
        return {"status": "unavailable", "reason": error, "as_of": stamp.isoformat(), "source": str(SIGNALS_PATH), "symbols": []}
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        latest[str(record.get("symbol", "UNKNOWN"))] = record
    symbols = []
    for symbol, record in sorted(latest.items()):
        symbols.append({
            "symbol": symbol,
            "status": _record_status(record.get("timestamp"), stamp),
            "timestamp": record.get("timestamp"),
            "latest_closed_5m_candle": record.get("latest_closed_5m_candle"),
            "latest_closed_5m_price": record.get("latest_closed_5m_price"),
            "decision_status": record.get("decision_status"),
            "decision_reason": record.get("decision_reason"),
            "selected_strategy": record.get("selected_strategy"),
            "research_preview_strategy": record.get("research_preview_strategy"),
            "candidates": record.get("candidates", [])[:20] if isinstance(record.get("candidates"), list) else [],
            "rejected_candidates": record.get("rejected_candidates", [])[:20] if isinstance(record.get("rejected_candidates"), list) else [],
            "has_open_position": record.get("has_open_position"),
        })
    status = "unavailable" if not symbols else ("live" if any(x["status"] == "live" for x in symbols) else "stale")
    return {"status": status, "as_of": stamp.isoformat(), "source": str(SIGNALS_PATH), "malformed_lines_in_tail": malformed, "symbols": symbols[:limit]}


def build_research_snapshot(limit: int = 50) -> dict[str, Any]:
    if not LEDGER_PATH.is_file():
        return {"status": "unavailable", "source": str(LEDGER_PATH), "entries": []}
    try:
        content = LEDGER_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"status": "unavailable", "source": str(LEDGER_PATH), "entries": []}
    matches = list(re.finditer(r"(?m)^##\s+(.+)$", content))
    entries = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        section = content[start:end].strip()
        paragraph = next((part.strip() for part in re.split(r"\n\s*\n", section) if part.strip()), "")
        entries.append({"title": match.group(1).strip(), "summary": paragraph[:700]})
    return {"status": "available", "source": str(LEDGER_PATH), "entry_count": len(entries), "entries": entries[-limit:][::-1]}


def build_backtest_snapshot(limit: int = 50) -> dict[str, Any]:
    if not DISCOVERY_DIR.is_dir():
        return {"status": "unavailable", "source": str(DISCOVERY_DIR), "artifacts": []}
    candidates = []
    patterns = ("*METADATA*.json", "*metadata*.json", "*PRIMARY*.csv", "*METRICS*.csv", "*RESULTS*.md")
    seen = set()
    for pattern in patterns:
        for path in DISCOVERY_DIR.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                display_path = str(path.relative_to(ROOT))
            except ValueError:
                display_path = path.name
            item: dict[str, Any] = {"name": path.name, "path": display_path, "bytes": path.stat().st_size}
            if path.suffix.lower() == ".json" and path.stat().st_size <= 512_000:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        item["metadata"] = {key: payload[key] for key in ("status", "symbol", "asset", "strategy", "strategy_id", "run_id", "start_utc", "end_utc", "configurations", "trade_count", "validation_passes", "oos_evaluated") if key in payload}
                except (OSError, UnicodeError, json.JSONDecodeError):
                    item["metadata_status"] = "unreadable"
            elif path.suffix.lower() == ".csv" and path.stat().st_size <= 512_000:
                try:
                    with path.open("r", encoding="utf-8", newline="") as handle:
                        reader = csv.DictReader(handle)
                        item["columns"] = reader.fieldnames or []
                        item["rows"] = list(deque(reader, maxlen=25))
                except (OSError, UnicodeError, csv.Error):
                    item["data_status"] = "unreadable"
            candidates.append(item)
    candidates.sort(key=lambda item: item["name"], reverse=True)
    return {"status": "available" if candidates else "unavailable", "source": str(DISCOVERY_DIR), "artifact_count": len(candidates), "artifacts": candidates[:limit]}


@app.get("/api/v1/health")
def get_health():
    return {
        "status": "available",
        "service": "salty-quant-read-only-api",
        "api_version": API_VERSION,
        "as_of": _now_utc().isoformat(),
        "source": "local repository and persisted state",
        "checks": {
            "market_data_cache": "present" if DATA_DIR.is_dir() else "not_created",
            "paper_state": "present" if STATE_PATH.is_file() else "not_created",
            "quant_signal_log": "present" if SIGNALS_PATH.is_file() else "not_created",
            "research_ledger": "present" if LEDGER_PATH.is_file() else "not_created",
            "backtest_artifacts": "present" if DISCOVERY_DIR.is_dir() else "not_created",
        },
        "approved_strategy_count": len(quant_supervisor.APPROVED_STRATEGIES),
        "python_version": platform.python_version(),
    }


@app.get("/api/v1/markets")
def get_markets(symbols: str | None = Query(default=None, description="Comma-separated config symbols, e.g. BTC,ETH,XAU")):
    requested = [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    try:
        return build_market_snapshot(symbols=requested)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/scanner/candidates")
def get_scanner_candidates(limit: int = Query(default=50, ge=1, le=200)):
    return build_scanner_snapshot(limit=limit)


@app.get("/api/v1/research/experiments")
def get_research_experiments(limit: int = Query(default=50, ge=1, le=200)):
    return build_research_snapshot(limit=limit)


@app.get("/api/v1/backtests")
def get_backtests(limit: int = Query(default=50, ge=1, le=200)):
    return build_backtest_snapshot(limit=limit)


@app.get("/api/v1/paper/positions")
def get_paper_positions():
    state, error = _paper_snapshot()
    if error:
        return {"status": "unavailable", "reason": error, "source": str(STATE_PATH), "positions": None, "position_count": None}
    assert state is not None
    positions = state.get("positions", {})
    return {
        "status": "available",
        "source": str(STATE_PATH),
        "as_of": _now_utc().isoformat(),
        "position_count": len(positions),
        "positions": [_safe_position(item) for item in positions.values() if isinstance(item, dict)],
        "pending_outcome_count": len(state.get("pending_outcomes", {})) if isinstance(state.get("pending_outcomes", {}), dict) else None,
    }


@app.get("/api/v1/paper/history")
def get_paper_history(limit: int = Query(default=100, ge=1, le=500)):
    state, error = _paper_snapshot()
    if error:
        return {"status": "unavailable", "reason": error, "source": str(STATE_PATH), "trade_count": None, "trades": None}
    assert state is not None
    history = state.get("trade_history", [])
    allowed = ("signal_id", "sym", "dir", "entry", "exit", "sl", "tp", "rr", "setup_type", "strategy_id", "triggered_at", "exit_time", "status", "gross_R", "gross_pnl_pct", "entry_source")
    trades = [{key: item.get(key) for key in allowed if key in item} for item in history[-limit:] if isinstance(item, dict)]
    return {"status": "available", "source": str(STATE_PATH), "trade_count": len(history), "retained_trade_limit": 2000, "trades": trades}


@app.get("/api/v1/risk/summary")
def get_risk_summary():
    state, error = _paper_snapshot()
    if error:
        return {"status": "unavailable", "reason": error, "source": str(STATE_PATH), "open_positions": None, "account_equity": None, "account_exposure": None, "circuit_breaker": "unavailable"}
    assert state is not None
    positions = state.get("positions", {})
    history = state.get("trade_history", [])
    values = []
    for item in history:
        if not isinstance(item, dict):
            continue
        try:
            value = float(item.get("gross_R"))
        except (TypeError, ValueError):
            continue
        if pd.notna(value):
            values.append(value)
    drawdown_r = None
    realized_gross_r = None
    if values:
        cumulative = pd.Series(values).cumsum()
        drawdown_r = float((cumulative - cumulative.cummax()).min())
        realized_gross_r = float(sum(values))
    return {
        "status": "available",
        "as_of": _now_utc().isoformat(),
        "source": str(STATE_PATH),
        "open_positions": len(positions),
        "open_symbols": sorted({str(item.get("sym")) for item in positions.values() if isinstance(item, dict) and item.get("sym")}),
        "pending_outcomes": len(state.get("pending_outcomes", {})) if isinstance(state.get("pending_outcomes", {}), dict) else None,
        "approved_strategy_count": len(quant_supervisor.APPROVED_STRATEGIES),
        "realized_gross_r_retained_history": realized_gross_r,
        "max_drawdown_r_retained_history": drawdown_r,
        "retained_history_trades": len(values),
        "account_equity": None,
        "account_exposure": None,
        "circuit_breaker": "unavailable_not_persisted",
        "limitations": [
            "Paper state has no account capital or position quantity; account equity and notional exposure cannot be calculated.",
            "Drawdown is a gross-R diagnostic over the retained trade-history window, not account drawdown or a fee-adjusted equity curve.",
        ],
    }
