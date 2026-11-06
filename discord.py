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
    agent_review = trade.get("agent_review")
    if isinstance(agent_review, dict) and agent_review.get("status") == "APPROVED":
        lines.append(
            "AI desk debate: "
            f"Bull {agent_review.get('bull_stance', '—')} · "
            f"Bear {agent_review.get('bear_stance', '—')} · "
            f"Chief {agent_review.get('decision', 'APPROVE')}"
        )
        chief_rationale = agent_review.get("trader_rationale")
        if isinstance(chief_rationale, str) and chief_rationale.strip():
            lines.append(f"Chief Trader review: {chief_rationale[:250]}")
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
        f"{icon} **SALTY QUANT — {label}**\n"
        f"Signal ID: `{trade['signal_id']}`\n"
        f"{trade['sym']} {trade['dir'].upper()}\n"
        f"Entry: {fmt(float(trade['entry']))} | Exit: {fmt(float(trade['exit']))}\n"
        f"SL: {fmt(float(trade['sl']))} | TP1: {fmt(float(trade['tp']))}\n"
        f"Result: **{outcome}** | Gross paper P&L (before fees, spread, slippage and funding): "
        f"**{trade['gross_pnl_pct']:+.3f}% ({trade['gross_R']:+.2f}R)**"
    )
    return _post(message)


def send_daily_report(message):
    """Deliver the once-daily India-time paper P&L summary."""
    return _post(message)



def send_quant_trade(sym, trade, fmt):
    """Execution-focused deterministic strategy alert; score is not a probability."""
    direction = trade["dir"].upper()
    icon = "🟢" if direction == "LONG" else "🔴"
    score = trade.get("quality_score")
    score_line = ""
    if isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100:
        score_line = f"Rule quality: **{score}/100** (rubric points, not probability)\n"
    message = (
        f"{icon} **SALTY QUANT — {direction} {sym}**\n"
        f"Signal ID: `{trade['signal_id']}`\n"
        f"Strategy: **{trade.get('setup_type', 'QUANT_SETUP')}** "
        f"(`{trade.get('strategy_id', 'UNSPECIFIED')}`)\n"
        f"{score_line}"
        f"Entry: **{fmt(trade['entry'])}**\n"
        f"Stop-loss: **{fmt(trade['sl'])}**\n"
        f"Target: **{fmt(trade['tp'])}**\n"
        f"Validated R:R: **{float(trade['rr']):.2f}R**\n"
        f"Timeframes: {', '.join(trade.get('timeframes_in_agreement', [])) or 'mixed'}\n"
        f"Why: {str(trade.get('rationale', ''))[:380]}\n"
        f"Invalidation: {str(trade.get('invalidation', 'See stop-loss'))[:220]}\n"
        "Paper tracking uses the latest closed 5m price; no exchange order is submitted."
    )
    return _post(message)


def send_visual_trade(sym, trade, fmt):
    """Execution-focused alert; bound every narrative field before Discord's 2,000-char limit."""
    def short(value, limit):
        text = str(value).strip()
        return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"

    direction = str(trade["dir"]).upper()
    icon = "🟢" if direction == "LONG" else "🔴"
    family = str(trade.get("setup_family") or trade.get("setup_type") or "OTHER")
    quality = trade.get("quality_score")
    confidence = trade.get("confidence")
    score_line = ""
    if isinstance(quality, int) and not isinstance(quality, bool) and isinstance(confidence, int) and not isinstance(confidence, bool):
        score_line = (
            f"Visual quality: **{quality}/100** | Confidence: **{confidence}/100** "
            "(rubric scores, not probabilities)\\n"
        )
    zone = trade.get("entry_zone") or {}
    zone_line = ""
    if isinstance(zone, dict) and all(key in zone for key in ("low", "high", "timeframe")):
        zone_line = (
            f"Entry zone ({zone['timeframe']}): "
            f"**{fmt(zone['low'])} – {fmt(zone['high'])}**\\n"
        )
    evidence_tfs = trade.get("evidence_timeframes") or trade.get("timeframes_in_agreement") or []
    supporting = trade.get("supporting_evidence") or []
    conflicts = trade.get("conflicting_evidence") or []
    cancel_if = trade.get("cancel_if") or []
    lines = [
        f"{icon} **SALTY QUANT AI — {direction} {sym}**",
        f"Signal ID: `{trade['signal_id']}`",
        f"Setup: **{family}**",
    ]
    if score_line:
        lines.append(score_line.rstrip())
    if zone_line:
        lines.append(zone_line.rstrip())
    lines.extend([
        f"Entry: **{fmt(trade['entry'])}**",
        f"Stop-loss: **{fmt(trade['sl'])}**",
        f"Target 1: **{fmt(trade['tp'])}**",
        f"Validated R:R: **{trade['rr']:.2f}R**",
        f"Trigger timeframe: {trade.get('trigger_timeframe', '—')} | Evidence: {', '.join(evidence_tfs[:6])}",
        f"Trigger: {short(trade.get('trigger_condition', ''), 140)}",
        f"Context: {short(trade.get('higher_timeframe_context', ''), 140)}",
        f"Why: {short(trade.get('rationale', ''), 170)}",
        f"Target rationale: {short(trade.get('target_rationale', ''), 120)}",
        f"Invalidation: {short(trade.get('invalidation', ''), 140)}",
    ])
    if supporting:
        lines.append("Evidence: " + " | ".join(short(item, 70) for item in supporting[:3]))
    if conflicts:
        lines.append("Conflicts considered: " + " | ".join(short(item, 70) for item in conflicts[:2]))
    if cancel_if:
        lines.append("Cancel before entry if: " + " | ".join(short(item, 70) for item in cancel_if[:2]))
    lines.append("Paper tracking only at the latest closed 5m price; no exchange order is submitted.")
    message = "\\n".join(lines)
    if len(message) > 1900:
        print("[warn] visual alert exceeded the safe Discord message budget; refusing truncated delivery")
        return False
    return _post(message)
