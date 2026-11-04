import os

import requests

COLORS = {"WATCH": 0xF1C40F, "TRIGGER": 0x2ECC71, "CANCEL": 0x95A5A6}
ICONS = {"WATCH": "👀", "TRIGGER": "🎯", "CANCEL": "❌"}


def _hook(stage):
    one = os.environ.get("DISCORD_WEBHOOK")
    if stage == "WATCH":
        return os.environ.get("DISCORD_WATCH_WEBHOOK") or one
    return os.environ.get("DISCORD_TRIGGER_WEBHOOK") or one


def send(stage, sym, w, fmt, lines=None, note=None):
    """w is the watch dict. fmt formats a price for this symbol."""
    arrow = "LONG" if w["dir"] == "long" else "SHORT"
    fields = [
        {"name": "Zone", "value": f"{fmt(w['lo'])} – {fmt(w['hi'])}", "inline": True},
        {"name": "Entry", "value": fmt(w["entry"]), "inline": True},
        {"name": "SL", "value": fmt(w["sl"]), "inline": True},
        {"name": "TP", "value": fmt(w["tp"]), "inline": True},
        {"name": "R:R", "value": f"{w['rr']:.1f}", "inline": True},
    ]
    if w.get("signal_id"):
        fields.append({"name": "Signal ID", "value": w["signal_id"], "inline": True})
    if "score" in w:
        fields.append({"name": "Score", "value": f"{w['score']}/100", "inline": True})
    desc = []
    if stage == "WATCH":
        desc.append("Price is approaching the zone. **Not an entry yet.** Wait for a TRIGGER message.")
    if lines:
        desc.append("• " + "\n• ".join(lines))
    if note:
        desc.append(note)
    embed = {
        "title": f"{ICONS[stage]} {stage} · {sym} {arrow}" + (" · flip retest" if w.get("flip") else ""),
        "description": "\n".join(desc),
        "color": COLORS[stage],
        "fields": fields,
        "footer": {"text": "Candidate setup, not financial advice."},
    }
    url = _hook(stage)
    if os.environ.get("DRY_RUN") or not url:
        print(f"[{stage}] {sym} {arrow}: {embed['description']} | " + ", ".join(f"{f['name']}={f['value']}" for f in fields))
        return
    try:
        requests.post(url, json={"embeds": [embed]}, timeout=15).raise_for_status()
    except Exception as ex:
        print(f"[warn] discord post failed: {ex}")


def post_text(text, stage=None):
    """Plain text post for reports and trade outcomes. Returns True if sent."""
    if stage == "TRIGGER":
        url = os.environ.get("DISCORD_TRIGGER_WEBHOOK") or os.environ.get("DISCORD_WEBHOOK") or os.environ.get("DISCORD_WATCH_WEBHOOK")
    else:
        url = os.environ.get("DISCORD_ZONES_WEBHOOK") or os.environ.get("DISCORD_WATCH_WEBHOOK") or os.environ.get("DISCORD_WEBHOOK")
    if os.environ.get("DRY_RUN") or not url:
        return False
    try:
        requests.post(url, json={"content": text[:1900]}, timeout=15).raise_for_status()
        return True
    except Exception as ex:
        print(f"[warn] discord post failed: {ex}")
        return False


def send_outcome(trade, fmt):
    outcome = trade["status"]
    icon = "🟢" if outcome == "TP" else ("🔴" if outcome == "SL" else "⚪")
    label = {"TP": "TAKE PROFIT HIT", "SL": "STOP LOSS HIT", "TIME": "TIME EXIT"}[outcome]
    direction = "LONG" if trade["dir"] == "long" else "SHORT"
    message = (
        f"{icon} **SMC SIGNAL CLOSED — {label}**\\n"
        f"Signal ID: `{trade['signal_id']}`\\n"
        f"{trade['sym']} {direction}\\n"
        f"Entry: {fmt(float(trade['entry']))} | Exit: {fmt(float(trade['exit']))}\\n"
        f"SL: {fmt(float(trade['sl']))} | TP: {fmt(float(trade['tp']))}\\n"
        f"Result: **{outcome}** | P&L: {trade['gross_pnl_pct']:+.3f}% "
        f"({trade['gross_R']:+.2f}R)"
    )
    post_text(message, stage="TRIGGER")
