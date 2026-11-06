"""Persistent AI-authored DNS map and deterministic local setup watcher.

The AI owns visual zone discovery. This module only validates/persists that map and
checks closed candles against it; it never invents or widens a demand/supply zone.
"""
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

import config as C

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
    """Refresh on age or a confirmed close through a zone on its own timeframe."""
    if not snapshot:
        return ["NO_EXISTING_MAP"]
    stamp = pd.Timestamp(snapshot.get("mapped_at"))
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    current = pd.Timestamp(now)
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    reasons = []
    if current - stamp >= pd.Timedelta(hours=MAP_REFRESH_HOURS):
        reasons.append("SCHEDULED_REFRESH")
    zones = snapshot.get("demand_zones", []) + snapshot.get("supply_zones", [])
    for zone in zones:
        if zone.get("status") != "ACTIVE":
            continue
        zone_frame = frames.get(zone.get("timeframe"))
        if zone_frame is None or zone_frame.empty:
            continue
        close = float(zone_frame.iloc[-1].close)
        if zone["side"] == "DEMAND" and close < float(zone["low"]):
            reasons.append("DEMAND_ZONE_BROKEN")
            break
        if zone["side"] == "SUPPLY" and close > float(zone["high"]):
            reasons.append("SUPPLY_ZONE_BROKEN")
            break
    return list(dict.fromkeys(reasons))


def _nearest_target(zones, entry, direction):
    """Use the nearest active, visually mapped opposing DNS band as the target."""
    candidates = []
    for zone in zones or []:
        if not isinstance(zone, dict) or zone.get("status") != "ACTIVE":
            continue
        try:
            quality = int(zone.get("quality", 0))
            low, high = float(zone["low"]), float(zone["high"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if quality < MIN_ZONE_QUALITY or not math.isfinite(low + high) or not (0 < low < high):
            continue
        level = low if direction == "LONG" else high
        if direction == "LONG" and level > entry:
            candidates.append(level)
        elif direction == "SHORT" and level < entry:
            candidates.append(level)
    if not candidates:
        return None
    return min(candidates) if direction == "LONG" else max(candidates)


def _zone_frame_is_valid(zone, frames, side):
    """Fail closed when the zone's own timeframe is missing or has closed through it."""
    frame = frames.get(zone.get("timeframe"))
    if frame is None or frame.empty or "close" not in frame:
        return False
    try:
        close = float(frame.iloc[-1].close)
        low, high = float(zone["low"]), float(zone["high"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    if not all(math.isfinite(x) for x in (close, low, high)):
        return False
    return not ((side == "DEMAND" and close < low) or (side == "SUPPLY" and close > high))


def _zone_gap_pct(entry, low, high):
    if entry <= 0 or not all(math.isfinite(x) for x in (entry, low, high)):
        return math.inf
    return max(low - entry, entry - high, 0.0) / entry * 100.0


def _candidate_for_trigger(
    symbol, frames, snapshot, zone, side, setup_type, stop, rationale
):
    """Apply common DNS anchoring, opposing-zone target and >=2R gates."""
    m5 = frames.get("5m")
    if m5 is None or m5.empty or len(m5) < 3:
        return None
    try:
        low, high = float(zone["low"]), float(zone["high"])
        entry = float(m5.iloc[-1].close)
        stop = float(stop)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not (0 < low < high and entry > 0 and stop > 0):
        return None
    if not all(math.isfinite(x) for x in (low, high, entry, stop)):
        return None
    if _zone_gap_pct(entry, low, high) > C.MAX_MARKET_ENTRY_DEVIATION_PCT:
        return None

    direction = "LONG" if side == "DEMAND" else "SHORT"
    opposing = snapshot.get("supply_zones", []) if direction == "LONG" else snapshot.get("demand_zones", [])
    target = _nearest_target(opposing, entry, direction)
    if target is None:
        return None
    risk = entry - stop if direction == "LONG" else stop - entry
    reward = target - entry if direction == "LONG" else entry - target
    if not (math.isfinite(risk) and math.isfinite(reward) and risk > 0 and reward >= 2.0 * risk):
        return None

    event_time = pd.Timestamp(m5.index[-1])
    event_time = event_time.tz_localize("UTC") if event_time.tzinfo is None else event_time.tz_convert("UTC")
    return {
        "symbol": symbol,
        "direction": direction,
        "setup_type": setup_type,
        "zone_id": zone["zone_id"],
        "zone_side": side,
        "zone_low": low,
        "zone_high": high,
        "zone_timeframe": zone["timeframe"],
        "zone_quality": int(zone["quality"]),
        "entry": entry,
        "stop_loss": stop,
        "take_profit": target,
        "rr": reward / risk,
        "event_candle": event_time.isoformat(),
        "map_revision": snapshot.get("revision"),
        "rationale": str(rationale)[:500],
        "invalidation": (
            "A move through the mapped demand band and structural stop invalidates the long setup."
            if side == "DEMAND" else
            "A move through the mapped supply band and structural stop invalidates the short setup."
        ),
        "status": "PAPER_CANDIDATE",
    }


def _recent_bars_contiguous(frame, count, minutes):
    if frame is None or len(frame) < count or not isinstance(frame.index, pd.DatetimeIndex):
        return False
    if frame.index.tz is None or not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        return False
    recent = frame.index[-count:]
    return len(recent) < 2 or bool(
        (recent.to_series().diff().dropna() == pd.Timedelta(minutes=minutes)).all()
    )


def _ema(series, period):
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def _atr(frame, period=14):
    previous = frame["close"].shift(1)
    tr = pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - previous).abs(),
        (frame["low"] - previous).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _is_bullish(row):
    return float(row.close) > float(row.open)


def _is_bearish(row):
    return float(row.close) < float(row.open)


def _touches_zone(row, low, high):
    return float(row.low) <= high and float(row.high) >= low


def _find_zone_setups(symbol, frames, snapshot, zone, side):
    """Detect distinct 5m confirmations at one AI-authored DNS band.

    Every setup uses only closed candles and passes the same final DNS proximity,
    opposing-zone target and 2R checks. This code never creates a zone.
    """
    m5 = frames.get("5m")
    if (
        m5 is None or len(m5) < 3
        or not _recent_bars_contiguous(m5, 3, 5)
        or not _zone_frame_is_valid(zone, frames, side)
    ):
        return []
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(m5.columns) or not isinstance(m5.index, pd.DatetimeIndex):
        return []
    if m5.index.tz is None or not m5.index.is_monotonic_increasing or m5.index.has_duplicates:
        return []
    try:
        low, high = float(zone["low"]), float(zone["high"])
        quality = int(zone["quality"])
        values = m5[["open", "high", "low", "close"]].tail(12).to_numpy(dtype=float)
    except (KeyError, TypeError, ValueError, OverflowError):
        return []
    if not (0 < low < high and 1 <= quality <= 5) or not values.size or not np.isfinite(values).all():
        return []
    if (values <= 0).any():
        return []
    tail = m5.tail(12)
    if (tail.high < tail[["open", "low", "close"]].max(axis=1)).any():
        return []
    if (tail.low > tail[["open", "high", "close"]].min(axis=1)).any():
        return []

    direction = "LONG" if side == "DEMAND" else "SHORT"
    last = m5.iloc[-1]
    previous = m5.iloc[-2]
    pad = max(float(last.close) * 0.0005, float(_atr(m5).iloc[-1]) * 0.08 if pd.notna(_atr(m5).iloc[-1]) else 0.0)
    if not math.isfinite(pad) or pad <= 0:
        pad = float(last.close) * 0.0005
    results = []

    def add(setup, stop, rationale):
        candidate = _candidate_for_trigger(
            symbol, frames, snapshot, zone, side, setup, stop, rationale
        )
        if candidate is not None:
            results.append(candidate)

    # 1) Liquidity sweep and reclaim: preserve the original strict two-candle trigger.
    sweep = m5.iloc[-2]
    sweep_triggered = False
    if side == "DEMAND":
        if (
            float(sweep.low) < low and float(sweep.close) > high
            and _is_bullish(last) and float(last.close) > float(sweep.high)
        ):
            sweep_triggered = True
            add(
                "DNS_LIQUIDITY_SWEEP_RECLAIM",
                min(float(sweep.low), low) - pad,
                "5m sell-side sweep below AI-mapped demand, close back above the band, then bullish confirmation beyond the sweep high.",
            )
    else:
        if (
            float(sweep.high) > high and float(sweep.close) < low
            and _is_bearish(last) and float(last.close) < float(sweep.low)
        ):
            sweep_triggered = True
            add(
                "DNS_LIQUIDITY_SWEEP_RECLAIM",
                max(float(sweep.high), high) + pad,
                "5m buy-side sweep above AI-mapped supply, close back below the band, then bearish confirmation beyond the sweep low.",
            )

    # 2) Zone rejection: the recent approach must actually trade into the AI band.
    recent = m5.iloc[-4:-1]
    touched = any(_touches_zone(row, low, high) for _, row in recent.iterrows())
    if side == "DEMAND":
        if not sweep_triggered and touched and _is_bullish(last) and float(last.close) > high and float(last.close) > float(previous.high):
            stop = min(float(row.low) for _, row in recent.iterrows()) - pad
            add("DNS_DEMAND_REJECTION", stop, "Recent 5m candles tested visually mapped demand; the latest bullish close reclaimed the band and broke the prior candle high.")
    else:
        if not sweep_triggered and touched and _is_bearish(last) and float(last.close) < low and float(last.close) < float(previous.low):
            stop = max(float(row.high) for _, row in recent.iterrows()) + pad
            add("DNS_SUPPLY_REJECTION", stop, "Recent 5m candles tested visually mapped supply; the latest bearish close rejected the band and broke the prior candle low.")

    # 3) BOS / CHOCH confirmation: first touch at DNS, then close through local swing.
    structure_window = m5.iloc[-9:-1]
    structure_touch = [
        idx for idx, row in structure_window.iterrows()
        if _touches_zone(row, low, high)
    ]
    if structure_touch and _recent_bars_contiguous(m5, 9, 5):
        prior_swing = m5.iloc[-6:-1]
        if side == "DEMAND":
            broken = float(last.close) > float(prior_swing.high.max()) and _is_bullish(last)
            if broken:
                touch_pos = m5.index.get_loc(structure_touch[0])
                segment = m5.iloc[touch_pos:]
                stop = float(segment.low.min()) - pad
                add("DNS_BOS_CHOCH_BULLISH", stop, "Price reacted from AI-mapped demand and the latest closed 5m candle broke the recent swing high, confirming bullish structure shift.")
        else:
            broken = float(last.close) < float(prior_swing.low.min()) and _is_bearish(last)
            if broken:
                touch_pos = m5.index.get_loc(structure_touch[0])
                segment = m5.iloc[touch_pos:]
                stop = float(segment.high.max()) + pad
                add("DNS_BOS_CHOCH_BEARISH", stop, "Price reacted from AI-mapped supply and the latest closed 5m candle broke the recent swing low, confirming bearish structure shift.")

    # 4) Trend pullback: higher-timeframe EMA alignment plus a 5m reclaim at the DNS band.
    m15 = frames.get("15m")
    if (
        m15 is not None and len(m15) >= 55
        and {"close", "open"}.issubset(m15.columns)
        and _recent_bars_contiguous(m5, 7, 5)
        and _recent_bars_contiguous(m15, 55, 15)
    ):
        ema20_15, ema50_15 = _ema(m15.close, 20).iloc[-1], _ema(m15.close, 50).iloc[-1]
        ema20_5 = _ema(m5.close, 20).iloc[-1]
        pullback_touch = any(_touches_zone(row, low, high) for _, row in m5.iloc[-7:-1].iterrows())
        if all(pd.notna(x) for x in (ema20_15, ema50_15, ema20_5)):
            if side == "DEMAND":
                trend_ok = float(ema20_15) > float(ema50_15) and float(m15.close.iloc[-1]) > float(ema20_15)
                reclaim = _is_bullish(last) and float(last.close) > float(ema20_5) and float(last.close) > float(previous.high)
                if trend_ok and pullback_touch and reclaim:
                    stop = float(m5.iloc[-7:].low.min()) - pad
                    add("DNS_TREND_PULLBACK", stop, "15m EMA20 is above EMA50; price pulled back into AI-mapped demand and the latest 5m candle reclaimed EMA20 with bullish follow-through.")
            else:
                trend_ok = float(ema20_15) < float(ema50_15) and float(m15.close.iloc[-1]) < float(ema20_15)
                reclaim = _is_bearish(last) and float(last.close) < float(ema20_5) and float(last.close) < float(previous.low)
                if trend_ok and pullback_touch and reclaim:
                    stop = float(m5.iloc[-7:].high.max()) + pad
                    add("DNS_TREND_PULLBACK", stop, "15m EMA20 is below EMA50; price pulled back into AI-mapped supply and the latest 5m candle rejected EMA20 with bearish follow-through.")

    # 5) FVG retrace: a genuine three-candle imbalance must overlap the mapped DNS band.
    atr5 = _atr(m5).iloc[-1]
    if pd.notna(atr5) and float(atr5) > 0 and _recent_bars_contiguous(m5, 12, 5):
        n = len(m5)
        for i in range(max(2, n - 10), n - 1):
            first, impulse, third = m5.iloc[i - 2], m5.iloc[i - 1], m5.iloc[i]
            if side == "DEMAND":
                gap_low, gap_high = float(first.high), float(third.low)
                displacement = _is_bullish(impulse) and (float(impulse.close) - float(impulse.open)) >= 0.6 * float(atr5)
                if gap_high <= gap_low or not displacement or min(gap_high, high) <= max(gap_low, low):
                    continue
                mitigated = float(last.low) <= gap_high and float(last.low) >= gap_low
                confirmed = _is_bullish(last) and float(last.close) > gap_high
                if mitigated and confirmed:
                    add("DNS_FVG_RETRACE", min(low, gap_low, float(last.low)) - pad, "A bullish three-candle fair-value gap overlaps AI-mapped demand; the latest 5m candle mitigated the gap and reclaimed above it.")
            else:
                gap_low, gap_high = float(third.high), float(first.low)
                displacement = _is_bearish(impulse) and (float(impulse.open) - float(impulse.close)) >= 0.6 * float(atr5)
                if gap_high <= gap_low or not displacement or min(gap_high, high) <= max(gap_low, low):
                    continue
                mitigated = float(last.high) >= gap_low and float(last.high) <= gap_high
                confirmed = _is_bearish(last) and float(last.close) < gap_low
                if mitigated and confirmed:
                    add("DNS_FVG_RETRACE", max(high, gap_high, float(last.high)) + pad, "A bearish three-candle fair-value gap overlaps AI-mapped supply; the latest 5m candle mitigated the gap and rejected below it.")

    # 6) RBS / SBR role reversal: a close through the mapped band, retest, then follow-through.
    reversal_history = m5.iloc[-8:]
    if len(reversal_history) >= 4 and _recent_bars_contiguous(m5, 8, 5):
        if side == "DEMAND":
            for j in range(1, len(reversal_history) - 1):
                before, breakout = reversal_history.iloc[j - 1], reversal_history.iloc[j]
                retest_rows = reversal_history.iloc[j + 1:-1]
                broke = float(before.close) <= high and float(breakout.close) > high and _is_bullish(breakout)
                held = (
                    not retest_rows.empty
                    and any(_touches_zone(row, low, high) and float(row.close) >= low for _, row in retest_rows.iterrows())
                )
                if broke and held and _is_bullish(last) and float(last.close) > float(previous.high):
                    stop = min(float(row.low) for _, row in retest_rows.iterrows()) - pad
                    add("DNS_RBS_RETEST", stop, "The mapped band changed from resistance to demand: price closed above it, retested the band, held, and confirmed with bullish 5m follow-through.")
                    break
        else:
            for j in range(1, len(reversal_history) - 1):
                before, breakout = reversal_history.iloc[j - 1], reversal_history.iloc[j]
                retest_rows = reversal_history.iloc[j + 1:-1]
                broke = float(before.close) >= low and float(breakout.close) < low and _is_bearish(breakout)
                held = (
                    not retest_rows.empty
                    and any(_touches_zone(row, low, high) and float(row.close) <= high for _, row in retest_rows.iterrows())
                )
                if broke and held and _is_bearish(last) and float(last.close) < float(previous.low):
                    stop = max(float(row.high) for _, row in retest_rows.iterrows()) + pad
                    add("DNS_SBR_RETEST", stop, "The mapped band changed from support to supply: price closed below it, retested the band, held, and confirmed with bearish 5m follow-through.")
                    break

    return results


def detect_local_setup(symbol, frames, snapshot, now=None):
    """Return independent DNS-anchored setup candidates from closed OHLCV candles.

    The visual AI map remains the only source of zones. Every sub-setup is a
    confirmation/refinement at that map, never a standalone mid-range signal.
    """
    if not isinstance(snapshot, dict) or not isinstance(frames, dict):
        return []
    out = []
    for side, key in (("DEMAND", "demand_zones"), ("SUPPLY", "supply_zones")):
        zones = snapshot.get(key, [])
        if not isinstance(zones, list):
            continue
        for zone in zones:
            if not isinstance(zone, dict) or zone.get("status") != "ACTIVE":
                continue
            try:
                quality = int(zone.get("quality", 0))
                low, high = float(zone["low"]), float(zone["high"])
                timeframe = str(zone["timeframe"])
                zone_id = str(zone["zone_id"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if quality < MIN_ZONE_QUALITY or quality > 5 or timeframe not in TIMEFRAMES:
                continue
            if not all(math.isfinite(x) for x in (low, high)) or not (0 < low < high) or not zone_id:
                continue
            out.extend(_find_zone_setups(symbol, frames, snapshot, zone, side))
    # De-duplicate a setup/zone at the same closed 5m event; retain the best R geometry.
    unique = {}
    for candidate in out:
        key = (candidate["zone_id"], candidate["setup_type"], candidate["event_candle"])
        previous = unique.get(key)
        if previous is None or candidate["rr"] > previous["rr"]:
            unique[key] = candidate
    return sorted(
        unique.values(),
        key=lambda item: (-item["zone_quality"], -item["rr"], item["setup_type"]),
    )
