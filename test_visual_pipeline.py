"""Offline tests for the visual-first market pipeline. No API key or network needed."""
import os
import tempfile
import pandas as pd

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="salty-quant-data-")

import data
import delta_auth
import main
import state as state_module
from main import validate_trade, manage_positions
import ai_analyst
from visual_chart import render_symbol_chart


def candles(freq, count=140, start="2026-10-20"):
    idx = pd.date_range(start=start, periods=count, freq=freq, tz="UTC")
    base = 100 + pd.Series(range(count), index=idx) * 0.025
    close = base + [0.12 if i % 2 else -0.08 for i in range(count)]
    open_ = base
    return pd.DataFrame({
        "open": open_.values,
        "high": [max(o, c) + 0.25 for o, c in zip(open_, close)],
        "low": [min(o, c) - 0.25 for o, c in zip(open_, close)],
        "close": close,
        "volume": [1000 + (i % 15) * 50 for i in range(count)]
    }, index=idx)


def test_worker_scheduler_aligns_to_five_minute_boundaries():
    from worker import seconds_until_next_tick
    assert seconds_until_next_tick(601, 300) == 299
    assert seconds_until_next_tick(600, 300) == 300
    assert abs(seconds_until_next_tick(900.25, 300) - 299.75) < 1e-9


def test_normalize_retains_volume_and_utc():
    normalized = data.normalize(candles("5min", 10))
    assert list(normalized.columns) == ["open", "high", "low", "close", "volume"]
    assert str(normalized.index.tz) == "UTC"


def test_closed_only_drops_forming_bar():
    df = candles("5min", 3, start="2026-11-04 10:00")
    now = pd.Timestamp("2026-11-04 10:14", tz="UTC")
    closed = data.closed_only(df, 5, now)
    assert len(closed) == 2
    assert closed.index[-1] == pd.Timestamp("2026-11-04 10:05", tz="UTC")


def test_delta_public_candle_adapter_parses_ohlcv():
    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {"success": True, "result": [{
                "time": 1793790000, "open": 100, "high": 102, "low": 99,
                "close": 101, "volume": 1234
            }]}
    original = data.requests.get
    seen = {}
    def fake_get(url, params, headers, timeout):
        seen.update({"url": url, "params": params, "headers": headers})
        return FakeResponse()
    data.requests.get = fake_get
    try:
        frame = data.fetch("BTCUSD", "5m", "1d")
    finally:
        data.requests.get = original
    assert seen["params"]["symbol"] == "BTCUSD"
    assert seen["params"]["resolution"] == "5m"
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert float(frame.volume.iloc[0]) == 1234


def test_fetch_bundle_uses_all_six_native_timeframes():
    minutes = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
    now = pd.Timestamp.now(tz="UTC").floor("5min")
    calls = []
    def fake_fetch(symbol, timeframe, period):
        calls.append((symbol, timeframe, period))
        step = minutes[timeframe]
        last_open = now.floor(f"{step}min") - pd.Timedelta(minutes=step)
        idx = pd.date_range(end=last_open, periods=40, freq=f"{step}min")
        return pd.DataFrame({
            "open": [100.0] * len(idx), "high": [101.0] * len(idx),
            "low": [99.0] * len(idx), "close": [100.5] * len(idx),
            "volume": [1000.0] * len(idx)
        }, index=idx)
    frames = data.fetch_bundle({"delta_symbol": "BTCUSD"}, now, fetcher=fake_fetch, symbol="BTC")
    assert {call[1] for call in calls} == set(minutes)
    assert all(call[0] == "BTCUSD" for call in calls)
    assert all(frames[tf] is not None and not frames[tf].empty for tf in minutes)
    assert data.freshness(frames, now)[0]


def test_visual_chart_png_contains_all_panels():
    frames = {
        "1w": candles("7D", 80), "1d": candles("1D", 110), "4h": candles("4h", 110),
        "1h": candles("1h", 130), "15m": candles("15min", 130),
        "5m": candles("5min", 130)
    }
    image = render_symbol_chart("BTC", frames, pd.Timestamp("2026-11-04 12:00", tz="UTC"))
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image) > 20_000


def test_valid_long_trade_is_repriced_to_latest_close():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100.05, "stop_loss": 95, "take_profit_1": 110,
        "take_profit_2": 115, "confidence": 82, "setup_type": "DEMAND_REJECTION",
        "bias": "BULLISH", "rationale": "Demand held and 5m reclaim.", "invalidation": "Close below demand."
    }
    plan, reason = validate_trade(analysis, 100.0)
    assert reason == "validated"
    assert plan["entry"] == 100.0
    assert abs(plan["rr"] - 2.0) < 1e-9
    assert plan["tp2"] == 115.0


def test_bad_risk_reward_is_rejected():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100, "stop_loss": 95, "take_profit_1": 109,
        "take_profit_2": None, "confidence": 90
    }
    plan, reason = validate_trade(analysis, 100)
    assert plan is None and "only 1.80R" in reason


def test_wrong_side_or_stale_entry_is_rejected():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100, "stop_loss": 101, "take_profit_1": 110,
        "take_profit_2": None, "confidence": 90
    }
    plan, reason = validate_trade(analysis, 100)
    assert plan is None and "not ordered" in reason
    analysis["stop_loss"] = 95
    analysis["entry"] = 102
    plan, reason = validate_trade(analysis, 100)
    assert plan is None and "away" in reason


def test_duplicate_open_position_is_rejected():
    analysis = {
        "action": "TRADE", "direction": "SHORT", "entry_mode": "MARKET",
        "entry": 100, "stop_loss": 105, "take_profit_1": 90,
        "take_profit_2": 85, "confidence": 90
    }
    plan, reason = validate_trade(analysis, 100, has_open_position=True)
    assert plan is None and "already exists" in reason


def test_delta_signature_uses_hmac_sha256():
    import hashlib
    import hmac
    message = "GET1700000000/v2/users/trading_preferences"
    expected = hmac.new(b"unit-test-secret", message.encode("utf-8"), hashlib.sha256).hexdigest()
    assert delta_auth.sign_message("unit-test-secret", message) == expected


def test_delta_read_only_client_signs_exact_prepared_request():
    import hashlib
    import hmac
    import requests

    class FakeResponse:
        status_code = 200
        ok = True
        def json(self):
            return {"success": True, "result": {"user_id": 12345, "private": "must-not-be-returned"}}

    class RecordingSession(requests.Session):
        def send(self, prepared, timeout=None, **kwargs):
            self.last_prepared = prepared
            self.last_timeout = timeout
            return FakeResponse()

    session = RecordingSession()
    client = delta_auth.DeltaReadOnlyClient(
        "dummy-api-key",
        "dummy-api-secret",
        session=session,
        clock=lambda: 1700000000
    )
    result = client._signed_get("/v2/users/trading_preferences", {"note": "BTC USD"})
    prepared = session.last_prepared
    message = "GET1700000000/v2/users/trading_preferences?note=BTC+USD"
    expected = hmac.new(b"dummy-api-secret", message.encode("utf-8"), hashlib.sha256).hexdigest()
    assert prepared.headers["signature"] == expected
    assert prepared.headers["api-key"] == "dummy-api-key"
    assert prepared.headers["timestamp"] == "1700000000"
    assert prepared.headers["User-Agent"] == delta_auth.USER_AGENT
    assert session.last_timeout == 15.0
    assert result["user_id"] == 12345


def test_delta_read_only_client_returns_only_authentication_marker():
    import requests

    class FakeResponse:
        status_code = 200
        ok = True
        def json(self):
            return {"success": True, "result": {"user_id": 12345, "notification_preferences": {"adl": True}}}

    class RecordingSession(requests.Session):
        def send(self, prepared, timeout=None, **kwargs):
            return FakeResponse()

    client = delta_auth.DeltaReadOnlyClient(
        "dummy-api-key", "dummy-api-secret", session=RecordingSession(),
        clock=lambda: 1700000000
    )
    result = client.get_trading_preferences()
    assert result == {"authenticated": True}


def test_delta_client_rejects_non_allowlisted_api_paths():
    client = delta_auth.DeltaReadOnlyClient("dummy-key", "dummy-secret")
    try:
        client._signed_get("/v2/orders")
    except ValueError as exc:
        assert "only permits GET" in str(exc)
    else:
        raise AssertionError("read-only Delta client must reject non-allowlisted endpoints")



def test_visual_analyst_compares_multiple_setup_families():
    setup_types = set(ai_analyst.ANALYSIS_ITEM["properties"]["setup_type"]["enum"])
    assert {"DEMAND_REJECTION", "LIQUIDITY_SWEEP_REVERSAL", "TREND_PULLBACK",
            "MOMENTUM_CONTINUATION", "RANGE_BREAKOUT", "MEAN_REVERSION",
            "VOLATILITY_EXPANSION"} <= setup_types
    prompt = ai_analyst.SYSTEM_PROMPT.lower()
    assert "compare candidate setups" in prompt
    assert "single clearest, highest-conviction" in prompt
    assert "return no_trade" in prompt


def test_late_tp_after_expiry_is_recorded_as_time_exit():
    triggered_at = pd.Timestamp("2026-11-01 00:00:00", tz="UTC")
    index = pd.to_datetime(
        ["2026-11-02 23:55:00+00:00", "2026-11-03 00:00:00+00:00"]
    )
    m5 = pd.DataFrame({
        "open": [100.0, 108.0],
        "high": [105.0, 111.0],  # TP is touched only after the 48h expiry.
        "low": [99.0, 107.0],
        "close": [102.0, 110.0],
        "volume": [1000.0, 1200.0]
    }, index=index)
    state = {
        "positions": {
            "TEST123": {
                "signal_id": "TEST123", "sym": "BTC", "dir": "long",
                "triggered_at": triggered_at.isoformat(),
                "entry": 100.0, "sl": 95.0, "tp": 110.0
            }
        },
        "trade_history": [],
        "pending_outcomes": {}
    }
    original_send = main.discord.send_outcome
    main.discord.send_outcome = lambda trade, fmt: True
    try:
        manage_positions(
            state, "BTC", m5,
            pd.Timestamp("2026-11-03 01:00:00", tz="UTC"),
            lambda value: str(value)
        )
    finally:
        main.discord.send_outcome = original_send

    assert "TEST123" not in state["positions"]
    assert len(state["trade_history"]) == 1
    result = state["trade_history"][0]
    assert result["status"] == "TIME"
    assert result["exit"] == 102.0
    assert result["exit_time"] == "2026-11-02T23:55:00+00:00"


def test_first_post_entry_candle_is_included_in_trade_tracking():
    triggered_at = pd.Timestamp("2026-11-01 12:00:00", tz="UTC")
    m5 = pd.DataFrame({
        "open": [100.0],
        "high": [111.0],
        "low": [99.0],
        "close": [110.0],
        "volume": [1000.0]
    }, index=pd.DatetimeIndex([triggered_at]))
    state = {
        "positions": {
            "TEST124": {
                "signal_id": "TEST124", "sym": "BTC", "dir": "long",
                "triggered_at": triggered_at.isoformat(),
                "entry": 100.0, "sl": 95.0, "tp": 110.0
            }
        },
        "trade_history": [],
        "pending_outcomes": {}
    }
    original_send = main.discord.send_outcome
    main.discord.send_outcome = lambda trade, fmt: True
    try:
        manage_positions(
            state, "BTC", m5,
            triggered_at + pd.Timedelta(minutes=5),
            lambda value: str(value)
        )
    finally:
        main.discord.send_outcome = original_send

    assert "TEST124" not in state["positions"]
    assert len(state["trade_history"]) == 1
    assert state["trade_history"][0]["status"] == "TP"
    assert state["trade_history"][0]["exit_time"] == triggered_at.isoformat()


def test_corrupt_state_fails_closed_instead_of_resetting_positions():
    import json
    with tempfile.TemporaryDirectory(prefix="salty-state-test-") as folder:
        path = os.path.join(folder, "state.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"positions": ')
        original_path = state_module.PATH
        state_module.PATH = path
        try:
            try:
                state_module.load()
            except RuntimeError as exc:
                assert "refusing to start with empty state" in str(exc)
            else:
                raise AssertionError("corrupt state must not silently reset open positions")
        finally:
            state_module.PATH = original_path


def test_state_save_is_atomic_and_round_trips():
    with tempfile.TemporaryDirectory(prefix="salty-state-test-") as folder:
        path = os.path.join(folder, "nested", "state.json")
        original_path = state_module.PATH
        state_module.PATH = path
        sample = {
            "positions": {"S1": {"sym": "BTC", "dir": "long"}},
            "trade_history": [{"signal_id": "S0"}]
        }
        try:
            state_module.save(sample)
            loaded = state_module.load()
            assert loaded["positions"] == sample["positions"]
            assert loaded["trade_history"] == sample["trade_history"]
            assert not os.path.exists(path + ".tmp")
        finally:
            state_module.PATH = original_path


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
