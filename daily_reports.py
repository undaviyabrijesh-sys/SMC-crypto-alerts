"""End-of-day paper-trade reporting in India Standard Time.

Reports realized closed positions only. Results are in R-multiples, not INR;
the current signal tracker does not model position sizing, contract multipliers,
fees, funding, spread or liquidation.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import math
import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
REPORT_AFTER = time(0, 5)


def _to_ist(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert(IST)


def _realized_for_day(trade_history, report_day: date):
    selected = []
    for trade in trade_history or []:
        if not isinstance(trade, dict) or not trade.get("exit_time"):
            continue
        try:
            local_exit = _to_ist(trade["exit_time"])
            r_value = float(trade.get("gross_R", 0.0))
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(r_value):
            continue
        if local_exit.date() == report_day:
            selected.append((trade, r_value))
    return selected


def build_daily_report(report_day: date, trade_history, open_positions=None) -> str:
    closed = _realized_for_day(trade_history, report_day)
    total = len(closed)
    wins = sum(r > 0 for _, r in closed)
    losses = sum(r < 0 for _, r in closed)
    breakeven = total - wins - losses
    total_r = sum(r for _, r in closed)
    win_rate = 100.0 * wins / total if total else 0.0

    status_counts = {}
    for trade, _ in closed:
        status = str(trade.get("status", "UNKNOWN")).upper()
        status_counts[status] = status_counts.get(status, 0) + 1

    lines = [
        f"🌙 **SALTY QUANT — DAILY PAPER P&L | {report_day.isoformat()} IST**",
        f"Closed trades: **{total}** | Wins: **{wins}** | Losses: **{losses}** | Breakeven: **{breakeven}**",
        f"Win rate: **{win_rate:.1f}%** | Realized result: **{total_r:+.2f}R**",
    ]
    if total:
        lines.append(
            f"Average per closed trade: **{total_r / total:+.2f}R** | "
            f"Best: **{max(r for _, r in closed):+.2f}R** | "
            f"Worst: **{min(r for _, r in closed):+.2f}R**"
        )
        if status_counts:
            lines.append("Exits: " + " | ".join(
                f"{key}: {status_counts[key]}" for key in sorted(status_counts)
            ))

        by_symbol = {}
        by_setup = {}
        for trade, r_value in closed:
            symbol = str(trade.get("sym", "UNKNOWN"))
            setup = str(trade.get("setup_type", "UNSPECIFIED"))
            by_symbol.setdefault(symbol, []).append(r_value)
            by_setup.setdefault(setup, []).append(r_value)

        lines.append("**By instrument**")
        for symbol, results in sorted(by_symbol.items()):
            lines.append(
                f"• {symbol}: {len(results)} trades | "
                f"{sum(results):+.2f}R | {sum(r > 0 for r in results)}W/"
                f"{sum(r < 0 for r in results)}L"
            )
        lines.append("**By setup**")
        for setup, results in sorted(by_setup.items()):
            lines.append(
                f"• {setup[:40]}: {len(results)} trades | {sum(results):+.2f}R"
            )
    else:
        lines.append("No paper positions were closed during this IST trading day.")

    positions = open_positions or {}
    lines.append(f"Open paper positions at report time: **{len(positions)}** (excluded from realized P&L).")
    lines.append(
        "Paper results are gross R-multiples based on the recorded entry/SL. "
        "They are not INR account P&L; fees, funding, spread, slippage and contract sizing are not included."
    )
    return "\n".join(lines)[:1900]


def maybe_send_daily_report(state, now, sender) -> bool:
    """Send yesterday's report after 00:05 IST once; retain failed delivery for retry."""
    local_now = _to_ist(now)
    if local_now.time().replace(tzinfo=None) < REPORT_AFTER:
        return False

    report_day = local_now.date() - timedelta(days=1)
    key = report_day.isoformat()
    sent = state.setdefault("daily_reports_sent", [])
    pending = state.setdefault("pending_daily_reports", {})
    if key in sent:
        return False

    message = pending.get(key)
    if not message:
        message = build_daily_report(
            report_day,
            state.get("trade_history", []),
            state.get("positions", {}),
        )
        pending[key] = message

    if not sender(message):
        return False

    pending.pop(key, None)
    sent.append(key)
    state["daily_reports_sent"] = sent[-365:]
    return True
