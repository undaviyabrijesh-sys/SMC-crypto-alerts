"""Offline tests for persistent DNS maps and the local sweep/reclaim watcher."""
import tempfile
import pandas as pd

import dns_engine


def _analysis():
    return {
        "symbol": "BTC", "bias": "BULLISH", "structure_summary": "Higher-timeframe demand.",
        "demand_zones": [
            {"low": 99, "high": 100, "timeframe": "1h", "quality": 4, "evidence": "Base then displacement."},
            {"low": 98, "high": 98.5, "timeframe": "4h", "quality": 2, "evidence": "Weak zone."},
        ],
        "supply_zones": [
            {"low": 110, "high": 111, "timeframe": "4h", "quality": 5, "evidence": "Clear bearish departure."}
        ],
        "liquidity_levels": [{"price": 105, "kind": "EQH", "timeframe": "1h", "evidence": "Repeated highs."}],
        "key_observations": ["Price is above demand."]
    }


def test_ai_map_is_validated_versioned_and_persisted():
    with tempfile.TemporaryDirectory() as folder:
        path = folder + "/dns.json"
        state = {"schema_version": 1, "symbols": {}, "history": {}}
        first = dns_engine.save_analysis(
            state, "BTC", _analysis(), "2026-11-05T00:00:00Z", 105, path
        )
        assert first["revision"] == 1
        assert len(first["demand_zones"]) == 2  # Preserve the full AI map, including weak zones.
        assert first["demand_zones"][0]["zone_id"]
        second = dns_engine.save_analysis(
            state, "BTC", _analysis(), "2026-11-05T04:00:00Z", 106, path
        )
        assert second["revision"] == 2
        loaded = dns_engine.load_map(path)
        assert loaded["symbols"]["BTC"]["revision"] == 2
        assert len(loaded["history"]["BTC"]) == 1


def test_refresh_due_on_missing_map_age_and_zone_break():
    now = pd.Timestamp("2026-11-05T08:00:00Z")
    frames = {"1h": pd.DataFrame({"close": [100.2, 98.5]})}
    assert dns_engine.refresh_reasons(None, now, frames) == ["NO_EXISTING_MAP"]
    snap = dns_engine.validate_analysis("BTC", _analysis(), "2026-11-05T00:00:00Z", 105)
    reasons = dns_engine.refresh_reasons(snap, now, frames)
    assert "SCHEDULED_REFRESH" in reasons
    assert "DEMAND_ZONE_BROKEN" in reasons


def test_local_watcher_confirms_demand_sweep_and_requires_two_r():
    idx = pd.date_range("2026-11-05T00:00:00Z", periods=3, freq="5min")
    frame = pd.DataFrame({
        "open": [101, 99.5, 100.1],
        "high": [102, 100.2, 101.5],
        "low": [100.5, 98.8, 100.0],
        "close": [101.2, 100.6, 100.8],
        "volume": [10, 12, 11],
    }, index=idx)
    # Keep the entry within the configured 0.35% distance of the mapped demand band.
    snap = dns_engine.validate_analysis("BTC", _analysis(), idx[-1], 100.8)
    snap["demand_zones"][0]["low"] = 100.0
    snap["demand_zones"][0]["high"] = 100.5
    candidates = dns_engine.detect_local_setup("BTC", {"5m": frame}, snap)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["direction"] == "LONG"
    assert candidate["setup_type"] == "DNS_LIQUIDITY_SWEEP_RECLAIM"
    assert candidate["rr"] >= 2
    assert candidate["zone_side"] == "DEMAND"


def test_local_watcher_rejects_confirmation_too_far_from_visual_zone():
    idx = pd.date_range("2026-11-05T00:00:00Z", periods=3, freq="5min")
    frame = pd.DataFrame({
        "open": [101, 99.5, 100.1],
        "high": [102, 100.2, 101.5],
        "low": [100.5, 98.8, 100.0],
        "close": [101.2, 100.5, 101.4],
        "volume": [10, 12, 11],
    }, index=idx)
    snap = dns_engine.validate_analysis("BTC", _analysis(), idx[-1], 101.4)
    # The existing demand band ends at 100.0: the confirmation is >0.35% away.
    assert dns_engine.detect_local_setup("BTC", {"5m": frame}, snap) == []


def test_local_watcher_does_not_signal_without_opposing_target():
    idx = pd.date_range("2026-11-05T00:00:00Z", periods=3, freq="5min")
    frame = pd.DataFrame({
        "open": [101, 99.5, 100.1], "high": [102, 100.2, 101.5],
        "low": [100.5, 98.8, 100.0], "close": [101.2, 100.5, 101.4],
        "volume": [10, 12, 11],
    }, index=idx)
    snap = dns_engine.validate_analysis("BTC", _analysis(), idx[-1], 101.4)
    snap["supply_zones"] = []
    assert dns_engine.detect_local_setup("BTC", {"5m": frame}, snap) == []


def test_zone_invalidation_uses_the_zone_own_timeframe():
    now = pd.Timestamp("2026-11-05T08:00:00Z")
    snap = dns_engine.validate_analysis("BTC", _analysis(), "2026-11-05T07:00:00Z", 105)
    snap["demand_zones"][0]["timeframe"] = "4h"
    frames = {
        "1h": pd.DataFrame({"close": [98.5]}),
        "4h": pd.DataFrame({"close": [100.5]}),
    }
    reasons = dns_engine.refresh_reasons(snap, now, frames)
    assert "DEMAND_ZONE_BROKEN" not in reasons

    frames["4h"] = pd.DataFrame({"close": [98.5]})
    reasons = dns_engine.refresh_reasons(snap, now, frames)
    assert "DEMAND_ZONE_BROKEN" in reasons
