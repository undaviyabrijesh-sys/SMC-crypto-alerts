"""Offline end-to-end tests on synthetic candles. Run: python test_synthetic.py"""
import json
import os
import tempfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd

os.environ["STATE_PATH"] = os.path.join(tempfile.mkdtemp(), "state.json")
os.environ["DRY_RUN"] = "1"

import config as C, discord, main, news, state as st  # noqa: E402
from zones import find_zones, zigzag  # noqa: E402

st.PATH = os.environ["STATE_PATH"]


def candle(o, c, pad=0.2):
    return o, max(o, c) + pad, min(o, c) - pad, c


def baseline():
    return [(100.2, 100.4, 99.6, 99.8) if k % 2 == 0 else (99.8, 100.4, 99.6, 100.2) for k in range(260)]


def decline(rows, to, steps):
    a = np.linspace(rows[-1][3], to, steps + 1)
    return rows + [candle(p0, p1) for p0, p1 in zip(a[:-1], a[1:])]


def make_1h(fvg=True, crash=False, retest=False, age=0, tail=0):
    rows = baseline() + [(100.5, 100.6, 99.5, 99.9)]           # tip candle: zone 99.5 - 100.6
    if fvg:                                                     # impulse leaves a fair value gap
        rows += [(99.9, 101.5, 99.8, 101.4), (101.4, 102.7, 101.3, 102.6), (102.6, 103.8, 102.5, 103.6)]
        top = 103.6
    else:                                                       # same leg built from overlapping candles
        rows += [(99.9, 100.9, 99.8, 100.8), (100.8, 101.7, 100.2, 101.6), (101.6, 102.5, 100.8, 102.4),
                 (102.4, 103.3, 101.5, 103.2), (103.2, 104.0, 102.3, 103.9)]
        top = 103.9
    if age:                                                     # long sideways stretch above the zone (no new tips)
        rows += [(103.5, 103.9, 102.9, 103.1) if k % 2 == 0 else (103.1, 103.9, 102.9, 103.5) for k in range(age)]
        rows = decline(rows, 100.95, 40)
    elif retest:                                                # price dips into the zone, reacts hard, comes back
        rows = decline(rows, 101.2, 12)
        rows.append((101.2, 101.3, 100.3, 100.9))
        rows = decline(rows, 103.6, 5)
        rows = decline(rows, 100.95, 24)
    elif crash:
        rows = decline(rows, 101.0, 20)
        rows += [(101.0, 101.2, 99.9, 100.0), (100.0, 100.1, 99.0, 99.1),   # body close below 99.5: role flips
                 (99.1, 99.2, 97.9, 98.0), (98.0, 98.1, 97.2, 97.3),
                 (97.3, 97.9, 97.2, 97.8), (97.8, 98.4, 97.7, 98.3), (98.3, 98.8, 98.2, 98.7),
                 (98.7, 99.2, 98.6, 99.1), (99.1, 99.3, 98.9, 99.0)]         # rebounds toward the zone from below
    else:
        rows = decline(rows, 100.95, 36)
    rows += [(100.95, 101.05, 100.85, 100.95)] * tail          # later hourly candles for multi-hour tests
    end = pd.Timestamp("2026-11-02 11:00", tz="UTC") + pd.Timedelta(hours=tail)
    idx = pd.date_range(end=end, periods=len(rows), freq="1h")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def make_15m(extra=()):
    idx = pd.date_range(end="2026-11-02 11:45", periods=480, freq="15min", tz="UTC")
    closes = np.where(np.arange(480) % 2 == 0, 101.0, 100.95)
    opens = np.roll(closes, 1)
    df = pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) + 0.1,
                       "low": np.minimum(opens, closes) - 0.1, "close": closes}, index=idx)
    for ts, o, h, l, c in extra:
        df.loc[pd.Timestamp(ts, tz="UTC")] = [o, h, l, c]
    return df.sort_index()


def patch(sent, events=()):
    discord.send = lambda stage, sym, w, fmt, lines=None, note=None: sent.append((stage, sym, w["dir"]))
    news.get_events = lambda: (list(events), True)
    news.headline_sentiment = lambda *a, **k: (0.0, 0, [])
    news.funding_rate = lambda *a, **k: None
    if os.path.exists(st.PATH):
        os.remove(st.PATH)


def run_case(m15_extra, now2, kronos=None, h1=None):
    sent = []
    patch(sent)
    kf = os.path.join(tempfile.mkdtemp(), "k.json")
    if kronos:
        json.dump(kronos, open(kf, "w"))
    os.environ["KRONOS_BIAS_FILE"] = kf
    h1 = h1 if h1 is not None else make_1h()
    holder = {"m15": make_15m()}
    fetch = lambda sym, interval, period: h1 if interval == "1h" else holder["m15"]
    main.run(now=pd.Timestamp("2026-11-02 12:05", tz="UTC"), fetcher=fetch)
    stage1 = list(sent); sent.clear()
    holder["m15"] = make_15m(m15_extra)
    main.run(now=pd.Timestamp(now2, tz="UTC"), fetcher=fetch)
    return stage1, list(sent)


REACT = [("2026-11-02 12:15", 100.95, 101.0, 100.65, 100.7), ("2026-11-02 12:30", 100.7, 100.75, 100.2, 100.5),
         ("2026-11-02 12:45", 100.5, 101.05, 100.45, 101.0), ("2026-11-02 13:00", 101.0, 101.3, 100.95, 101.2)]


def test_zone_on_tip_with_fvg():
    zones, tips = find_zones(make_1h(), "T")
    assert len(zones) == 1 and zones[0]["kind"] == "demand" and not zones[0]["flip"], zones
    assert abs(zones[0]["lo"] - 99.5) < 1e-9 and abs(zones[0]["hi"] - 100.6) < 1e-9
    assert zones[0]["strength"] > 4 and 103.8 in tips["highs"], (zones, tips)


def test_no_zones_on_minor_swings():
    idx = pd.date_range(end="2026-11-02 11:00", periods=260, freq="1h", tz="UTC")
    df = pd.DataFrame(baseline(), index=idx, columns=["open", "high", "low", "close"])
    zones, _ = find_zones(df, "T")
    assert zones == [] and zigzag(df, C.ZZ_ATR)[0] == []


def test_no_zone_without_fvg():
    zones, _ = find_zones(make_1h(fvg=False), "T")
    assert zones == [], zones


def test_role_reversal_flip():
    zones, _ = find_zones(make_1h(crash=True), "T")
    flips = [z for z in zones if z["flip"]]
    assert len(flips) == 1 and flips[0]["kind"] == "supply", zones
    assert abs(flips[0]["lo"] - 99.5) < 1e-9 and abs(flips[0]["hi"] - 100.6) < 1e-9
    assert not any(z["kind"] == "demand" and abs(z["lo"] - 99.5) < 1e-9 for z in zones)  # original demand is gone


def test_watch_then_trigger_without_any_trend_filter():
    s1, s2 = run_case(REACT, "2026-11-02 13:20")
    assert [x[0] for x in s1] == ["WATCH"] * 3 and [x[0] for x in s2] == ["TRIGGER"] * 3, (s1, s2)


def test_watch_then_cancel_on_break():
    extra = [("2026-11-02 12:15", 100.9, 100.95, 99.0, 99.2)]   # closes below zone low (99.5)
    s1, s2 = run_case(extra, "2026-11-02 12:35")
    assert [x[0] for x in s1] == ["WATCH"] * 3 and [x[0] for x in s2] == ["CANCEL"] * 3, (s1, s2)


def test_kronos_hard_filter():
    s1, _ = run_case([], "2026-11-02 12:20", kronos={"BTC": "down", "ETH": "flat", "XAU": "up"})
    assert [x[1] for x in s1] == ["XAU"], s1
    s1, _ = run_case([], "2026-11-02 12:20", kronos={})
    assert len(s1) == 3


def test_retested_zone_stays_valid_and_reaction_is_measured():
    zones, _ = find_zones(make_1h(retest=True), "T")
    z = [x for x in zones if abs(x["lo"] - 99.5) < 1e-9]
    assert len(z) == 1 and z[0]["kind"] == "demand" and z[0]["retests"] == 1 and z[0]["best_reaction"] > 2, zones
    s1, _ = run_case([], "2026-11-02 12:20", h1=make_1h(retest=True))
    assert [x[0] for x in s1] == ["WATCH"] * 3, s1          # a retested zone can still be watched


def test_week_old_zone_still_works():
    h1 = make_1h(age=200)
    zones, _ = find_zones(h1, "T")
    z = [x for x in zones if abs(x["lo"] - 99.5) < 1e-9]
    age_bars = len(h1) - 1 - h1.index.get_loc(pd.Timestamp(z[0]["formed"]))
    assert len(z) == 1 and age_bars > 168, (zones, age_bars)       # older than one week
    s1, _ = run_case([], "2026-11-02 12:20", h1=h1)
    assert [x[0] for x in s1] == ["WATCH"] * 3, s1


def test_same_zone_alerts_again_only_after_price_leaves_and_returns():
    sent = []
    patch(sent)
    os.environ["KRONOS_BIAS_FILE"] = "/nonexistent"
    h1 = make_1h(tail=6)
    later = [("2026-11-02 13:15", 101.05, 101.1, 100.95, 101.0),     # lingers near the zone: no departure yet
             ("2026-11-02 13:30", 101.0, 102.6, 100.95, 102.4),     # leaves (about 2 ATR away)
             ("2026-11-02 13:45", 102.4, 102.5, 101.6, 101.8),
             ("2026-11-02 14:00", 101.8, 101.9, 101.2, 101.3),
             ("2026-11-02 14:15", 101.3, 101.4, 100.9, 100.95)]     # coming back toward the zone
    second = [("2026-11-02 14:45", 100.95, 101.0, 100.35, 100.45),  # second entry into the zone
              ("2026-11-02 15:00", 100.45, 101.2, 100.4, 101.1),
              ("2026-11-02 15:15", 101.1, 101.3, 101.0, 101.2)]
    steps = [("2026-11-02 12:05", []), ("2026-11-02 13:20", REACT), ("2026-11-02 13:35", REACT + later[:1]),
             ("2026-11-02 14:35", REACT + later), ("2026-11-02 15:35", REACT + later + second)]
    got = []
    for now, extra in steps:
        sent.clear()
        m15 = make_15m(extra)
        main.run(now=pd.Timestamp(now, tz="UTC"), fetcher=lambda y, i, p: h1 if i == "1h" else m15)
        got.append([x[0] for x in sent])
    assert got == [["WATCH"] * 3, ["TRIGGER"] * 3, [], [], []], got


def test_zones_report_lists_zone_and_liquidity():
    import show_zones
    h1, m15 = make_1h(retest=True), make_15m()
    blocks = show_zones.report(fetcher=lambda y, i, p: h1 if i == "1h" else m15, now=pd.Timestamp("2026-11-02 12:05", tz="UTC"))
    assert len(blocks) == 3 and "DEMAND" in blocks[0] and "99.5 - 100.6" in blocks[0], blocks[0]
    assert "tested 1x" in blocks[0] and "liquidity above" in blocks[0], blocks[0]


def test_replay_scores_outcome():
    import replay
    h1, m15 = make_1h(), make_15m(REACT + [("2026-11-02 13:15", 101.2, 104.0, 101.1, 103.9)])
    patch([])
    events, trig = replay.replay(fetcher=lambda y, i, p: h1 if i == "1h" else m15, days=1, verbose=False)
    assert len(trig) == 3 and set(trig.result) == {"TP"}, trig


def test_no_new_watch_in_blackout():
    sent = []
    patch(sent, events=[{"title": "CPI", "time": datetime(2026, 11, 2, 12, 30, tzinfo=timezone.utc)}])
    os.environ["KRONOS_BIAS_FILE"] = "/nonexistent"
    h1, m15 = make_1h(), make_15m()
    main.run(now=pd.Timestamp("2026-11-02 12:05", tz="UTC"), fetcher=lambda s, i, p: h1 if i == "1h" else m15)
    assert sent == [], sent


def test_triggered_signal_lifecycle_tp_and_conservative_sl():
    sent = []
    original = discord.send_outcome
    discord.send_outcome = lambda trade, fmt: sent.append(trade["status"])
    try:
        t0 = pd.Timestamp("2026-11-04 10:00", tz="UTC")
        idx = pd.date_range(t0, periods=3, freq="15min")
        fmt = lambda x: f"{x:.2f}"
        for signal_id, candle, expected in [
            ("TPTEST", (100.0, 111.0, 99.0, 108.0), "TP"),
            ("SLTEST", (100.0, 111.0, 94.0, 108.0), "SL"),
        ]:
            state = {"positions": {
                signal_id: {"signal_id": signal_id, "sym": "BTC", "dir": "long",
                            "entry": 100.0, "sl": 95.0, "tp": 110.0,
                            "triggered_at": idx[0].isoformat(), "status": "OPEN"}
            }, "trade_history": []}
            bars = pd.DataFrame([
                (100.0, 101.0, 99.0, 100.0), candle,
                (108.0, 109.0, 107.0, 108.0)
            ], index=idx, columns=["open", "high", "low", "close"])
            main.manage_positions(state, "BTC", bars, idx[-1] + pd.Timedelta(minutes=15), fmt)
            assert signal_id not in state["positions"], state
            assert state["trade_history"][-1]["status"] == expected, state
        assert sent == ["TP", "SL"], sent
    finally:
        discord.send_outcome = original


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
