"""Discord execution and paper-outcome notifications."""
import math
import os
import requests


def _trigger_hook():
    return os.environ.get("DISCORD_TRIGGER_WEBHOOK") or os.environ.get("DISCORD_WEBHOOK")


def _post(content):
    url = _trigger_hook()
    if os.environ.get("DRY_RUN") or not url:
        print("[DISCORD DRY RUN / NOT CONFIGURED]\n" + content)
        return False
    try:
        response = requests.post(url, json={"content": content[:1900]}, timeout=15)
        response.raise_for_status()
        return True
    except Exception as exc:
        # Request exceptions may contain the full webhook URL, which is a credential.
        print(f"[warn] Discord post failed ({type(exc).__name__}); webhook URL redacted")
        return False


def send_ai_trade(sym, trade, fmt):
    direction = trade["dir"].upper()
    icon = "🟢" if direction == "LONG" else "🔴"
    setup_line = f"Setup: **{trade.get('setup_type', 'OTHER')}**"
    raw_confidence = trade.get("confidence")
    confidence = None
    # Match the validator's numeric contract: booleans, strings, fractional,
    # non-finite and out-of-range values are not measured confidence scores.
    if isinstance(raw_confidence, int) and not isinstance(raw_confidence, bool):
        if 0 <= raw_confidence <= 100:
            confidence = raw_confidence
    elif isinstance(raw_confidence, float):
        if math.isfinite(raw_confidence) and raw_confidence.is_integer() and 0 <= raw_confidence <= 100:
            confidence = int(raw_confidence)
    if confidence is not None:
        setup_line += f" | Confidence: **{confidence:g}/100**"
    lines = [
        f"{icon} **SALTY QUANT AI — {direction} {sym}**",
        f"Signal ID: {trade['signal_id']}",
        setup_line,
    ]
    primary_zone = trade.get("primary_zone")
    if primary_zone:
        lines.append(
            f"Primary DNS ({primary_zone['side']} · {primary_zone['timeframe']} · Q{primary_zone['quality']}): "
            f"**{fmt(primary_zone['low'])} – {fmt(primary_zone['high'])}**"
        )
    selected_zone = trade.get("selected_entry_zone")
    if selected_zone:
        lines.append(
            f"Entry zone ({selected_zone['timeframe']}): "
            f"**{fmt(selected_zone['low'])} – {fmt(selected_zone['high'])}**"
        )
    lines.extend([
        f"Entry: **{fmt(trade['entry'])}**",
        f"Stop-loss: **{fmt(trade['sl'])}**",
        f"Target 1: **{fmt(trade['tp'])}**",
    ])
    if trade.get("tp2") is not None:
        lines.append(f"Target 2: **{fmt(trade['tp2'])}**")
    lines.extend([
        f"Validated R:R to T1: **{trade['rr']:.2f}R**",
        f"Bias: {trade.get('bias', 'UNCLEAR')} | Timeframes: {', '.join(trade.get('timeframes_in_agreement', [])) or 'mixed'}",
        f"Why: {trade.get('rationale', 'Visual SMC setup confirmed')[:350]}",
        f"Invalidation: {trade.get('invalidation', 'See stop-loss')[:220]}",
        "Paper tracking assumes entry at the latest closed 5m price; this is not a broker fill or an exchange order."
    ])
    return _post("\n".join(lines))


def send_outcome(trade, fmt):
    outcome = trade["status"]
    icon = "🟢" if outcome == "TP" else ("🔴" if outcome == "SL" else "⚪")
    label = {"TP": "TAKE PROFIT HIT", "SL": "STOP LOSS HIT", "TIME": "TIME EXIT"}.get(outcome, outcome)
    message = (
        f"{icon} **SALTY QUANT AI — {label}**\n"
        f"Signal ID: `{trade['signal_id']}`\n"
        f"{trade['sym']} {trade['dir'].upper()}\n"
        f"Entry: {fmt(float(trade['entry']))} | Exit: {fmt(float(trade['exit']))}\n"
        f"SL: {fmt(float(trade['sl']))} | TP1: {fmt(float(trade['tp']))}\n"
        f"Result: **{outcome}** | Paper P&L: **{trade['gross_pnl_pct']:+.3f}% "
        f"({trade['gross_R']:+.2f}R)**"
    )
    return _post(message)


def send_daily_report(message):
    """Deliver the once-daily India-time paper P&L summary."""
    return _post(message)
