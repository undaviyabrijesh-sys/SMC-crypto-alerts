"""Regression tests for stale triggers, lifecycle expiry and replay costs."""
import pandas as pd

import main
import replay


def _watch():
    return {
        "id": "BTC-demand-test", "sym": "BTC", "dir": "long",
        "lo": 99.0, "hi": 100.0, "created": "2026-11-04T09:45:00+00:00",
        "entry": 100.7, "sl": 99.0, "tp": 110.0, "rr": 5.4,
        "score": 80, "trend": "up",
    }


def test_old_rejection_is_not_triggered():
    sent = []
    original_send = main.discord.send
    try:
        main.discord.send = lambda stage, *args, **kwargs: sent.append(stage)
        idx = pd.date_range("2026-11-04 10:00", periods=2, freq="15min", tz="UTC")
        bars = pd.DataFrame([
            (100.4, 100.8, 99.5, 100.7),  # touched zone and rejected bullishly
            (100.7, 101.0, 100.5, 100.6),  # later closed red: old rejection is stale
        ], index=idx, columns=["open", "high", "low", "close"])
        watch = _watch()
        watch["created"] = idx[0].isoformat()
        state = {"watches": {watch["id"]: watch}, "positions": {}, "rearm": {}, "log": []}
        main.manage_watches(state, "BTC", bars, 2.0, idx[-1] + pd.Timedelta(minutes=15), None, str)
        assert "TRIGGER" not in sent, sent
        assert state["positions"] == {}, state["positions"]
    finally:
        main.discord.send = original_send


def test_latest_rejection_can_trigger():
    sent = []
    original_send = main.discord.send
    try:
        main.discord.send = lambda stage, *args, **kwargs: sent.append(stage)
        idx = pd.date_range("2026-11-04 10:00", periods=1, freq="15min", tz="UTC")
        bars = pd.DataFrame([
            (100.4, 100.8, 99.5, 100.7),
        ], index=idx, columns=["open", "high", "low", "close"])
        watch = _watch()
        watch["created"] = idx[0].isoformat()
        state = {"watches": {watch["id"]: watch}, "positions": {}, "rearm": {}, "log": []}
        main.manage_watches(state, "BTC", bars, 2.0, idx[-1] + pd.Timedelta(minutes=15), None, str)
        assert sent == ["TRIGGER"], sent
        position = next(iter(state["positions"].values()))
        assert position["triggered_at"] == idx[0].isoformat(), position
    finally:
        main.discord.send = original_send


def test_replay_respects_time_expiry_and_round_trip_cost():
    t0 = pd.Timestamp("2026-01-01 00:00", tz="UTC")
    idx = pd.date_range(t0 + pd.Timedelta(minutes=15), periods=5, freq="15min")
    bars = pd.DataFrame([
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 111.0, 99.0, 110.0),  # target only after the 1h horizon
        (110.0, 112.0, 109.0, 111.0),
    ], index=idx, columns=["open", "high", "low", "close"])
    trade = {"dir": "long", "entry": 100.0, "sl": 95.0, "tp": 110.0}
    outcome, net_r = replay._outcome(
        bars, t0, trade, max_hours=1, cost_bps=10.0,
        asof=t0 + pd.Timedelta(hours=1, minutes=30),
    )
    assert outcome == "TIME", outcome
    assert abs(net_r - (-0.02)) < 1e-9, net_r


def test_replay_deducts_round_trip_cost_from_target():
    t0 = pd.Timestamp("2026-01-01 00:00", tz="UTC")
    idx = pd.date_range(t0 + pd.Timedelta(minutes=15), periods=2, freq="15min")
    bars = pd.DataFrame([
        (100.0, 111.0, 99.0, 110.0),
        (110.0, 111.0, 109.0, 110.0),
    ], index=idx, columns=["open", "high", "low", "close"])
    trade = {"dir": "long", "entry": 100.0, "sl": 95.0, "tp": 110.0}
    outcome, net_r = replay._outcome(
        bars, t0, trade, max_hours=48, cost_bps=10.0,
        asof=t0 + pd.Timedelta(minutes=45),
    )
    assert outcome == "TP", outcome
    assert abs(net_r - 1.98) < 1e-9, net_r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
