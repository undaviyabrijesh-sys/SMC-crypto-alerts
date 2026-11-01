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
