"""AI-independent closed-candle paper trade lifecycle tracking."""
import pandas as pd

import config as C
import discord


def _utc_now(value=None):
    now = pd.Timestamp(value) if value is not None else pd.Timestamp.now(tz="UTC")
    return now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")


def manage_positions(state, sym, m5, now, fmt):
    """Track closed 5m outcomes; never infer the first exit across missing bars."""
    positions = state.setdefault("positions", {})
    if m5 is None or m5.empty:
        return
    for signal_id, trade in list(positions.items()):
        if trade.get("sym") != sym:
            continue
        triggered_at = _utc_now(trade["triggered_at"])
        expiry_at = triggered_at + pd.Timedelta(hours=C.TRADE_MAX_HOURS)
        latest_eligible_open = expiry_at - pd.Timedelta(minutes=5)
        future = m5[(m5.index >= triggered_at) & (m5.index <= latest_eligible_open)]
        is_long = trade["dir"] == "long"
        exit_price = None
        outcome = None
        exit_ts = None
        expected_next_open = triggered_at
        data_gap = False
        for ts, bar in future.iterrows():
            if ts != expected_next_open:
                data_gap = True
                break
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
            expected_next_open += pd.Timedelta(minutes=5)

        if (
            not outcome
            and not data_gap
            and _utc_now(now) >= expiry_at
            and not future.empty
            and expected_next_open == expiry_at
        ):
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
            "gross_pnl_pct": round((float(exit_price) - entry) / entry * signed * 100, 4),
        }
        state.setdefault("trade_history", []).append(result)
        state["trade_history"] = state["trade_history"][-2000:]
        del positions[signal_id]
        delivered = discord.send_outcome(result, lambda x: fmt(sym, x))
        if not delivered:
            state.setdefault("pending_outcomes", {})[signal_id] = result
        print(f"[closed] {sym} {signal_id}: {outcome} {pnl_r:+.2f}R")
