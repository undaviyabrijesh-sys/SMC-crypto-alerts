"""Offline tests for the visual-first market pipeline. No API key or network needed."""
import os
import tempfile
import pandas as pd

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="salty-quant-data-")

import data
from main import validate_trade
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


def test_visual_chart_png_contains_all_panels():
    frames = {
        "1d": candles("1D", 110), "4h": candles("4h", 110),
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
