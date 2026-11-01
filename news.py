import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

import config as C

HEADERS = {"User-Agent": "Mozilla/5.0 (advance-alerts)"}
CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

LEX = {
    "crypto": (
        ["etf inflow", "inflows", "approved", "approval", "adoption", "rate cut", "rallies", "surges", "soars",
         "record high", "all-time high", "accumulat", "breakout", "bullish"],
        ["hack", "exploit", "ban", "lawsuit", "sues", "crackdown", "liquidat", "rate hike", "outflow",
         "sell-off", "selloff", "plunge", "crash", "bearish", "fraud", "collapse", "slump"],
    ),
    "gold": (
        ["rate cut", "dovish", "safe haven", "safe-haven", "geopolitic", "weaker dollar", "dollar falls",
         "yields fall", "record high", "central bank buying", "rallies", "surges"],
        ["rate hike", "hawkish", "stronger dollar", "dollar rises", "dollar surges", "yields rise",
         "yields jump", "strong jobs", "sell-off", "slump", "profit-taking"],
    ),
}


def get_events():
    """High-impact USD events this week as UTC datetimes. Returns (events, ok)."""
    try:
        r = requests.get(CAL_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        out = []
        for e in r.json():
            if e.get("country") == "USD" and e.get("impact") == "High":
                t = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
                out.append({"title": e.get("title", "event"), "time": t})
        return out, True
    except Exception as ex:
        print(f"[warn] calendar unavailable: {ex}")
        return [], False


def in_blackout(events, now):
    now = now.to_pydatetime() if hasattr(now, "to_pydatetime") else now
    for e in events:
        if e["time"] - timedelta(minutes=C.BLACKOUT_BEFORE_MIN) <= now <= e["time"] + timedelta(minutes=C.BLACKOUT_AFTER_MIN):
            return e
    return None


def headline_sentiment(kind: str, query: str, now):
    """Crude keyword score in [-1, 1] scaled by how many headlines matched. Returns (score, matched, samples)."""
    bull, bear = LEX[kind]
    try:
        url = f"https://news.google.com/rss/search?q={quote(query)}+when:1d&hl=en-US&gl=US&ceid=US:en"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        items = ET.fromstring(r.content).findall(".//item")
    except Exception as ex:
        print(f"[warn] news unavailable for {query}: {ex}")
        return 0.0, 0, []
    now = now.to_pydatetime() if hasattr(now, "to_pydatetime") else now
    cutoff = now - timedelta(hours=C.NEWS_LOOKBACK_HOURS)
    nb = nr = 0
    samples = []
    for it in items:
        title = (it.findtext("title") or "").lower()
        try:
            ts = email.utils.parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            continue
        if ts < cutoff:
            continue
        b = any(k in title for k in bull)
        s = any(k in title for k in bear)
        if b and not s:
            nb += 1
            samples.append(("+", it.findtext("title")))
        elif s and not b:
            nr += 1
            samples.append(("-", it.findtext("title")))
    matched = nb + nr
    if matched == 0:
        return 0.0, 0, []
    net = (nb - nr) / matched
    return net * min(1.0, matched / 5), matched, samples[:3]


def funding_rate(okx_inst):
    if not okx_inst:
        return None
    try:
        r = requests.get(f"https://www.okx.com/api/v5/public/funding-rate?instId={okx_inst}", headers=HEADERS, timeout=15)
        return float(r.json()["data"][0]["fundingRate"])
    except Exception as ex:
        print(f"[warn] funding unavailable for {okx_inst}: {ex}")
        return None
