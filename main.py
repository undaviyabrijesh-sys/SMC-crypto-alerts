"""Salty Quant AI: raw OHLCV -> chart images -> visual AI analysis -> validated execution alerts."""
import hashlib
import json
import math
import os
import uuid
from pathlib import Path

import pandas as pd

import ai_analyst
import config as C
import data
import discord
import daily_reports
import state as st
from visual_chart import render_symbol_chart


def _utc_now(value=None):
    now = pd.Timestamp(value) if value is not None else pd.Timestamp.now(tz="UTC")
    return now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")


def _fmt(symbol, value):
    digits = C.SYMBOLS[symbol].get("dp", 2)
    return f"{float(value):,.{digits}f}"


def build_context(frames_by_symbol):
    """Compact exact recent OHLCV accompanies the images for price-level precision."""
    limits = {"1w": 12, "1d": 18, "4h": 24, "1h": 30, "15m": 24, "5m": 24}
    context = {}
    for symbol, frames in frames_by_symbol.items():
        current = frames["5m"].iloc[-1]
        tf_data = {}
        for tf, limit in limits.items():
            df = frames[tf].tail(limit)
            rows = []
            for ts, row in df.iterrows():
                rows.append([
                    ts.isoformat(),
                    round(float(row.open), 8),
                    round(float(row.high), 8),
                    round(float(row.low), 8),
                    round(float(row.close), 8),
                    round(float(row.volume), 4)
                ])
            tf_data[tf] = rows
        instrument = C.SYMBOLS[symbol]["delta_symbol"]
        descriptions = {
            "BTC": "Bitcoin perpetual contract",
            "ETH": "Ethereum perpetual contract",
            "XAU": "Tether Gold Token perpetual contract (not spot XAUUSD)"
        }
        context[symbol] = {
            "venue": "Delta Exchange India",
            "instrument": instrument,
            "instrument_description": descriptions.get(symbol, "Delta perpetual contract"),
            "last_price": float(current.close),
            "last_closed_5m_candle": frames["5m"].index[-1].isoformat(),
            "timeframes": tf_data
        }
    return context


def build_recent_setup_feedback(trade_history, lookback_per_setup=30):
    """Summarize only already-closed paper outcomes; this is context, not a trained edge."""
    import math

    grouped = {}
    for trade in trade_history or []:
        if not isinstance(trade, dict) or not trade.get("exit_time"):
            continue
        setup = str(trade.get("setup_type", "OTHER")).upper()
        symbol = str(trade.get("sym", "UNKNOWN")).upper()
        try:
            value = float(trade.get("gross_R"))
            exit_time = _utc_now(trade["exit_time"])
        except (TypeError, ValueError, KeyError):
            continue
        if not math.isfinite(value):
            continue
        grouped.setdefault((symbol, setup), []).append(
            (exit_time, value, str(trade.get("status", "UNKNOWN")).upper())
        )

    feedback = {}
    for (symbol, setup), observations in grouped.items():
        observations.sort(key=lambda item: item[0])
        sample = observations[-lookback_per_setup:]
        values = [item[1] for item in sample]
        count = len(values)
        feedback[f"{symbol}|{setup}"] = {
            "closed_paper_trades": count,
            "wins": sum(value > 0 for value in values),
            "losses": sum(value < 0 for value in values),
            "win_rate_pct": round(100.0 * sum(value > 0 for value in values) / count, 1),
            "mean_gross_R": round(sum(values) / count, 3),
            "sum_gross_R": round(sum(values), 3),
            "sample_reliability": "LOW_SAMPLE" if count < 20 else "OBSERVATIONAL_ONLY",
            "last_exit_utc": sample[-1][0].isoformat(),
        }
    return feedback


def validate_trade(analysis, current_price, has_open_position=False):
    """Mechanical safety gate; it validates an AI plan but never creates a setup or zone."""
    if analysis.get("action") != "TRADE":
        return None, "AI decision is NO_TRADE"
    if has_open_position:
        return None, "an open paper position already exists for this symbol"
    if analysis.get("direction") not in ("LONG", "SHORT"):
        return None, "missing or invalid direction"
    if analysis.get("entry_mode") != "MARKET":
        return None, "only immediately actionable market entries are supported in this release"
    try:
        model_entry = float(analysis["entry"])
        sl = float(analysis["stop_loss"])
        tp1 = float(analysis["take_profit_1"])
        current_price = float(current_price)
    except (TypeError, ValueError, KeyError):
        return None, "entry, stop-loss or first target is missing"
    if not all(math.isfinite(value) for value in (model_entry, sl, tp1, current_price)):
        return None, "price levels must be finite"
    if min(model_entry, sl, tp1, current_price) <= 0:
        return None, "non-positive price level"
    deviation_pct = abs(model_entry - current_price) / current_price * 100
    if deviation_pct > C.MAX_MARKET_ENTRY_DEVIATION_PCT:
        return None, f"AI entry is {deviation_pct:.2f}% away from the latest close"

    # The paper fill uses the actual latest closed candle close, not a guessed visual price.
    entry = current_price
    direction = analysis["direction"]
    if direction == "LONG" and not (sl < entry < tp1):
        return None, "LONG levels are not ordered SL < entry < TP"
    if direction == "SHORT" and not (tp1 < entry < sl):
        return None, "SHORT levels are not ordered TP < entry < SL"
    risk = abs(entry - sl)
    reward = abs(tp1 - entry)
    rr = reward / risk if risk else 0.0
    if rr < C.MIN_AI_RR:
        return None, f"validated reward/risk is only {rr:.2f}R"
    confidence = int(analysis.get("confidence", 0))
    if confidence < C.MIN_AI_CONFIDENCE:
        return None, f"confidence {confidence} is below the configured gate"

    selected_zone = analysis.get("selected_entry_zone")
    if not isinstance(selected_zone, dict):
        return None, "AI trade is missing its selected entry zone"
    try:
        zone_low = float(selected_zone["low"])
        zone_high = float(selected_zone["high"])
        zone_timeframe = selected_zone["timeframe"]
        zone_evidence = str(selected_zone["evidence"])
    except (TypeError, ValueError, KeyError):
        return None, "AI selected entry zone is incomplete"
    if not all(math.isfinite(value) for value in (zone_low, zone_high)) or not (0 < zone_low < zone_high):
        return None, "AI selected entry zone has invalid price bounds"
    if zone_timeframe not in ("1w", "1d", "4h", "1h", "15m", "5m"):
        return None, "AI selected entry zone has an invalid timeframe"
    zone_gap = max(zone_low - entry, entry - zone_high, 0.0)
    zone_gap_pct = zone_gap / entry * 100
    if zone_gap_pct > C.MAX_MARKET_ENTRY_DEVIATION_PCT:
        return None, f"latest price is {zone_gap_pct:.2f}% away from the AI selected entry zone"

    # A sub-setup is not actionable unless its entry band overlaps a quality
    # demand zone for LONG or a quality supply zone for SHORT.
    expected_zone_side = "DEMAND" if direction == "LONG" else "SUPPLY"
    directional_zones = analysis.get("demand_zones" if direction == "LONG" else "supply_zones")
    if not isinstance(directional_zones, list):
        directional_zones = []
    primary_zone = None
    for candidate in directional_zones:
        if not isinstance(candidate, dict):
            continue
        try:
            primary_low = float(candidate["low"])
            primary_high = float(candidate["high"])
            primary_quality = int(candidate.get("quality", 0))
            primary_timeframe = str(candidate["timeframe"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            not math.isfinite(primary_low)
            or not math.isfinite(primary_high)
            or not (0 < primary_low < primary_high)
            or primary_timeframe not in ("1w", "1d", "4h", "1h", "15m", "5m")
            or primary_quality < C.MIN_DNS_ZONE_QUALITY
            or primary_quality > 5
        ):
            continue
        overlap = min(zone_high, primary_high) - max(zone_low, primary_low)
        if overlap <= 0:
            continue
        distance = max(primary_low - entry, entry - primary_high, 0.0) / entry * 100
        if distance > C.MAX_MARKET_ENTRY_DEVIATION_PCT:
            continue
        primary_zone = {
            "side": expected_zone_side,
            "low": primary_low,
            "high": primary_high,
            "timeframe": primary_timeframe,
            "quality": primary_quality,
            "evidence": str(candidate.get("evidence", "")),
        }
        break
    if primary_zone is None:
        return None, (
            f"{direction} trade lacks a nearby quality >= {C.MIN_DNS_ZONE_QUALITY} "
            f"{expected_zone_side.lower()} zone overlapping the selected entry band"
        )

    tp2 = analysis.get("take_profit_2")
    if tp2 is not None:
        try:
            tp2 = float(tp2)
            if (
                not math.isfinite(tp2)
                or (direction == "LONG" and tp2 <= tp1)
                or (direction == "SHORT" and tp2 >= tp1)
            ):
                tp2 = None
        except (TypeError, ValueError):
            tp2 = None

    return {
        "dir": direction.lower(),
        "entry": entry,
        "sl": sl,
        "tp": tp1,
        "tp2": tp2,
        "rr": rr,
        "confidence": confidence,
        "setup_type": analysis.get("setup_type", "OTHER"),
        "bias": analysis.get("bias", "UNCLEAR"),
        "rationale": analysis.get("rationale", ""),
        "invalidation": analysis.get("invalidation", ""),
        "selected_entry_zone": {
            "low": zone_low,
            "high": zone_high,
            "timeframe": zone_timeframe,
            "evidence": zone_evidence
        },
        "primary_zone": primary_zone,
        "zones": {
            "demand": analysis.get("demand_zones", []),
            "supply": analysis.get("supply_zones", []),
            "liquidity": analysis.get("liquidity_levels", [])
        },
        "timeframes_in_agreement": analysis.get("timeframes_in_agreement", [])
    }, "validated"


def manage_positions(state, sym, m5, now, fmt):
    """Paper-track AI alerts on fully closed 5m candles; conservative SL-first same-bar handling."""
    positions = state.setdefault("positions", {})
    if m5 is None or m5.empty:
        return
    for signal_id, trade in list(positions.items()):
        if trade.get("sym") != sym:
            continue
        # triggered_at is the actual entry time: the close of the signal candle.
        # The next 5m candle opens at that exact timestamp and is eligible for tracking.
        triggered_at = pd.Timestamp(trade["triggered_at"])
        expiry_at = triggered_at + pd.Timedelta(hours=C.TRADE_MAX_HOURS)
        # Candle timestamps are bar-open times. Only bars that close by expiry
        # may trigger TP/SL; a later bar must not retroactively change the exit.
        latest_eligible_open = expiry_at - pd.Timedelta(minutes=5)
        future = m5[(m5.index >= triggered_at) & (m5.index <= latest_eligible_open)]
        is_long = trade["dir"] == "long"
        exit_price = None
        outcome = None
        exit_ts = None
        for ts, bar in future.iterrows():
            op, hi, lo = float(bar.open), float(bar.high), float(bar.low)
            sl, tp = float(trade["sl"]), float(trade["tp"])
            if is_long:
                if op <= sl:
                    exit_price, outcome = op, "SL"
                elif op >= tp:
                    exit_price, outcome = op, "TP"
                elif lo <= sl:
                    exit_price, outcome = sl, "SL"
                elif hi >= tp:
                    exit_price, outcome = tp, "TP"
            else:
                if op >= sl:
                    exit_price, outcome = op, "SL"
                elif op <= tp:
                    exit_price, outcome = op, "TP"
                elif hi >= sl:
                    exit_price, outcome = sl, "SL"
                elif lo <= tp:
                    exit_price, outcome = tp, "TP"
            if outcome:
                exit_ts = ts
                break
        if not outcome and _utc_now(now) >= expiry_at:
            # Prefer the last eligible close only when that candle actually closes
            # at expiry. If candles are missing near expiry, use the first observed
            # post-expiry open; without either price, keep the trade unresolved.
            last_eligible_close = (
                future.index[-1] + pd.Timedelta(minutes=5) if not future.empty else None
            )
            if last_eligible_close == expiry_at:
                exit_ts = future.index[-1]
                exit_price = float(future.iloc[-1].close)
            else:
                after_expiry = m5[m5.index >= expiry_at]
                if after_expiry.empty:
                    continue
                exit_ts = after_expiry.index[0]
                exit_price = float(after_expiry.iloc[0].open)
            outcome = "TIME"
        if not outcome:
            continue

        entry = float(trade["entry"])
        risk = abs(entry - float(trade["sl"]))
        signed = 1 if is_long else -1
        pnl_r = ((float(exit_price) - entry) / risk * signed) if risk else 0.0
        result = {
            **trade,
            "status": outcome,
            "exit": float(exit_price),
            "exit_time": exit_ts.isoformat(),
            "gross_R": round(pnl_r, 4),
            "gross_pnl_pct": round((float(exit_price) - entry) / entry * signed * 100, 4)
        }
        state.setdefault("trade_history", []).append(result)
        state["trade_history"] = state["trade_history"][-2000:]
        del positions[signal_id]
        delivered = discord.send_outcome(result, lambda x: fmt(sym, x))
        if not delivered:
            state.setdefault("pending_outcomes", {})[signal_id] = result
        print(f"[closed] {sym} {signal_id}: {outcome} {pnl_r:+.2f}R")


def _save_zone_review_chart(symbol, frames, analysis, now, raw_png=None):
    """Persist paired raw-input and AI-annotated charts for visual quality review."""
    cfg = C.SYMBOLS[symbol]
    raw = raw_png or render_symbol_chart(
        f"{symbol} · {cfg['delta_symbol']}", frames, now
    )
    annotated = render_symbol_chart(
        f"{symbol} · {cfg['delta_symbol']}", frames, now, annotations=analysis
    )
    root = Path(os.environ.get(
        "CHART_REVIEW_DIR", str(data.DATA_DIR / "review_charts")
    ))
    root.mkdir(parents=True, exist_ok=True)

    def save_atomic(target, payload):
        temp = target.with_name(target.name + ".tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    raw_path = root / f"{symbol}_raw.png"
    review_path = root / f"{symbol}_latest.png"
    save_atomic(raw_path, raw)
    save_atomic(review_path, annotated)
    return {
        "raw_path": str(raw_path),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
        "dns_review_path": str(review_path),
        "dns_review_sha256": hashlib.sha256(annotated).hexdigest(),
        "dns_review_bytes": len(annotated),
    }

def _append_research(record):
    path = Path(os.environ.get("RESEARCH_PATH", "research/visual_decisions.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def run(now=None, fetcher=data.fetch, analyzer=None):
    now = _utc_now(now)
    state = st.load()
    # Retry trade-closure messages until Discord confirms delivery.
    for signal_id, outcome in list(state.setdefault("pending_outcomes", {}).items()):
        sym = outcome.get("sym")
        if sym in C.SYMBOLS and discord.send_outcome(outcome, lambda x, s=sym: _fmt(s, x)):
            del state["pending_outcomes"][signal_id]
    # Retry an unsent execution alert briefly; never silently paper-track a signal that Discord did not receive.
    pending = state.setdefault("pending_alerts", {})
    for signal_id, trade in list(pending.items()):
        age = now - pd.Timestamp(trade.get("analysis_time", now.isoformat()))
        if age > pd.Timedelta(minutes=10):
            print(f"[drop] {trade.get('sym')} {signal_id}: Discord alert stayed undelivered for over 10 minutes")
            del pending[signal_id]
            continue
        sent = discord.send_ai_trade(trade["sym"], trade, _fmt(trade["sym"], trade["entry"]))
        if sent:
            state.setdefault("positions", {})[signal_id] = trade
            del pending[signal_id]
            print(f"[alert-delivered] {trade['sym']} {signal_id}")
    frames_by_symbol = {}
    chart_images = {}
    last_candle = {}

    # Download and persist all markets together. Data transforms are chart preparation only.
    for symbol, cfg in C.SYMBOLS.items():
        try:
            frames = data.fetch_bundle(cfg, now, fetcher=fetcher, symbol=symbol)
            if frames.get("5m") is not None and not frames["5m"].empty:
                manage_positions(state, symbol, frames["5m"], now, lambda x: _fmt(symbol, x))
            usable, reason = data.freshness(frames, now)
            if not usable:
                print(f"[skip] {symbol}: {reason}")
                continue
            candle_ts = frames["5m"].index[-1].isoformat()
            frames_by_symbol[symbol] = frames
            last_candle[symbol] = candle_ts
            previous = state.setdefault("last_ai_candle", {}).get(symbol)
            if previous != candle_ts:
                chart_images[symbol] = render_symbol_chart(f"{symbol} · {cfg['delta_symbol']}", frames, now)
        except Exception as exc:
            print(f"[error] {symbol} data/chart: {exc}")

    # Daily summaries are disabled unless explicitly opted in; execution/outcome alerts stay primary.
    if daily_reports.is_enabled(os.environ.get("ENABLE_DAILY_PNL_REPORT")):
        daily_reports.maybe_send_daily_report(state, now, discord.send_daily_report)

    if not frames_by_symbol:
        st.save(state)
        raise RuntimeError("No symbol has a fresh, complete OHLCV bundle; refusing to report a successful analysis run")
    if not chart_images:
        st.save(state)
        print("[skip] no new closed 5m candle; no repeated AI analysis")
        return

    market_context = build_context({s: frames_by_symbol[s] for s in chart_images})
    market_context["_research_feedback"] = build_recent_setup_feedback(
        state.get("trade_history", [])
    )
    active_trades = list(state.get("positions", {}).values()) + list(state.get("pending_alerts", {}).values())
    active = {
        t.get("sym"): {
            "direction": t["dir"], "entry": t["entry"], "stop_loss": t["sl"],
            "take_profit": t["tp"], "signal_id": t["signal_id"]
        }
        for t in active_trades
    }
    call_analyser = analyzer or ai_analyst.analyse
    try:
        result, meta = call_analyser(chart_images, market_context, active_positions=active)
    except Exception as exc:
        print(f"[error] AI analysis failed; candle timestamps were not advanced: {exc}")
        st.save(state)
        raise

    by_symbol = {item.get("symbol"): item for item in result.get("analyses", [])}
    review_charts = {}
    for symbol, analysis in by_symbol.items():
        if symbol not in frames_by_symbol:
            continue
        try:
            review_charts[symbol] = _save_zone_review_chart(
                symbol, frames_by_symbol[symbol], analysis, now,
                raw_png=chart_images[symbol]
            )
        except Exception as exc:
            print(f"[warn] {symbol} DNS review chart could not be saved: {type(exc).__name__}")

    _append_research({
        "timestamp": now.isoformat(),
        "model": meta.get("model"),
        "response_id": meta.get("response_id"),
        "usage": meta.get("usage"),
        "market_context": market_context,
        "zone_review_charts": review_charts,
        "analysis": result
    })
    for symbol, analysis in by_symbol.items():
        if symbol not in chart_images:
            continue
        current_price = float(frames_by_symbol[symbol]["5m"].iloc[-1].close)
        plan, reason = validate_trade(
            analysis,
            current_price,
            has_open_position=(
                any(p.get("sym") == symbol for p in state.get("positions", {}).values())
                or any(p.get("sym") == symbol for p in state.get("pending_alerts", {}).values())
            )
        )
        print(f"[AI] {symbol}: {analysis.get('action')} {analysis.get('direction')} | {reason}")
        if plan is not None:
            signal_id = uuid.uuid4().hex[:12].upper()
            # Delta candle indices are bar-open times; the paper entry is at
            # the latest closed candle's close, i.e. five minutes after its index.
            signal_ts = pd.Timestamp(last_candle[symbol]) + pd.Timedelta(minutes=5)
            trade = {
                **plan,
                "signal_id": signal_id,
                "sym": symbol,
                "triggered_at": signal_ts.isoformat(),
                "status": "OPEN",
                "entry_source": "AI_VISUAL_PAPER",
                "model": meta.get("model"),
                "analysis_time": now.isoformat()
            }
            delivered = discord.send_ai_trade(symbol, trade, _fmt(symbol, current_price))
            if delivered:
                state.setdefault("positions", {})[signal_id] = trade
                print(f"[signal] {symbol} {plan['dir'].upper()} {signal_id} at {_fmt(symbol, current_price)} | {plan['rr']:.2f}R")
            else:
                state.setdefault("pending_alerts", {})[signal_id] = trade
                print(f"[pending] {symbol} {signal_id}: Discord delivery pending; not yet paper-tracked")

    # Mark only successfully analysed candles. A transient API failure retries next workflow run.
    for symbol, candle_ts in last_candle.items():
        if symbol in chart_images:
            state.setdefault("last_ai_candle", {})[symbol] = candle_ts
    state["last_analysis_at"] = now.isoformat()
    state["last_market_commentary"] = result.get("market_commentary", "")
    st.save(state)


if __name__ == "__main__":
    run()
