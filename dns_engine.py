"""Persistent AI-authored DNS map and deterministic local setup watcher.

The AI owns visual zone discovery. This module only validates/persists that map and
checks closed candles against it; it never invents or widens a demand/supply zone.
"""
import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd

TIMEFRAMES = {"1w", "1d", "4h", "1h", "15m", "5m"}
MAP_REFRESH_HOURS = max(1, int(os.environ.get("DNS_MAP_REFRESH_HOURS", "4")))
MIN_ZONE_QUALITY = max(1, min(5, int(os.environ.get("MIN_DNS_ZONE_QUALITY", "3"))))
MAX_HISTORY = 20


def _path():
    return Path(os.environ.get("DNS_MAP_PATH", str(Path(os.environ.get("DATA_DIR", "market_data")) / "dns_map.json")))


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def load_map(path=None):
    target = Path(path) if path else _path()
    try:
        with target.open(encoding="utf-8") as handle:
            result = json.load(handle)
    except FileNotFoundError:
        return {"schema_version": 1, "symbols": {}, "history": {}}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot safely read DNS map at {target}") from exc
    if not isinstance(result, dict) or result.get("schema_version") != 1:
        raise RuntimeError("DNS map has an unsupported or invalid schema; refusing to reset it")
    result.setdefault("symbols", {})
    result.setdefault("history", {})
    return result


def _clean_zones(zones, side):
    if not isinstance(zones, list):
        raise ValueError(f"{side} zones must be a list")
    cleaned = []
    seen = set()
    for raw in zones:
        if not isinstance(raw, dict):
            continue
        try:
            low, high = float(raw["low"]), float(raw["high"])
            quality = int(raw["quality"])
            timeframe = str(raw["timeframe"])
            evidence = str(raw.get("evidence", "")).strip()
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (not math.isfinite(low) or not math.isfinite(high) or low <= 0
                or low >= high or quality < 1 or quality > 5
                or timeframe not in TIMEFRAMES or not evidence):
            continue
        key = (round(low, 10), round(high, 10), timeframe)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "zone_id": hashlib.sha1(
                f"{side}|{low:.10f}|{high:.10f}|{timeframe}".encode()
            ).hexdigest()[:12],
            "side": side, "low": low, "high": high,
            "timeframe": timeframe, "quality": quality,
            "evidence": evidence[:500], "status": "ACTIVE",
        })
    return cleaned[:10]


def validate_analysis(symbol, analysis, observed_at, price):
    """Convert a schema-validated AI map into a compact, auditable symbol snapshot."""
    if not isinstance(analysis, dict):
        raise ValueError("AI analysis must be an object")
    if analysis.get("symbol") != symbol:
        raise ValueError("AI map symbol mismatch")
    stamp = pd.Timestamp(observed_at)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    price = float(price)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Map reference price must be positive and finite")
    demand = _clean_zones(analysis.get("demand_zones", []), "DEMAND")
    supply = _clean_zones(analysis.get("supply_zones", []), "SUPPLY")
    liquidity = []
    for level in analysis.get("liquidity_levels", []) or []:
        if not isinstance(level, dict):
            continue
        try:
            value = float(level["price"])
            timeframe = str(level["timeframe"])
            kind = str(level["kind"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0 and timeframe in TIMEFRAMES:
            liquidity.append({
                "price": value, "timeframe": timeframe,
                "kind": kind, "evidence": str(level.get("evidence", ""))[:300]
            })
    return {
        "symbol": symbol,
        "mapped_at": stamp.isoformat(),
        "reference_price": price,
        "bias": str(analysis.get("bias", "UNCLEAR")),
        "structure_summary": str(analysis.get("structure_summary", ""))[:1200],
        "demand_zones": demand,
        "supply_zones": supply,
        "liquidity_levels": liquidity[:30],
        "key_observations": [str(x)[:300] for x in (analysis.get("key_observations") or [])[:20]],
        "source": "AI_VISUAL_MAP",
    }


def save_analysis(map_state, symbol, analysis, observed_at, price, path=None):
    """Version every accepted AI map; retain prior maps for audit and replay."""
    snapshot = validate_analysis(symbol, analysis, observed_at, price)
    symbols = map_state.setdefault("symbols", {})
    history = map_state.setdefault("history", {})
    previous = symbols.get(symbol)
    versions = history.setdefault(symbol, [])
    if previous:
        versions.append(previous)
        history[symbol] = versions[-MAX_HISTORY:]
    revision = int(previous.get("revision", 0)) + 1 if previous else 1
    snapshot["revision"] = revision
    symbols[symbol] = snapshot
    if path:
        _atomic_json(Path(path), map_state)
    else:
        _atomic_json(_path(), map_state)
    return snapshot


def refresh_reasons(snapshot, now, frames):
    """Refresh on age or a confirmed 1h close through a mapped zone."""
    if not snapshot:
        return ["NO_EXISTING_MAP"]
    stamp = pd.Timestamp(snapshot.get("mapped_at"))
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    current = pd.Timestamp(now)
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    reasons = []
    if current - stamp >= pd.Timedelta(hours=MAP_REFRESH_HOURS):
        reasons.append("SCHEDULED_REFRESH")
    h1 = frames.get("1h")
    if h1 is not None and len(h1) >= 2:
        close = float(h1.iloc[-1].close)
        zones = snapshot.get("demand_zones", []) + snapshot.get("supply_zones", [])
        for zone in zones:
            if zone.get("status") != "ACTIVE":
                continue
            if zone["side"] == "DEMAND" and close < float(zone["low"]):
                reasons.append("DEMAND_ZONE_BROKEN")
                break
            if zone["side"] == "SUPPLY" and close > float(zone["high"]):
                reasons.append("SUPPLY_ZONE_BROKEN")
                break
    return list(dict.fromkeys(reasons))


def _nearest_target(zones, entry, direction):
    candidates = []
    for zone in zones:
        if zone.get("status") != "ACTIVE":
            continue
        level = float(zone["low"] if direction == "LONG" else zone["high"])
        if direction == "LONG" and level > entry:
            candidates.append(level)
        elif direction == "SHORT" and level < entry:
            candidates.append(level)
    if not candidates:
        return None
    return min(candidates) if direction == "LONG" else max(candidates)


def detect_local_setup(symbol, frames, snapshot, now=None):
    """Return a confirmed paper candidate only for a two-candle sweep/reclaim at DNS.

    This intentionally narrow first detector is a baseline, not a claim that all
    sub-setups are implemented. It requires a sweep beyond the zone and a close
    back through its far edge, followed by a confirming close beyond the reclaim
    candle extreme. No AI call is made here.
    """
    m5 = frames.get("5m")
    if m5 is None or len(m5) < 3 or not snapshot:
        return []
    bars = m5.tail(3)
    sweep, confirm = bars.iloc[-2], bars.iloc[-1]
    out = []
    h1 = frames.get("1h")
    latest_h1_close = float(h1.iloc[-1].close) if h1 is not None and not h1.empty else None
    for side, zones, opposing, direction in (
        ("DEMAND", snapshot.get("demand_zones", []), snapshot.get("supply_zones", []), "LONG"),
        ("SUPPLY", snapshot.get("supply_zones", []), snapshot.get("demand_zones", []), "SHORT"),
    ):
        for zone in zones:
            if zone.get("status") != "ACTIVE" or int(zone.get("quality", 0)) < MIN_ZONE_QUALITY:
                continue
            low, high = float(zone["low"]), float(zone["high"])
            # A confirmed 1h close through the distal edge invalidates the zone.
            if latest_h1_close is not None and (
                (side == "DEMAND" and latest_h1_close < low)
                or (side == "SUPPLY" and latest_h1_close > high)
            ):
                continue
            if side == "DEMAND":
                swept = float(sweep.low) < low and float(sweep.close) > high
                confirmed = float(confirm.close) > float(sweep.high) and float(confirm.close) > float(confirm.open)
                stop = min(float(sweep.low), low) * (1 - 0.0005)
                entry = float(confirm.close)
                target = _nearest_target(opposing, entry, direction)
                risk = entry - stop
                reward = target - entry if target is not None else 0
            else:
                swept = float(sweep.high) > high and float(sweep.close) < low
                confirmed = float(confirm.close) < float(sweep.low) and float(confirm.close) < float(confirm.open)
                stop = max(float(sweep.high), high) * (1 + 0.0005)
                entry = float(confirm.close)
                target = _nearest_target(opposing, entry, direction)
                risk = stop - entry
                reward = entry - target if target is not None else 0
            if not (swept and confirmed and risk > 0 and reward >= 2 * risk):
                continue
            event_time = pd.Timestamp(bars.index[-1])
            event_time = event_time.tz_localize("UTC") if event_time.tzinfo is None else event_time.tz_convert("UTC")
            out.append({
                "symbol": symbol, "direction": direction,
                "setup_type": "DNS_LIQUIDITY_SWEEP_RECLAIM",
                "zone_id": zone["zone_id"], "zone_side": side,
                "zone_low": low, "zone_high": high,
                "zone_timeframe": zone["timeframe"], "zone_quality": zone["quality"],
                "entry": entry, "stop_loss": stop, "take_profit": target,
                "rr": reward / risk, "event_candle": event_time.isoformat(),
                "map_revision": snapshot.get("revision"),
                "status": "PAPER_CANDIDATE",
            })
    return out
