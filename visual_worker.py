"""Opt-in visual-first paper worker with independent setup comparison.

The model chooses the market hypothesis from fresh multi-timeframe chart images.
This module only validates data integrity and mechanical risk; it never constructs
market structure, zones, or candidate rankings.
"""
import hashlib
import json
import math
import os
import uuid
from pathlib import Path

import pandas as pd

import config as C
import data
import discord
import main
import state as st
import visual_first_analyst
from visual_chart import render_symbol_chart


TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d", "1w")
MIN_STOP_ATR = 0.35
MAX_STOP_ATR = 2.5
OPPOSING_SIGNAL_TIE_MARGIN = 8
FAILURE_COOLDOWN_MINUTES = 30


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _finite_positive(value):
    """Accept JSON numbers only; reject bools, strings, NaN and infinity."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _atr(frame, period=14, timeframe=None):
    if frame is None or len(frame) < period + 1:
        return None
    if timeframe is not None:
        minutes = data.MINUTES.get(timeframe)
        if minutes is None:
            return None
        recent_index = pd.DatetimeIndex(frame.index[-(period + 1):])
        if len(recent_index) != period + 1:
            return None
        intervals = recent_index.to_series().diff().dropna()
        if not intervals.eq(pd.Timedelta(minutes=minutes)).all():
            return None
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)
    value = float(true_range.tail(period).mean())
    return value if math.isfinite(value) and value > 0 else None


def _watermarks(frames):
    result = {}
    for timeframe in TIMEFRAMES:
        frame = frames.get(timeframe)
        if frame is None or frame.empty:
            raise ValueError(f"missing {timeframe} frame for visual analysis")
        opened = pd.Timestamp(frame.index[-1])
        opened = opened.tz_localize("UTC") if opened.tzinfo is None else opened.tz_convert("UTC")
        result[timeframe] = (opened + pd.Timedelta(minutes=data.MINUTES[timeframe])).isoformat()
    return result


def _validate_candidate(candidate, current_price, frames):
    if not isinstance(candidate, dict):
        return None, "candidate is not an object"
    candidate_id = candidate.get("candidate_id")
    family = candidate.get("setup_family")
    direction = candidate.get("direction")
    trigger_tf = candidate.get("trigger_timeframe")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        return None, "candidate ID is missing"
    if family not in visual_first_analyst.SETUP_FAMILIES:
        return None, "unknown setup family"
    if direction not in ("LONG", "SHORT"):
        return None, "invalid direction"
    if trigger_tf not in TIMEFRAMES:
        return None, "invalid trigger timeframe"
    if candidate.get("entry_type") != "MARKET":
        return None, "candidate requires a future limit/retest/conditional entry"

    entry = _finite_positive(current_price)
    stop = _finite_positive(candidate.get("stop_loss"))
    target = _finite_positive(candidate.get("target_1"))
    zone = candidate.get("entry_zone")
    if entry is None or stop is None or target is None or not isinstance(zone, dict):
        return None, "candidate contains missing or invalid price levels"
    zone_low = _finite_positive(zone.get("low"))
    zone_high = _finite_positive(zone.get("high"))
    if zone_low is None or zone_high is None or zone_low >= zone_high:
        return None, "candidate entry zone has invalid bounds"
    if zone.get("timeframe") not in TIMEFRAMES or not str(zone.get("evidence", "")).strip():
        return None, "candidate entry zone is missing timeframe evidence"
    zone_gap = max(zone_low - entry, entry - zone_high, 0.0) / entry * 100.0
    if zone_gap > C.MAX_MARKET_ENTRY_DEVIATION_PCT:
        return None, "latest close is outside the configured entry-zone deviation"

    if direction == "LONG" and not stop < entry < target:
        return None, "LONG levels must satisfy stop < entry < target"
    if direction == "SHORT" and not target < entry < stop:
        return None, "SHORT levels must satisfy target < entry < stop"
    risk = entry - stop if direction == "LONG" else stop - entry
    reward = target - entry if direction == "LONG" else entry - target
    if risk <= 0:
        return None, "candidate risk is not positive"
    rr = reward / risk
    if not math.isfinite(rr) or rr < C.MIN_AI_RR:
        return None, f"candidate fails the minimum {C.MIN_AI_RR:.1f}R gate"
    reported_rr = _finite_positive(candidate.get("reward_risk"))
    if reported_rr is None or abs(reported_rr - rr) > max(0.02, rr * 0.02):
        return None, "reported reward/risk does not match the entry/stop/target"

    atr = _atr(frames.get(trigger_tf), timeframe=trigger_tf)
    if atr is None:
        return None, f"insufficient {trigger_tf} candles to calculate stop ATR"
    stop_atr = risk / atr
    if not math.isfinite(stop_atr) or not MIN_STOP_ATR <= stop_atr <= MAX_STOP_ATR:
        return None, f"stop distance {stop_atr:.3f} ATR is outside the 0.35–2.5 safety band"

    confidence = candidate.get("confidence")
    quality = candidate.get("quality_score")
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
        return None, "confidence must be an integer from 0 to 100"
    if isinstance(quality, bool) or not isinstance(quality, int) or not 0 <= quality <= 100:
        return None, "quality score must be an integer from 0 to 100"
    if confidence < C.MIN_AI_CONFIDENCE or quality < C.MIN_AI_CONFIDENCE:
        return None, f"confidence and quality must both meet {C.MIN_AI_CONFIDENCE}/100"

    evidence_tfs = candidate.get("evidence_timeframes")
    aligned_tfs = candidate.get("timeframes_in_agreement")
    if (
        not isinstance(evidence_tfs, list)
        or any(not isinstance(tf, str) or tf not in TIMEFRAMES for tf in evidence_tfs)
        or trigger_tf not in evidence_tfs
        or len(set(evidence_tfs)) < 2
    ):
        return None, "candidate must cite at least two chart timeframes including its trigger timeframe"
    if (
        not isinstance(aligned_tfs, list)
        or any(not isinstance(tf, str) or tf not in TIMEFRAMES for tf in aligned_tfs)
        or len(set(aligned_tfs)) < 2
    ):
        return None, "candidate must cite at least two distinct timeframe-alignment references"
    supporting = candidate.get("supporting_evidence")
    if not isinstance(supporting, list) or not supporting or any(not isinstance(x, str) or not x.strip() for x in supporting):
        return None, "candidate lacks specific supporting chart evidence"
    for field in ("trigger_condition", "higher_timeframe_context", "target_rationale", "invalidation", "selection_rationale"):
        if not isinstance(candidate.get(field), str) or not candidate[field].strip():
            return None, f"candidate is missing {field}"
    cancel_if = candidate.get("cancel_if")
    if not isinstance(cancel_if, list) or not cancel_if or any(not isinstance(x, str) or not x.strip() for x in cancel_if):
        return None, "candidate lacks explicit pre-entry cancellation conditions"
    conflicts = candidate.get("conflicting_evidence", [])
    if not isinstance(conflicts, list) or any(not isinstance(x, str) for x in conflicts):
        return None, "candidate conflicting_evidence must be a string list"

    return {
        "candidate_id": candidate_id,
        "setup_family": family,
        "setup_type": family,
        "dir": direction.lower(),
        "entry": entry,
        "sl": stop,
        "tp": target,
        "tp2": None,
        "rr": rr,
        "atr": atr,
        "stop_atr": stop_atr,
        "confidence": confidence,
        "quality_score": quality,
        "entry_zone": {
            "low": zone_low,
            "high": zone_high,
            "timeframe": zone["timeframe"],
            "evidence": zone["evidence"],
        },
        "trigger_timeframe": trigger_tf,
        "trigger_condition": candidate["trigger_condition"],
        "higher_timeframe_context": candidate["higher_timeframe_context"],
        "supporting_evidence": supporting,
        "evidence_timeframes": evidence_tfs,
        "conflicting_evidence": conflicts,
        "timeframes_in_agreement": aligned_tfs,
        "target_rationale": candidate["target_rationale"],
        "invalidation": candidate["invalidation"],
        "cancel_if": cancel_if,
        "rationale": candidate["selection_rationale"],
    }, "validated"


def validate_analysis(analysis, current_price, frames, expected_watermarks,
                      has_open_position=False, now=None):
    """Validate the model-selected candidate; never substitute a different candidate."""
    if not isinstance(analysis, dict):
        return None, "symbol analysis is not an object"
    symbol = analysis.get("symbol")
    if not isinstance(symbol, str) or symbol not in C.SYMBOLS:
        return None, "analysis contains an unknown symbol"
    if analysis.get("chart_watermarks") != expected_watermarks:
        return None, "chart watermarks are missing, stale or mismatched"
    try:
        as_of = pd.Timestamp(analysis.get("as_of_utc"))
        as_of = as_of.tz_localize("UTC") if as_of.tzinfo is None else as_of.tz_convert("UTC")
        reference = main._utc_now(now)
        age_minutes = (reference - as_of).total_seconds() / 60.0
        if age_minutes < -2 or age_minutes > 2:
            return None, "visual analysis timestamp is stale or in the future"
    except (TypeError, ValueError, OverflowError):
        return None, "visual analysis timestamp is invalid"
    if has_open_position:
        return None, "an open or pending paper position already exists for this symbol"
    if not isinstance(analysis.get("comparison_summary"), str) or not analysis["comparison_summary"].strip():
        return None, "candidate comparison summary is missing"

    action = analysis.get("action")
    selected_id = analysis.get("selected_candidate_id")
    candidates = analysis.get("candidates")
    if not isinstance(candidates, list):
        return None, "candidates must be a list"
    candidate_map = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return None, "candidate list contains a non-object"
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip() or candidate_id in candidate_map:
            return None, "candidate IDs are missing or duplicated"
        candidate_map[candidate_id] = candidate

    if action == "NO_TRADE":
        if selected_id is not None:
            return None, "NO_TRADE response must have a null selected_candidate_id"
        return None, "AI selected NO_TRADE"
    if action != "TRADE" or not isinstance(selected_id, str) or not selected_id:
        return None, "TRADE response must select exactly one candidate ID"

    viable = {}
    rejections = {}
    for candidate_id, candidate in candidate_map.items():
        plan, reason = _validate_candidate(candidate, current_price, frames)
        if plan is None:
            rejections[candidate_id] = reason
        else:
            viable[candidate_id] = (plan, candidate)

    if selected_id not in candidate_map:
        return None, "selected candidate ID is not present in candidates"
    if selected_id not in viable:
        return None, f"selected candidate failed validation: {rejections.get(selected_id, 'invalid candidate')}"

    selected_plan, selected_candidate = viable[selected_id]
    # The visual model owns setup comparison and selection. This layer validates
    # the chosen candidate; it must never substitute or re-rank market hypotheses.
    for other_id, (other_plan, _) in viable.items():
        if other_id == selected_id:
            continue
        if other_plan["dir"] != selected_plan["dir"]:
            # Do not replace the model's choice with a coded alternative. Fail closed
            # unless the model-selected side is clearly stronger than every opposite
            # actionable candidate by the configured quality margin.
            if other_plan["quality_score"] > selected_plan["quality_score"] - OPPOSING_SIGNAL_TIE_MARGIN:
                return None, "opposing actionable candidates are not clearly separated in quality; fail-closed NO_TRADE"

    selected_plan["comparison_summary"] = analysis["comparison_summary"]
    return selected_plan, "validated"


def _append_research(record):
    path = Path(os.environ.get("VISUAL_FIRST_RESEARCH_PATH", "research/visual_first_decisions.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())



def _persist_chart_images(chart_images, cycle_id, chart_watermarks, chart_hashes, now):
    """Persist raw chart PNGs and a hash/watermark manifest for later audit."""
    if (
        not isinstance(cycle_id, str)
        or len(cycle_id) != 24
        or any(char not in "0123456789abcdef" for char in cycle_id)
    ):
        raise ValueError("visual chart cycle_id must be a 24-character lowercase SHA-256 prefix")

    root = Path(os.environ.get("VISUAL_FIRST_CHART_DIR", "visual_artifacts"))
    cycle_dir = root / cycle_id
    cycle_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "cycle_id": cycle_id,
        "created_at_utc": pd.Timestamp(now).isoformat(),
        "charts": [],
    }

    for symbol in sorted(chart_images):
        if symbol not in C.SYMBOLS:
            raise ValueError(f"unknown symbol in visual chart artifact: {symbol}")
        image = chart_images[symbol]
        if not isinstance(image, (bytes, bytearray)) or not image:
            raise ValueError(f"empty visual chart artifact for {symbol}")
        image_bytes = bytes(image)
        digest = hashlib.sha256(image_bytes).hexdigest()
        if chart_hashes.get(symbol) != digest:
            raise ValueError(f"visual chart hash mismatch for {symbol}")
        watermarks = chart_watermarks.get(symbol)
        if not isinstance(watermarks, dict) or set(watermarks) != set(TIMEFRAMES):
            raise ValueError(f"incomplete visual chart watermarks for {symbol}")

        filename = f"{symbol}.png"
        target = cycle_dir / filename
        temporary = target.with_name(target.name + ".tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(image_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

        manifest["charts"].append({
            "symbol": symbol,
            "file": filename,
            "sha256": digest,
            "chart_watermarks": watermarks,
        })

    manifest_path = cycle_dir / "manifest.json"
    temporary = manifest_path.with_name(manifest_path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, manifest_path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return str(cycle_dir)


def _set_failure_cooldown(state, now):
    try:
        minutes = max(5, int(os.environ.get("VISUAL_FIRST_FAILURE_COOLDOWN_MINUTES", FAILURE_COOLDOWN_MINUTES)))
    except (TypeError, ValueError):
        minutes = FAILURE_COOLDOWN_MINUTES
    state["visual_ai_cooldown_until"] = (now + pd.Timedelta(minutes=minutes)).isoformat()


def _retry_pending_visual_alerts(state, frames_by_symbol, now):
    pending = state.setdefault("pending_visual_alerts", {})
    positions = state.setdefault("positions", {})
    changed = False
    delivered = 0
    dropped = 0
    for signal_id, trade in list(pending.items()):
        try:
            age = now - pd.Timestamp(trade.get("analysis_time", now.isoformat()))
        except (TypeError, ValueError):
            age = pd.Timedelta.max
        if age > pd.Timedelta(minutes=10):
            del pending[signal_id]
            dropped += 1
            changed = True
            continue
        symbol = trade.get("sym")
        frames = frames_by_symbol.get(symbol)
        if symbol not in C.SYMBOLS or frames is None:
            continue
        other_open = (
            [item for key, item in positions.items() if key != signal_id]
            + list(state.get("pending_alerts", {}).values())
            + [item for key, item in pending.items() if key != signal_id]
        )
        if any(item.get("sym") == symbol for item in other_open):
            del pending[signal_id]
            dropped += 1
            changed = True
            continue
        candidate = trade.get("_candidate")
        current_price = float(frames["5m"].iloc[-1].close)
        plan, reason = _validate_candidate(candidate, current_price, frames)
        if plan is None:
            del pending[signal_id]
            dropped += 1
            changed = True
            print(f"[visual-first-expired] {symbol} {signal_id}: {reason}", flush=True)
            continue
        latest_close = pd.Timestamp(frames["5m"].index[-1]) + pd.Timedelta(minutes=5)
        refreshed = {
            **trade,
            **plan,
            "signal_id": signal_id,
            "sym": symbol,
            "triggered_at": latest_close.isoformat(),
            "analysis_time": now.isoformat(),
            "status": "OPEN",
        }
        try:
            sent = discord.send_visual_trade(
                symbol, refreshed, lambda value, s=symbol: main._fmt(s, value)
            )
        except Exception as exc:
            sent = False
            print(f"[visual-first-alert-error] {type(exc).__name__}; delivery will be retried", flush=True)
        if sent:
            final_trade = {key: value for key, value in refreshed.items() if key != "_candidate"}
            positions[signal_id] = final_trade
            del pending[signal_id]
            delivered += 1
            changed = True
            print(
                f"[visual-first-signal] {symbol} {plan['dir'].upper()} "
                f"{plan['setup_family']} {plan['rr']:.2f}R paper-only",
                flush=True,
            )
        else:
            pending[signal_id] = refreshed
            changed = True
    if changed:
        st.save(state)
    return {"delivered": delivered, "dropped": dropped}


def run(now=None, fetcher=data.fetch, analyzer=None, enabled=None, frames_loader=None):
    """Run one visual-first paper-analysis cycle. Disabled unless explicitly opted in."""
    if enabled is None:
        enabled = _truthy(os.environ.get("ENABLE_VISUAL_PAPER"))
    if not enabled:
        print("[visual-first] disabled; set ENABLE_VISUAL_PAPER=true for an explicit paper-only run", flush=True)
        return {"status": "disabled", "analyzed": 0, "signals": 0}

    now = main._utc_now(now)
    state = st.load()
    for signal_id, outcome in list(state.setdefault("pending_outcomes", {}).items()):
        symbol = outcome.get("sym")
        if symbol in C.SYMBOLS and discord.send_outcome(
            outcome, lambda value, s=symbol: main._fmt(s, value)
        ):
            del state["pending_outcomes"][signal_id]

    frames_by_symbol = {}
    chart_images = {}
    chart_watermarks = {}
    candle_watermarks = {}
    chart_hashes = {}
    for symbol, cfg in C.SYMBOLS.items():
        try:
            if frames_loader is None:
                frames = data.fetch_bundle(cfg, now, fetcher=fetcher, symbol=symbol)
            else:
                frames = frames_loader(cfg, now, symbol)
            five_minute = frames.get("5m")
            if five_minute is not None and not five_minute.empty:
                main.manage_positions(
                    state, symbol, five_minute, now,
                    lambda value, s=symbol: main._fmt(s, value)
                )
            usable, reason = data.freshness(frames, now)
            if not usable:
                print(f"[visual-first-skip] {symbol}: {reason}", flush=True)
                continue
            frames_by_symbol[symbol] = frames
            candle_ts = pd.Timestamp(five_minute.index[-1]).isoformat()
            candle_watermarks[symbol] = candle_ts
            if state.setdefault("last_visual_candle", {}).get(symbol) == candle_ts:
                continue
            image = render_symbol_chart(
                f"{symbol} · {cfg['delta_symbol']}", frames, now
            )
            if not isinstance(image, (bytes, bytearray)) or not image:
                raise ValueError("chart renderer returned an empty image")
            image = bytes(image)
            chart_images[symbol] = image
            chart_watermarks[symbol] = _watermarks(frames)
            chart_hashes[symbol] = hashlib.sha256(image).hexdigest()
        except Exception as exc:
            print(f"[visual-first-data-error] {symbol}: {type(exc).__name__}: {exc}", flush=True)

    pending_delivery = _retry_pending_visual_alerts(state, frames_by_symbol, now)
    if not frames_by_symbol:
        st.save(state)
        return {"status": "no_fresh_data", "analyzed": 0, "signals": pending_delivery["delivered"]}
    if not chart_images:
        st.save(state)
        print("[visual-first] no new closed 5m candle; no repeated model request", flush=True)
        return {"status": "no_new_candle", "analyzed": 0, "signals": pending_delivery["delivered"]}

    cooldown_raw = state.get("visual_ai_cooldown_until")
    if cooldown_raw:
        try:
            cooldown_until = pd.Timestamp(cooldown_raw)
            cooldown_until = cooldown_until.tz_localize("UTC") if cooldown_until.tzinfo is None else cooldown_until.tz_convert("UTC")
            if now < cooldown_until:
                st.save(state)
                print("[visual-first] model failure cooldown active; no new alert decisions", flush=True)
                return {"status": "cooldown", "analyzed": 0, "signals": pending_delivery["delivered"]}
        except (TypeError, ValueError):
            state.pop("visual_ai_cooldown_until", None)

    cycle_payload = {
        symbol: chart_watermarks[symbol] for symbol in sorted(chart_watermarks)
    }
    cycle_id = hashlib.sha256(
        json.dumps(cycle_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    try:
        chart_artifact_dir = _persist_chart_images(
            chart_images, cycle_id, chart_watermarks, chart_hashes, now
        )
    except Exception as exc:
        st.save(state)
        print(
            f"[visual-first] chart artifact persistence failed ({type(exc).__name__}); "
            "no new signals created",
            flush=True,
        )
        return {"status": "image_persistence_error", "analyzed": 0, "signals": pending_delivery["delivered"]}
    market_context = main.build_context({
        symbol: frames_by_symbol[symbol] for symbol in chart_images
    })
    market_context["_visual_first"] = {
        "schema_version": 2,
        "cycle_id": cycle_id,
        "as_of_utc": now.isoformat(),
        "chart_watermarks": chart_watermarks,
        "chart_sha256": chart_hashes,
        "chart_timeframes": list(TIMEFRAMES),
    }
    active_trades = (
        list(state.get("positions", {}).values())
        + list(state.get("pending_alerts", {}).values())
        + list(state.get("pending_visual_alerts", {}).values())
    )
    active = {
        item.get("sym"): {
            "direction": item.get("dir"),
            "entry": item.get("entry"),
            "stop_loss": item.get("sl"),
            "take_profit": item.get("tp"),
            "signal_id": item.get("signal_id"),
        }
        for item in active_trades if item.get("sym")
    }
    call_analyser = analyzer or visual_first_analyst.analyse
    try:
        result, meta = call_analyser(chart_images, market_context, active_positions=active)
        analyses = visual_first_analyst.validate_response_coverage(
            result, set(chart_images), cycle_id
        )
        meta = meta if isinstance(meta, dict) else {}
    except Exception as exc:
        state["visual_ai_cooldown_until"] = None
        _set_failure_cooldown(state, now)
        try:
            _append_research({
                "kind": "VISUAL_FIRST_ERROR",
                "timestamp": now.isoformat(),
                "cycle_id": cycle_id,
                "chart_watermarks": chart_watermarks,
                "chart_sha256": chart_hashes,
                "chart_artifact_dir": chart_artifact_dir,
                "error_type": type(exc).__name__,
                "error": str(exc)[:400],
            })
        except OSError:
            print("[visual-first] decision-log persistence failed; no signal can be sent", flush=True)
        st.save(state)
        return {"status": "analysis_error", "analyzed": 0, "signals": pending_delivery["delivered"]}

    validation = {}
    new_pending = {}
    for symbol in chart_images:
        analysis = analyses[symbol]
        current_price = float(frames_by_symbol[symbol]["5m"].iloc[-1].close)
        has_position = any(item.get("sym") == symbol for item in active_trades)
        plan, reason = validate_analysis(
            analysis,
            current_price,
            frames_by_symbol[symbol],
            chart_watermarks[symbol],
            has_open_position=has_position,
            now=now,
        )
        validation[symbol] = {
            "status": "VALIDATED" if plan is not None else "NO_TRADE",
            "reason": reason,
            "selected_candidate_id": analysis.get("selected_candidate_id"),
            "action": analysis.get("action"),
        }
        if plan is None:
            continue
        signal_id = uuid.uuid4().hex[:12].upper()
        signal_ts = pd.Timestamp(candle_watermarks[symbol]) + pd.Timedelta(minutes=5)
        trade = {
            **plan,
            "signal_id": signal_id,
            "sym": symbol,
            "triggered_at": signal_ts.isoformat(),
            "status": "OPEN",
            "entry_source": "VISUAL_FIRST_PAPER",
            "model": meta.get("model") if isinstance(meta, dict) else None,
            "cycle_id": cycle_id,
            "chart_watermarks": chart_watermarks[symbol],
            "chart_sha256": chart_hashes[symbol],
            "analysis_time": now.isoformat(),
            "_candidate": next(
                candidate for candidate in analysis["candidates"]
                if candidate["candidate_id"] == plan["candidate_id"]
            ),
        }
        new_pending[signal_id] = trade

    try:
        _append_research({
            "kind": "VISUAL_FIRST_ANALYSIS",
            "timestamp": now.isoformat(),
            "cycle_id": cycle_id,
            "model": meta.get("model") if isinstance(meta, dict) else None,
            "response_id": meta.get("response_id") if isinstance(meta, dict) else None,
            "usage": meta.get("usage") if isinstance(meta, dict) else None,
            "market_context": market_context,
            "chart_watermarks": chart_watermarks,
            "chart_sha256": chart_hashes,
            "chart_artifact_dir": chart_artifact_dir,
            "analysis": result,
            "validation": validation,
        })
    except OSError as exc:
        st.save(state)
        print(f"[visual-first] research log failed ({type(exc).__name__}); no signals created", flush=True)
        return {"status": "persistence_error", "analyzed": 0, "signals": pending_delivery["delivered"]}

    for symbol, candle_ts in candle_watermarks.items():
        if symbol in chart_images:
            state.setdefault("last_visual_candle", {})[symbol] = candle_ts
    state.pop("visual_ai_cooldown_until", None)
    state.setdefault("pending_visual_alerts", {}).update(new_pending)
    state["last_visual_analysis_at"] = now.isoformat()
    st.save(state)

    delivery = _retry_pending_visual_alerts(state, frames_by_symbol, now)
    return {
        "status": "ok",
        "analyzed": len(chart_images),
        "signals": delivery["delivered"],
        "pending": len(state.get("pending_visual_alerts", {})),
        "no_trade": sum(1 for item in validation.values() if item["status"] == "NO_TRADE"),
        "cycle_id": cycle_id,
    }


if __name__ == "__main__":
    run()
