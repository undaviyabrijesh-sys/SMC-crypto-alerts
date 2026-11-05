"""Offline tests for the visual-first market pipeline. No API key or network needed."""
import os
import tempfile
import pandas as pd

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="salty-quant-data-")

import data
import bootstrap_historical_data as historical_data
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


def test_normalize_rejects_invalid_or_nonfinite_ohlc():
    invalid = candles("5min", 3)
    invalid.iloc[0, invalid.columns.get_loc("high")] = invalid.iloc[0]["close"] - 1
    try:
        data.normalize(invalid)
    except ValueError as exc:
        assert "OHLC invariants failed" in str(exc)
    else:
        raise AssertionError("inconsistent high/low values must be rejected")

    nonfinite = candles("5min", 3)
    nonfinite.iloc[0, nonfinite.columns.get_loc("open")] = float("inf")
    try:
        data.normalize(nonfinite)
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("non-finite OHLC values must be rejected")


def test_normalize_handles_missing_volume_and_rejects_negative_volume():
    frame = candles("5min", 3)
    frame.iloc[0, frame.columns.get_loc("volume")] = float("nan")
    normalized = data.normalize(frame)
    assert normalized.volume.iloc[0] == 0.0

    frame.iloc[1, frame.columns.get_loc("volume")] = -1.0
    try:
        data.normalize(frame)
    except ValueError as exc:
        assert "negative values" in str(exc)
    else:
        raise AssertionError("negative volume must be rejected")


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


def test_visual_chart_draws_ai_dns_overlays_on_matching_panels():
    frames = {
        "1w": candles("7D", 80), "1d": candles("1D", 110), "4h": candles("4h", 110),
        "1h": candles("1h", 130), "15m": candles("15min", 130),
        "5m": candles("5min", 130)
    }
    analysis = {
        "demand_zones": [{"low": 102.8, "high": 103.4, "timeframe": "15m", "quality": 4, "evidence": "Bullish base."}],
        "supply_zones": [{"low": 102.7, "high": 103.0, "timeframe": "4h", "quality": 5, "evidence": "Bearish base."}],
        "selected_entry_zone": {"low": 102.95, "high": 103.15, "timeframe": "15m", "evidence": "Refined demand trigger."}
    }
    raw = render_symbol_chart("BTC", frames, pd.Timestamp("2026-11-04 12:00", tz="UTC"))
    reviewed = render_symbol_chart(
        "BTC", frames, pd.Timestamp("2026-11-04 12:00", tz="UTC"), annotations=analysis
    )
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert reviewed.startswith(b"\x89PNG\r\n\x1a\n")
    assert reviewed != raw
    assert len(reviewed) > 20_000


def test_latest_dns_review_chart_is_saved_atomically():
    import hashlib

    frames = {
        "1w": candles("7D", 80), "1d": candles("1D", 110), "4h": candles("4h", 110),
        "1h": candles("1h", 130), "15m": candles("15min", 130),
        "5m": candles("5min", 130)
    }
    analysis = {
        "demand_zones": [{"low": 102.8, "high": 103.4, "timeframe": "15m", "quality": 4, "evidence": "Bullish base."}],
        "supply_zones": [{"low": 102.7, "high": 103.0, "timeframe": "4h", "quality": 5, "evidence": "Bearish base."}]
    }
    with tempfile.TemporaryDirectory(prefix="salty-dns-review-") as folder:
        old = os.environ.get("CHART_REVIEW_DIR")
        os.environ["CHART_REVIEW_DIR"] = folder
        try:
            raw_png = render_symbol_chart(
                "BTC", frames, pd.Timestamp("2026-11-04 12:00", tz="UTC")
            )
            saved = main._save_zone_review_chart(
                "BTC", frames, analysis, pd.Timestamp("2026-11-04 12:00", tz="UTC"),
                raw_png=raw_png
            )
        finally:
            if old is None:
                os.environ.pop("CHART_REVIEW_DIR", None)
            else:
                os.environ["CHART_REVIEW_DIR"] = old
        with open(saved["raw_path"], "rb") as handle:
            raw_image = handle.read()
        with open(saved["dns_review_path"], "rb") as handle:
            review_image = handle.read()
        assert raw_image.startswith(b"\x89PNG\r\n\x1a\n")
        assert review_image.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(raw_image) == saved["raw_bytes"]
        assert len(review_image) == saved["dns_review_bytes"]
        assert hashlib.sha256(raw_image).hexdigest() == saved["raw_sha256"]
        assert hashlib.sha256(review_image).hexdigest() == saved["dns_review_sha256"]
        assert not os.path.exists(saved["raw_path"] + ".tmp")
        assert not os.path.exists(saved["dns_review_path"] + ".tmp")


def test_valid_long_trade_is_repriced_to_latest_close():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100.05, "stop_loss": 95, "take_profit_1": 110,
        "take_profit_2": 115, "confidence": 82, "setup_type": "DEMAND_REJECTION",
        "selected_entry_zone": {"low": 99.8, "high": 100.2, "timeframe": "15m", "evidence": "Demand reclaim band."},
        "demand_zones": [{"low": 99.5, "high": 100.5, "timeframe": "15m", "quality": 4, "evidence": "Base before bullish displacement."}],
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
        "take_profit_2": None, "confidence": 90,
        "selected_entry_zone": {"low": 99.8, "high": 100.2, "timeframe": "15m", "evidence": "Entry band."},
        "demand_zones": [{"low": 99.5, "high": 100.5, "timeframe": "15m", "quality": 4, "evidence": "Demand base."}]
    }
    plan, reason = validate_trade(analysis, 100)
    assert plan is None and "only 1.80R" in reason


def test_wrong_side_or_stale_entry_is_rejected():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100, "stop_loss": 101, "take_profit_1": 110,
        "take_profit_2": None, "confidence": 90,
        "selected_entry_zone": {"low": 99.8, "high": 100.2, "timeframe": "15m", "evidence": "Entry band."}
    }
    plan, reason = validate_trade(analysis, 100)
    assert plan is None and "not ordered" in reason
    analysis["stop_loss"] = 95
    analysis["entry"] = 102
    plan, reason = validate_trade(analysis, 100)
    assert plan is None and "away" in reason


def test_trade_without_nearby_selected_entry_zone_is_rejected():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100.0, "stop_loss": 95.0, "take_profit_1": 110.0,
        "take_profit_2": None, "confidence": 90,
        "selected_entry_zone": {"low": 98.0, "high": 99.0, "timeframe": "1h", "evidence": "Distant demand band."},
        "demand_zones": [{"low": 98.0, "high": 99.0, "timeframe": "1h", "quality": 4, "evidence": "Distant demand band."}]
    }
    plan, reason = validate_trade(analysis, 100.0)
    assert plan is None and "away from the AI selected entry zone" in reason


def test_long_trade_requires_a_nearby_quality_demand_zone():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100.0, "stop_loss": 95.0, "take_profit_1": 110.0,
        "take_profit_2": None, "confidence": 90,
        "selected_entry_zone": {"low": 99.8, "high": 100.2, "timeframe": "15m", "evidence": "Entry band."},
        "supply_zones": [{"low": 99.5, "high": 100.5, "timeframe": "15m", "quality": 5, "evidence": "Wrong side."}]
    }
    plan, reason = validate_trade(analysis, 100.0)
    assert plan is None and "demand zone" in reason.lower()

    analysis["demand_zones"] = [
        {"low": 99.5, "high": 100.5, "timeframe": "15m", "quality": 2, "evidence": "Weak demand."}
    ]
    plan, reason = validate_trade(analysis, 100.0)
    assert plan is None and "quality >= 3" in reason

    analysis["demand_zones"] = [
        {"low": 99.5, "high": 100.5, "timeframe": "15m", "quality": 4, "evidence": "Strong demand."}
    ]
    plan, reason = validate_trade(analysis, 100.0)
    assert reason == "validated"
    assert plan["primary_zone"]["side"] == "DEMAND"
    assert plan["primary_zone"]["quality"] == 4


def test_short_trade_requires_a_nearby_supply_zone():
    analysis = {
        "action": "TRADE", "direction": "SHORT", "entry_mode": "MARKET",
        "entry": 100.0, "stop_loss": 105.0, "take_profit_1": 90.0,
        "take_profit_2": None, "confidence": 90,
        "selected_entry_zone": {"low": 99.8, "high": 100.2, "timeframe": "15m", "evidence": "Supply trigger."},
        "supply_zones": [{"low": 99.5, "high": 100.5, "timeframe": "1h", "quality": 4, "evidence": "Supply rejection base."}]
    }
    plan, reason = validate_trade(analysis, 100.0)
    assert reason == "validated"
    assert plan["primary_zone"]["side"] == "SUPPLY"


def test_selected_entry_band_must_overlap_its_primary_dns_zone():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100.0, "stop_loss": 95.0, "take_profit_1": 110.0,
        "take_profit_2": None, "confidence": 90,
        "selected_entry_zone": {"low": 99.8, "high": 100.2, "timeframe": "15m", "evidence": "Entry band."},
        "demand_zones": [{"low": 99.6, "high": 99.79, "timeframe": "1h", "quality": 4, "evidence": "Non-overlapping demand."}]
    }
    plan, reason = validate_trade(analysis, 100.0)
    assert plan is None and "overlapping" in reason


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
    assert "selected_entry_zone" in ai_analyst.ANALYSIS_ITEM["required"]
    prompt = ai_analyst.SYSTEM_PROMPT.lower()
    assert "compare candidate setups" in prompt
    assert "selected_entry_zone" in prompt
    assert "select the single clearest candidate" in prompt
    assert "return no_trade" in prompt
    assert "demand and supply first" in prompt
    assert "sub-setups" in prompt
    assert "mid-range trades" in prompt


def test_analyst_accepts_exactly_one_analysis_per_requested_symbol():
    ai_analyst._validate_symbol_coverage(
        {"analyses": [{"symbol": "BTC"}, {"symbol": "ETH"}]},
        {"BTC", "ETH"}
    )


def test_analyst_rejects_duplicate_symbol_analyses():
    try:
        ai_analyst._validate_symbol_coverage(
            {"analyses": [{"symbol": "BTC"}, {"symbol": "BTC"}]},
            {"BTC", "ETH"}
        )
    except ValueError as exc:
        assert "Model symbols mismatch" in str(exc)
    else:
        raise AssertionError("duplicate model analyses must be rejected")


def test_late_tp_after_expiry_is_recorded_as_time_exit():
    triggered_at = pd.Timestamp("2026-11-01 00:00:00", tz="UTC")
    expiry_at = triggered_at + pd.Timedelta(hours=48)
    index = pd.date_range(start=triggered_at, periods=576, freq="5min")
    m5 = pd.DataFrame({
        "open": [100.0] * len(index),
        "high": [105.0] * len(index),
        "low": [99.0] * len(index),
        "close": [102.0] * len(index),
        "volume": [1000.0] * len(index)
    }, index=index)
    # This TP touch is after expiry and must not replace the confirmed TIME exit.
    post_expiry = pd.DataFrame({
        "open": [108.0], "high": [111.0], "low": [107.0],
        "close": [110.0], "volume": [1200.0]
    }, index=pd.DatetimeIndex([expiry_at]))
    m5 = pd.concat([m5, post_expiry])
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
            state, "BTC", m5, expiry_at + pd.Timedelta(hours=1),
            lambda value: str(value)
        )
    finally:
        main.discord.send_outcome = original_send

    assert "TEST123" not in state["positions"]
    assert len(state["trade_history"]) == 1
    result = state["trade_history"][0]
    assert result["status"] == "TIME"
    assert result["exit"] == 102.0
    assert result["exit_time"] == (expiry_at - pd.Timedelta(minutes=5)).isoformat()

def test_expired_trade_with_no_eligible_candles_remains_open():
    triggered_at = pd.Timestamp("2026-11-01 12:00:00", tz="UTC")
    expiry_at = triggered_at + pd.Timedelta(hours=48)
    m5 = pd.DataFrame({
        "open": [108.0], "high": [109.0], "low": [107.0],
        "close": [108.5], "volume": [1000.0]
    }, index=pd.DatetimeIndex([expiry_at]))
    state = {
        "positions": {
            "GAP125": {
                "signal_id": "GAP125", "sym": "BTC", "dir": "long",
                "triggered_at": triggered_at.isoformat(),
                "entry": 100.0, "sl": 95.0, "tp": 110.0
            }
        },
        "trade_history": [],
        "pending_outcomes": {}
    }
    manage_positions(
        state, "BTC", m5, expiry_at + pd.Timedelta(minutes=5),
        lambda value: str(value)
    )
    assert "GAP125" in state["positions"]
    assert state["trade_history"] == []
    assert state["pending_outcomes"] == {}

def test_trade_is_not_time_closed_before_expiry_when_no_post_entry_candle_exists():
    triggered_at = pd.Timestamp("2026-11-01 12:00:00", tz="UTC")
    last_pre_entry = triggered_at - pd.Timedelta(minutes=5)
    m5 = pd.DataFrame({
        "open": [100.0], "high": [101.0], "low": [99.0],
        "close": [100.5], "volume": [1000.0]
    }, index=pd.DatetimeIndex([last_pre_entry]))
    state = {
        "positions": {
            "GAP126": {
                "signal_id": "GAP126", "sym": "BTC", "dir": "long",
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
            pd.Timestamp("2026-11-03 11:59:00", tz="UTC"),
            lambda value: str(value)
        )
    finally:
        main.discord.send_outcome = original_send

    assert "GAP126" in state["positions"]
    assert state["trade_history"] == []



def test_time_exit_is_not_confirmed_when_trade_window_has_missing_bars():
    triggered_at = pd.Timestamp("2026-11-01 12:00:00", tz="UTC")
    expiry_at = triggered_at + pd.Timedelta(hours=48)
    last_eligible = expiry_at - pd.Timedelta(minutes=10)
    post_expiry = expiry_at + pd.Timedelta(minutes=10)
    m5 = pd.DataFrame({
        "open": [105.0, 108.0], "high": [106.0, 109.0],
        "low": [104.0, 107.0], "close": [105.5, 108.5],
        "volume": [1000.0, 1100.0]
    }, index=pd.DatetimeIndex([last_eligible, post_expiry]))
    state = {
        "positions": {
            "GAP127": {
                "signal_id": "GAP127", "sym": "BTC", "dir": "long",
                "triggered_at": triggered_at.isoformat(),
                "entry": 100.0, "sl": 95.0, "tp": 110.0
            }
        },
        "trade_history": [],
        "pending_outcomes": {}
    }
    manage_positions(
        state, "BTC", m5, expiry_at + pd.Timedelta(minutes=15),
        lambda value: str(value)
    )
    assert "GAP127" in state["positions"]
    assert state["trade_history"] == []

def test_tracker_does_not_accept_tp_after_a_gap_in_the_trade_window():
    triggered_at = pd.Timestamp("2026-11-01 12:00:00", tz="UTC")
    later_bar = triggered_at + pd.Timedelta(minutes=10)
    m5 = pd.DataFrame({
        "open": [100.0, 108.0],
        "high": [101.0, 111.0],
        "low": [99.0, 107.0],
        "close": [100.5, 110.0],
        "volume": [1000.0, 1100.0]
    }, index=pd.DatetimeIndex([triggered_at, later_bar]))
    state = {
        "positions": {
            "GAP129": {
                "signal_id": "GAP129", "sym": "BTC", "dir": "long",
                "triggered_at": triggered_at.isoformat(),
                "entry": 100.0, "sl": 95.0, "tp": 110.0
            }
        },
        "trade_history": [],
        "pending_outcomes": {}
    }
    manage_positions(
        state, "BTC", m5, later_bar + pd.Timedelta(minutes=5),
        lambda value: str(value)
    )
    assert "GAP129" in state["positions"]
    assert state["trade_history"] == []


def test_expired_trade_waits_for_a_price_if_no_candle_reaches_expiry():
    triggered_at = pd.Timestamp("2026-11-01 12:00:00", tz="UTC")
    last_eligible = pd.Timestamp("2026-11-03 11:50:00", tz="UTC")
    m5 = pd.DataFrame({
        "open": [105.0], "high": [106.0], "low": [104.0],
        "close": [105.5], "volume": [1000.0]
    }, index=pd.DatetimeIndex([last_eligible]))
    state = {
        "positions": {
            "GAP128": {
                "signal_id": "GAP128", "sym": "BTC", "dir": "long",
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
            pd.Timestamp("2026-11-03 12:15:00", tz="UTC"),
            lambda value: str(value)
        )
    finally:
        main.discord.send_outcome = original_send

    assert "GAP128" in state["positions"]
    assert state["trade_history"] == []


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


def test_discord_execution_alert_includes_optional_second_target():
    captured = {}
    original_post = main.discord._post
    def capture(content):
        captured["content"] = content
        return True
    main.discord._post = capture
    trade = {
        "signal_id": "FORMAT01", "dir": "long", "setup_type": "TREND_PULLBACK",
        "confidence": 86, "entry": 100.0, "sl": 95.0, "tp": 110.0, "tp2": 115.0,
        "selected_entry_zone": {"low": 99.8, "high": 100.2, "timeframe": "15m", "evidence": "Reclaim band."},
        "primary_zone": {"side": "DEMAND", "low": 99.5, "high": 100.5, "timeframe": "1h", "quality": 4, "evidence": "Demand base."},
        "rr": 2.0, "bias": "BULLISH", "timeframes_in_agreement": ["4h", "1h", "15m"],
        "rationale": "Higher-timeframe trend aligned with a confirmed pullback.",
        "invalidation": "A close below the structural swing low."
    }
    try:
        assert main.discord.send_ai_trade("BTC", trade, lambda value: f"{value:.1f}")
    finally:
        main.discord._post = original_post

    message = captured["content"]
    assert "Target 1: **110.0**" in message
    assert "Target 2: **115.0**" in message
    assert "Entry zone (15m): **99.8 – 100.2**" in message
    assert "Primary DNS (DEMAND · 1h · Q4): **99.5 – 100.5**" in message
    assert "Why: Higher-timeframe trend aligned" in message
    assert "Invalidation: A close below" in message


def test_discord_execution_alert_omits_unmeasured_confidence():
    captured = {}
    original_post = main.discord._post

    def capture(content):
        captured["content"] = content
        return True

    main.discord._post = capture
    trade = {
        "signal_id": "DNSCONF01", "dir": "long",
        "setup_type": "DNS_LIQUIDITY_SWEEP_RECLAIM",
        "entry": 100.0, "sl": 99.0, "tp": 102.5, "rr": 2.5,
    }
    try:
        assert main.discord.send_ai_trade("BTC", trade, lambda value: f"{value:.1f}")
    finally:
        main.discord._post = original_post

    message = captured["content"]
    assert "Setup: **DNS_LIQUIDITY_SWEEP_RECLAIM**" in message
    assert "Confidence:" not in message
    assert "Validated R:R to T1: **2.50R**" in message


def test_discord_execution_alert_rejects_malformed_confidence():
    captured = {}
    original_post = main.discord._post

    def capture(content):
        captured["content"] = content
        return True

    main.discord._post = capture
    trade = {
        "signal_id": "BADCONF01", "dir": "long",
        "setup_type": "DNS_LIQUIDITY_SWEEP_RECLAIM",
        "entry": 100.0, "sl": 99.0, "tp": 102.5, "rr": 2.5,
    }
    invalid_values = (
        True, False, "86", 75.5, float("nan"), float("inf"),
        -1, 101, 10**10000,
    )
    try:
        for value in invalid_values:
            captured.clear()
            trade["confidence"] = value
            assert main.discord.send_ai_trade(
                "BTC", trade, lambda price: f"{price:.1f}"
            )
            assert "Confidence:" not in captured["content"], repr(value)

        captured.clear()
        trade["confidence"] = 86.0
        assert main.discord.send_ai_trade(
            "BTC", trade, lambda price: f"{price:.1f}"
        )
        assert "Confidence: **86/100**" in captured["content"]
    finally:
        main.discord._post = original_post


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



def test_trade_gate_rejects_nonfinite_required_prices_and_zone_bounds():
    def valid_analysis():
        return {
            "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
            "entry": 100.0, "stop_loss": 95.0, "take_profit_1": 110.0,
            "take_profit_2": 115.0, "confidence": 90,
            "selected_entry_zone": {
                "low": 99.8, "high": 100.2, "timeframe": "15m",
                "evidence": "Nearby entry band."
            },
            "demand_zones": [{"low": 99.5, "high": 100.5, "timeframe": "15m", "quality": 4, "evidence": "Demand base."}]
        }

    cases = [
        ("entry", float("nan"), 100.0),
        ("stop_loss", float("inf"), 100.0),
        ("take_profit_1", float("nan"), 100.0),
        ("current_price", None, float("inf")),
        ("zone_high", float("inf"), 100.0),
    ]
    for field, bad_value, current_price in cases:
        analysis = valid_analysis()
        if field == "current_price":
            pass
        elif field == "zone_high":
            analysis["selected_entry_zone"]["high"] = bad_value
        else:
            analysis[field] = bad_value
        plan, reason = validate_trade(analysis, current_price)
        assert plan is None, f"{field} should be rejected"
        assert "finite" in reason or "invalid price bounds" in reason


def test_nonfinite_optional_second_target_is_ignored():
    analysis = {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100.0, "stop_loss": 95.0, "take_profit_1": 110.0,
        "take_profit_2": float("inf"), "confidence": 90,
        "selected_entry_zone": {
            "low": 99.8, "high": 100.2, "timeframe": "15m",
            "evidence": "Nearby entry band."
        },
        "demand_zones": [{"low": 99.5, "high": 100.5, "timeframe": "15m", "quality": 4, "evidence": "Demand base."}]
    }
    plan, reason = validate_trade(analysis, 100.0)
    assert reason == "validated"
    assert plan is not None
    assert plan["tp2"] is None

def test_discord_delivery_errors_do_not_log_webhook_secret():
    import contextlib
    import io

    webhook = "https://discord.com/api/webhooks/12345/dummy-secret-token"
    old_hook = os.environ.get("DISCORD_TRIGGER_WEBHOOK")
    old_dry_run = os.environ.get("DRY_RUN")
    original_post = main.discord.requests.post

    def fail_with_secret(*args, **kwargs):
        raise main.discord.requests.ConnectionError(f"connection failed for {webhook}")

    os.environ["DISCORD_TRIGGER_WEBHOOK"] = webhook
    os.environ.pop("DRY_RUN", None)
    main.discord.requests.post = fail_with_secret
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            delivered = main.discord._post("test alert")
    finally:
        main.discord.requests.post = original_post
        if old_hook is None:
            os.environ.pop("DISCORD_TRIGGER_WEBHOOK", None)
        else:
            os.environ["DISCORD_TRIGGER_WEBHOOK"] = old_hook
        if old_dry_run is None:
            os.environ.pop("DRY_RUN", None)
        else:
            os.environ["DRY_RUN"] = old_dry_run

    assert delivered is False
    assert webhook not in output.getvalue()
    assert "ConnectionError" in output.getvalue()


def test_historical_chunk_planner_never_exceeds_api_limit_and_has_no_time_gaps():
    step = historical_data.TIMEFRAME_SECONDS["5m"]
    start = 0
    end = step * 2001
    chunks = list(historical_data.build_chunks(start, end, step, max_candles=2000))
    assert len(chunks) == 2
    assert chunks[0] == (0, step * 2000 - 1)
    assert chunks[1] == (step * 2000, end - 1)
    assert chunks[0][1] + 1 == chunks[1][0]
    assert all(right - left + 1 <= step * 2000 for left, right in chunks)


def test_historical_parser_validates_ohlcv_and_records_missing_volume():
    payload = {"success": True, "result": [
        {"time": 300, "open": 100, "high": 102, "low": 99, "close": 101},
        {"time": 600, "open": 101, "high": 103, "low": 100, "close": 102, "volume": 50},
    ]}
    frame = historical_data.parse_candle_payload(payload, "BTCUSD", "5m", 0, 900, 2)
    assert len(frame) == 2
    assert frame.volume.iloc[0] == 0.0
    assert frame.attrs["missing_volume_rows"] == 1
    assert str(frame.index.tz) == "UTC"

    malformed = {"success": True, "result": [
        {"time": 300, "open": 100, "high": float("inf"), "low": 99, "close": 101, "volume": 1}
    ]}
    try:
        historical_data.parse_candle_payload(malformed, "BTCUSD", "5m", 0, 900, 2)
    except historical_data.HistoricalDataError as exc:
        assert "non-finite OHLCV" in str(exc)
    else:
        raise AssertionError("non-finite historical candles must be rejected")


def test_historical_fetch_retries_rate_limit_and_uses_bounded_request():
    class FakeResponse:
        def __init__(self, status_code, payload=None, headers=None):
            self.status_code = status_code
            self._payload = payload or {"success": True, "result": []}
            self.headers = headers or {}
        def raise_for_status(self):
            if self.status_code >= 400:
                import requests
                raise requests.HTTPError(f"HTTP {self.status_code}")
        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.calls = []
            self.responses = [
                FakeResponse(429, headers={"Retry-After": "1"}),
                FakeResponse(200, {"success": True, "result": [
                    {"time": 300, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 5}
                ]})
            ]
        def get(self, url, params, headers, timeout):
            self.calls.append((url, params, headers, timeout))
            return self.responses.pop(0)

    session = FakeSession()
    sleeps = []
    frame = historical_data.fetch_chunk(
        session, "BTCUSD", "5m", 0, 599, max_candles=2,
        retries=1, sleep=sleeps.append
    )
    assert len(frame) == 1
    assert len(session.calls) == 2
    assert sleeps == [1.0]
    assert session.calls[0][1] == {
        "resolution": "5m", "symbol": "BTCUSD", "start": "0", "end": "599"
    }


def test_historical_archive_persists_hash_coverage_and_resumes_after_interruption():
    import json
    import requests

    class FakeResponse:
        status_code = 200
        headers = {}
        def __init__(self, start, end):
            self._start = int(start)
            self._end = int(end)
        def raise_for_status(self):
            return None
        def json(self):
            rows = []
            for stamp in (0, 300, 600, 900):
                if self._start <= stamp <= self._end:
                    rows.append({
                        "time": stamp, "open": 100 + stamp / 1000,
                        "high": 102 + stamp / 1000, "low": 99 + stamp / 1000,
                        "close": 101 + stamp / 1000, "volume": 10
                    })
            return {"success": True, "result": rows}

    class InterruptingSession:
        def __init__(self):
            self.calls = 0
        def get(self, url, params, headers, timeout):
            self.calls += 1
            if self.calls == 2:
                raise requests.ConnectionError("simulated interruption")
            return FakeResponse(params["start"], params["end"])

    class WorkingSession:
        def __init__(self):
            self.calls = []
        def get(self, url, params, headers, timeout):
            self.calls.append(params.copy())
            return FakeResponse(params["start"], params["end"])

    with tempfile.TemporaryDirectory(prefix="salty-historical-") as folder:
        output = __import__("pathlib").Path(folder)
        interrupted = InterruptingSession()
        try:
            historical_data.download_dataset(
                "BTC", "BTCUSD", "5m", 0, 1200, output,
                session=interrupted, request_delay=0, max_candles=2,
                retries=0, sleep=lambda seconds: None
            )
        except requests.ConnectionError:
            pass
        else:
            raise AssertionError("simulated connection failure should interrupt the first run")

        resumed = WorkingSession()
        result = historical_data.download_dataset(
            "BTC", "BTCUSD", "5m", 0, 1200, output,
            session=resumed, request_delay=0, max_candles=2,
            retries=0, sleep=lambda seconds: None
        )
        assert len(resumed.calls) == 1
        assert resumed.calls[0]["start"] == "600"
        archive = output / "BTC_5m.csv"
        assert archive.exists()
        assert result["row_count"] == 4
        assert result["missing_expected_candles"] == 0
        assert result["gap_count"] == 0
        assert result["largest_gap_seconds"] == 0
        assert result["requested_coverage_pct_estimate"] == 100.0
        assert result["observed_coverage_pct"] == 100.0
        assert len(result["sha256"]) == 64
        assert historical_data.file_sha256(archive) == result["sha256"]
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["datasets"]["BTC_BTCUSD_5m"]["row_count"] == 4
        assert (output / "coverage.csv").exists()
        coverage = pd.read_csv(output / "coverage.csv")
        assert coverage.loc[0, "dataset_key"] == "BTC_BTCUSD_5m"
        assert not (output / ".work" / "BTC_5m").exists()


def test_historical_parser_includes_candle_at_inclusive_chunk_end():
    payload = {"success": True, "result": [
        {"time": 600, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 5}
    ]}
    frame = historical_data.parse_candle_payload(payload, "BTCUSD", "5m", 1, 600, 2)
    assert len(frame) == 1
    assert int(frame.index[0].timestamp()) == 600


def test_historical_fetch_does_not_retry_permanent_client_errors():
    import requests

    class BadResponse:
        status_code = 400
        headers = {}
        def raise_for_status(self):
            raise requests.HTTPError("bad request", response=self)
        def json(self):
            raise AssertionError("bad response must not be parsed")

    class FakeSession:
        def __init__(self):
            self.calls = 0
        def get(self, *args, **kwargs):
            self.calls += 1
            return BadResponse()

    session = FakeSession()
    try:
        historical_data.fetch_chunk(
            session, "BTCUSD", "5m", 0, 599, max_candles=2,
            retries=5, sleep=lambda seconds: None
        )
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("HTTP 400 must fail immediately")
    assert session.calls == 1


def test_historical_checkpoint_and_manifest_reject_malformed_json_shapes():
    with tempfile.TemporaryDirectory(prefix="salty-historical-state-") as folder:
        root = __import__("pathlib").Path(folder)
        progress = root / "progress.json"
        manifest = root / "manifest.json"
        progress.write_text("[]", encoding="utf-8")
        manifest.write_text("[]", encoding="utf-8")
        expected = {
            "symbol_alias": "BTC", "contract_symbol": "BTCUSD",
            "timeframe": "5m", "start_epoch": 0, "end_epoch": 900,
            "max_candles": 2000
        }
        assert historical_data._read_progress(progress, expected) is None
        try:
            historical_data._load_manifest(manifest)
        except historical_data.HistoricalDataError as exc:
            assert "manifest is unreadable" in str(exc)
        else:
            raise AssertionError("a non-object manifest must fail closed")


def test_historical_coverage_metrics_count_missing_intervals():
    index = pd.to_datetime([0, 300, 900], unit="s", utc=True)
    frame = pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [102.0, 103.0, 104.0],
        "low": [99.0, 100.0, 101.0],
        "close": [101.0, 102.0, 103.0],
        "volume": [1.0, 1.0, 1.0]
    }, index=index)
    metrics = historical_data._coverage_metrics(frame, 300, 0, 1200)
    assert metrics["missing_expected_candles"] == 1
    assert metrics["gap_count"] == 1
    assert metrics["largest_gap_seconds"] == 600
    assert metrics["observed_coverage_pct"] == 75.0


def test_historical_archive_excludes_currently_forming_last_candle():
    class FakeResponse:
        status_code = 200
        headers = {}
        def raise_for_status(self):
            return None
        def json(self):
            return {"success": True, "result": [
                {"time": stamp, "open": 100, "high": 102, "low": 99,
                 "close": 101, "volume": 5}
                for stamp in (0, 300, 600, 900)
            ]}

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    with tempfile.TemporaryDirectory(prefix="salty-closed-bars-") as folder:
        output = __import__("pathlib").Path(folder)
        result = historical_data.download_dataset(
            "BTC", "BTCUSD", "5m", 0, 1000, output,
            session=FakeSession(), request_delay=0, retries=0,
            sleep=lambda seconds: None
        )
        archive = pd.read_csv(output / "BTC_5m.csv", parse_dates=["timestamp"])
        assert result["row_count"] == 3
        assert archive["timestamp"].max() == pd.Timestamp("1970-01-01T00:10:00Z")
        assert pd.Timestamp(result["last_candle_close_utc"]) <= pd.Timestamp(
            "1970-01-01T00:16:40Z"
        )


def _confidence_gate_analysis(confidence):
    return {
        "action": "TRADE", "direction": "LONG", "entry_mode": "MARKET",
        "entry": 100.0, "stop_loss": 95.0, "take_profit_1": 110.0,
        "take_profit_2": None, "confidence": confidence,
        "selected_entry_zone": {
            "low": 99.8, "high": 100.2, "timeframe": "15m",
            "evidence": "Entry band."
        },
        "demand_zones": [{
            "low": 99.5, "high": 100.5, "timeframe": "1h",
            "quality": 4, "evidence": "Confirmed demand."
        }]
    }


def test_trade_validator_rejects_malformed_or_out_of_range_confidence():
    invalid_values = (
        None, "90", True, float("nan"), float("inf"),
        -1, 101, 75.5, 10**10000
    )
    for value in invalid_values:
        plan, reason = validate_trade(_confidence_gate_analysis(value), 100.0)
        assert plan is None
        assert "confidence" in reason.lower()


def test_trade_validator_accepts_confidence_boundary_and_enforces_minimum():
    plan, reason = validate_trade(_confidence_gate_analysis(75), 100.0)
    assert reason == "validated"
    assert plan["confidence"] == 75

    plan, reason = validate_trade(_confidence_gate_analysis(74), 100.0)
    assert plan is None
    assert "below the configured gate" in reason



def test_discord_outcome_alert_labels_gross_pnl_before_costs():
    captured = {}
    original_post = main.discord._post

    def capture(content):
        captured["content"] = content
        return True

    main.discord._post = capture
    trade = {
        "signal_id": "GROSS01",
        "status": "TP",
        "sym": "BTC",
        "dir": "long",
        "entry": 100.0,
        "exit": 110.0,
        "sl": 95.0,
        "tp": 110.0,
        "gross_pnl_pct": 10.0,
        "gross_R": 2.0,
    }
    try:
        assert main.discord.send_outcome(trade, lambda value: f"{value:.1f}")
    finally:
        main.discord._post = original_post

    message = captured["content"]
    assert "Gross paper P&L (before fees, spread, slippage and funding)" in message
    assert "+10.000% (+2.00R)" in message
    assert "Net P&L" not in message

def test_discord_outcome_alert_labels_gross_pnl_before_costs():
    captured = {}
    original_post = main.discord._post

    def capture(content):
        captured["content"] = content
        return True

    main.discord._post = capture
    trade = {
        "signal_id": "GROSS01",
        "status": "TP",
        "sym": "BTC",
        "dir": "long",
        "entry": 100.0,
        "exit": 110.0,
        "sl": 95.0,
        "tp": 110.0,
        "gross_pnl_pct": 10.0,
        "gross_R": 2.0,
    }
    try:
        assert main.discord.send_outcome(trade, lambda value: f"{value:.1f}")
    finally:
        main.discord._post = original_post

    message = captured["content"]
    assert "Gross paper P&L (before fees, spread, slippage and funding)" in message
    assert "+10.000% (+2.00R)" in message
    assert "Net P&L" not in message
