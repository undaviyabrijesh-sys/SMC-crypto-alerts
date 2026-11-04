"""Salty Quant AI: raw OHLCV -> chart images -> visual AI analysis -> validated execution alerts."""
import json
import os
import uuid
from pathlib import Path

import pandas as pd

import ai_analyst
import config as C
import data
import discord
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
    limits = {"1d": 18, "4h": 24, "1h": 30, "15m": 24, "5m": 24}
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
    except (TypeError, ValueError, KeyError):
        return None, "entry, stop-loss or first target is missing"
    if min(model_entry, sl, tp1, float(current_price)) <= 0:
        return None, "non-positive price level"
    current_price = float(current_price)
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

    tp2 = analysis.get("take_profit_2")
    if tp2 is not None:
        try:
            tp2 = float(tp2)
            if (direction == "LONG" and tp2 <= tp1) or (direction == "SHORT" and tp2 >= tp1):
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
        triggered_at = pd.Timestamp(trade["triggered_at"])
        future = m5[m5.index > triggered_at]
        if future.empty:
            continue
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
        if not outcome and _utc_now(now) - triggered_at > pd.Timedelta(hours=C.TRADE_MAX_HOURS):
            exit_ts = future.index[-1]
            exit_price = float(future.iloc[-1].close)
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
        discord.send_outcome(result, lambda x: fmt(sym, x))
        print(f"[closed] {sym} {signal_id}: {outcome} {pnl_r:+.2f}R")


def _append_research(record):
    path = Path(os.environ.get("RESEARCH_PATH", "research/visual_decisions.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def run(now=None, fetcher=data.fetch, analyzer=None):
    now = _utc_now(now)
    state = st.load()
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

    if not chart_images:
        st.save(state)
        print("[skip] no new closed 5m candle; no repeated AI analysis")
        return

    market_context = build_context({s: frames_by_symbol[s] for s in chart_images})
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
        return

    _append_research({
        "timestamp": now.isoformat(),
        "model": meta.get("model"),
        "response_id": meta.get("response_id"),
        "usage": meta.get("usage"),
        "market_context": market_context,
        "analysis": result
    })

    by_symbol = {item.get("symbol"): item for item in result.get("analyses", [])}
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
            signal_ts = last_candle[symbol]
            trade = {
                **plan,
                "signal_id": signal_id,
                "sym": symbol,
                "triggered_at": signal_ts,
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
