"""AI-free five-minute quant worker: data -> independent rules -> supervisor -> paper tracking."""
import json
import os
import uuid
from pathlib import Path

import pandas as pd

import config as C
import data
import discord
import quant_strategies
import quant_supervisor
import state as st
from trade_lifecycle import manage_positions


def _utc_now(value=None):
    stamp = pd.Timestamp(value) if value is not None else pd.Timestamp.now(tz="UTC")
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _fmt(symbol, value):
    digits = C.SYMBOLS[symbol].get("dp", 2)
    return f"{float(value):,.{digits}f}"


def _append_record(record):
    path = Path(os.environ.get(
        "QUANT_RESEARCH_PATH", "research/quant_signals.jsonl"
    ))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _active_symbol(state, symbol):
    active = list(state.get("positions", {}).values()) + list(state.get("pending_alerts", {}).values())
    return any(isinstance(item, dict) and item.get("sym") == symbol for item in active)


def _paper_trade(symbol, candidate, now):
    signal_id = uuid.uuid4().hex[:12].upper()
    direction = candidate["direction"].lower()
    return {
        "signal_id": signal_id,
        "sym": symbol,
        "dir": direction,
        "entry": float(candidate["entry"]),
        "sl": float(candidate["stop_loss"]),
        "tp": float(candidate["take_profit"]),
        "tp2": None,
        "rr": float(candidate["rr"]),
        "setup_type": candidate["setup_type"],
        "strategy_id": candidate["strategy_id"],
        "quality_score": int(candidate["quality_score"]),
        "score_type": candidate["score_type"],
        "bias": "BULLISH" if direction == "long" else "BEARISH",
        "rationale": candidate["rationale"],
        "invalidation": candidate["invalidation"],
        "timeframes_in_agreement": candidate["timeframes_in_agreement"],
        "triggered_at": candidate["triggered_at"],
        "status": "OPEN",
        "entry_source": "QUANT_PAPER",
        "analysis_time": now.isoformat(),
        "target_basis": candidate["target_basis"],
    }


def run(now=None, fetcher=data.fetch):
    """Run one deterministic analysis cycle. No AI API or exchange order is used."""
    now = _utc_now(now)
    state = st.load()
    state.setdefault("positions", {})
    state.setdefault("pending_outcomes", {})
    last_candles = state.setdefault("quant_last_candle", {})

    # Outcome delivery is independent of signal generation and continues on every cycle.
    for signal_id, outcome in list(state["pending_outcomes"].items()):
        symbol = outcome.get("sym")
        if symbol in C.SYMBOLS and discord.send_outcome(outcome, lambda value, s=symbol: _fmt(s, value)):
            del state["pending_outcomes"][signal_id]

    for symbol, cfg in C.SYMBOLS.items():
        try:
            frames = data.fetch_bundle(cfg, now, fetcher=fetcher, symbol=symbol)
        except Exception as exc:
            print(f"[quant-data-error] {symbol}: {type(exc).__name__}: {exc}")
            continue

        m5 = frames.get("5m")
        if m5 is not None and not m5.empty:
            manage_positions(state, symbol, m5, now, lambda value, s=symbol: _fmt(s, value))

        usable, reason = data.freshness(frames, now)
        if not usable:
            print(f"[quant-skip] {symbol}: {reason}")
            continue
        candle = frames["5m"].index[-1].isoformat()
        if last_candles.get(symbol) == candle:
            continue

        current_price = float(frames["5m"].iloc[-1].close)
        active = _active_symbol(state, symbol)
        candidates = quant_strategies.generate_candidates(symbol, frames)
        decision = quant_supervisor.select_candidate(
            candidates,
            current_price,
            latest_candle=candle,
            has_open_position=active,
        )

        delivery = "not_applicable"
        if decision["selected"] is not None:
            trade = _paper_trade(symbol, decision["selected"], now)
            if discord.send_ai_trade(symbol, trade, lambda value: _fmt(symbol, value)):
                state["positions"][trade["signal_id"]] = trade
                delivery = "sent"
            else:
                # Do not track a paper position when its execution alert was not delivered.
                delivery = "failed_no_position_opened"

        record = {
            "timestamp": now.isoformat(),
            "symbol": symbol,
            "latest_closed_5m_candle": candle,
            "latest_closed_5m_price": current_price,
            "engine": "DETERMINISTIC_MULTI_STRATEGY",
            "engine_version": "1.0.0",
            "candidates": candidates,
            "decision_status": decision["status"],
            "decision_reason": decision["reason"],
            "selected_strategy": decision["selected"]["strategy_id"] if decision["selected"] else None,
            "research_preview_strategy": decision["preview"]["strategy_id"] if decision["preview"] else None,
            "rejected_candidates": decision["rejected"],
            "discord_delivery": delivery,
            "has_open_position": active,
        }
        _append_record(record)
        last_candles[symbol] = candle

        if decision["status"] == "RESEARCH_ONLY" and decision["preview"]:
            preview = decision["preview"]
            print(
                f"[quant-shadow] {symbol} {preview['direction']} {preview['strategy_id']} "
                f"score={preview['quality_score']} rr={preview['rr']:.2f}; not promoted"
            )
        elif decision["selected"]:
            print(f"[quant-signal] {symbol} {decision['selected']['strategy_id']} paper alert {delivery}")
        elif candidates:
            print(f"[quant-no-trade] {symbol}: {decision['reason']}")
        else:
            print(f"[quant-no-setup] {symbol}: no strategy trigger")

    state["last_quant_cycle_at"] = now.isoformat()
    st.save(state)


if __name__ == "__main__":
    run()
