"""Offline tests for persistent DNS maps and the local sweep/reclaim watcher."""
import tempfile
from unittest.mock import patch

import pandas as pd

import dns_engine
import dns_worker


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
        "high": [102, 100.7, 101.5],
        "low": [100.5, 98.8, 100.0],
        "close": [101.2, 100.6, 100.8],
        "volume": [10, 12, 11],
    }, index=idx)
    # Keep the entry within the configured 0.35% distance of the mapped demand band.
    snap = dns_engine.validate_analysis("BTC", _analysis(), idx[-1], 100.8)
    snap["demand_zones"][0]["low"] = 100.0
    snap["demand_zones"][0]["high"] = 100.5
    candidates = dns_engine.detect_local_setup(
        "BTC", {"5m": frame, "1h": pd.DataFrame({"close": [100.8]})}, snap
    )
    assert len(candidates) == 1, candidates
    candidate = candidates[0]
    assert candidate["direction"] == "LONG"
    assert candidate["setup_type"] == "DNS_LIQUIDITY_SWEEP_RECLAIM"
    assert candidate["rr"] >= 2
    assert candidate["zone_side"] == "DEMAND"



def _setup_test_frames(base=100.0, trend=1):
    idx = pd.date_range("2026-11-05T00:00:00Z", periods=60, freq="5min")
    m5 = pd.DataFrame({
        "open": [base] * 60,
        "high": [base + 0.2] * 60,
        "low": [base - 0.2] * 60,
        "close": [base] * 60,
        "volume": [100.0] * 60,
    }, index=idx)
    m15_index = pd.date_range(end=idx[-1], periods=60, freq="15min")
    closes = [95.0 + (6.0 * i / 59) for i in range(60)] if trend > 0 else [115.0 - (6.0 * i / 59) for i in range(60)]
    m15 = pd.DataFrame({
        "open": closes,
        "high": [x + 0.2 for x in closes],
        "low": [x - 0.2 for x in closes],
        "close": closes,
        "volume": [100.0] * 60,
    }, index=m15_index)
    h1_close = 101.0 if trend > 0 else 109.8
    h1 = pd.DataFrame({"close": [h1_close] * 60}, index=pd.date_range(end=idx[-1], periods=60, freq="1h"))
    h4 = pd.DataFrame({"close": [h1_close] * 60}, index=pd.date_range(end=idx[-1], periods=60, freq="4h"))
    return {"5m": m5, "15m": m15, "1h": h1, "4h": h4}


def _setup_test_map(side="DEMAND"):
    demand = {
        "zone_id": "DEMAND1", "side": "DEMAND", "low": 100.0, "high": 100.5,
        "timeframe": "1h", "quality": 4, "evidence": "AI visual demand", "status": "ACTIVE",
    }
    supply = {
        "zone_id": "SUPPLY1", "side": "SUPPLY", "low": 110.0, "high": 110.5,
        "timeframe": "4h", "quality": 4, "evidence": "AI visual supply", "status": "ACTIVE",
    }
    return {
        "revision": 4,
        "demand_zones": [demand] if side == "DEMAND" else [{
            **demand, "low": 99.5, "high": 100.0,
        }],
        "supply_zones": [supply] if side == "DEMAND" else [{
            **supply, "low": 109.5, "high": 110.0,
        }],
    }


def test_dns_zone_rejection_bos_choch_and_trend_pullback_are_separate_candidates():
    frames = _setup_test_frames(trend=1)
    m5 = frames["5m"]
    m5.iloc[-2, m5.columns.get_loc("open")] = 100.2
    m5.iloc[-2, m5.columns.get_loc("high")] = 100.6
    m5.iloc[-2, m5.columns.get_loc("low")] = 100.0
    m5.iloc[-2, m5.columns.get_loc("close")] = 100.3
    m5.iloc[-1, m5.columns.get_loc("open")] = 100.5
    m5.iloc[-1, m5.columns.get_loc("high")] = 101.0
    m5.iloc[-1, m5.columns.get_loc("low")] = 100.4
    m5.iloc[-1, m5.columns.get_loc("close")] = 100.8

    candidates = dns_engine.detect_local_setup("BTC", frames, _setup_test_map())
    setup_types = {item["setup_type"] for item in candidates}
    assert "DNS_DEMAND_REJECTION" in setup_types
    assert "DNS_BOS_CHOCH_BULLISH" in setup_types
    assert "DNS_TREND_PULLBACK" in setup_types
    assert all(item["zone_side"] == "DEMAND" and item["rr"] >= 2 for item in candidates)


def test_dns_fvg_retrace_requires_imbalance_overlap_with_visual_demand():
    frames = _setup_test_frames(trend=1)
    m5 = frames["5m"]
    # A bullish three-candle FVG [99.9, 100.1] overlaps the mapped demand band.
    for offset, values in {
        -5: (99.8, 100.0, 99.6, 99.8),
        -4: (99.9, 101.0, 99.8, 100.8),
        -3: (100.3, 100.7, 100.1, 100.5),
        -2: (100.0, 100.2, 99.8, 100.0),
        -1: (100.5, 100.9, 100.05, 100.8),
    }.items():
        for col, value in zip(("open", "high", "low", "close"), values):
            m5.iloc[offset, m5.columns.get_loc(col)] = value
    candidates = dns_engine.detect_local_setup("BTC", frames, _setup_test_map())
    assert any(item["setup_type"] == "DNS_FVG_RETRACE" for item in candidates)


def test_dns_rbs_and_sbr_require_break_retest_and_follow_through():
    long_frames = _setup_test_frames(trend=1)
    long_bars = {
        -8: (99.7, 99.9, 99.5, 99.7),
        -7: (100.0, 100.4, 99.9, 100.2),
        -6: (100.4, 101.0, 100.3, 100.8),  # Close above mapped resistance.
        -5: (100.7, 100.9, 100.3, 100.6),  # Retest and hold the flipped band.
        -1: (100.5, 101.0, 100.4, 100.8),  # Confirm above the previous high.
    }
    for offset, values in long_bars.items():
        for col, value in zip(("open", "high", "low", "close"), values):
            long_frames["5m"].iloc[offset, long_frames["5m"].columns.get_loc(col)] = value
    long_candidates = dns_engine.detect_local_setup("BTC", long_frames, _setup_test_map("DEMAND"))
    assert any(item["setup_type"] == "DNS_RBS_RETEST" for item in long_candidates)

    short_frames = _setup_test_frames(base=110.0, trend=-1)
    short_bars = {
        -8: (110.3, 110.5, 110.1, 110.3),
        -7: (110.1, 110.2, 109.7, 109.9),
        -6: (109.8, 109.9, 109.0, 109.2),  # Close below mapped support.
        -5: (109.3, 109.7, 109.1, 109.4),  # Retest and reject the flipped band.
        -1: (109.4, 109.5, 108.8, 109.2),  # Confirm below the previous low, still near mapped supply.
    }
    for offset, values in short_bars.items():
        for col, value in zip(("open", "high", "low", "close"), values):
            short_frames["5m"].iloc[offset, short_frames["5m"].columns.get_loc(col)] = value
    short_candidates = dns_engine.detect_local_setup("BTC", short_frames, _setup_test_map("SUPPLY"))
    assert any(item["setup_type"] == "DNS_SBR_RETEST" for item in short_candidates)


def test_local_watcher_skips_a_sweep_when_recent_five_minute_bars_have_a_gap():
    idx = pd.DatetimeIndex([
        "2026-11-05T00:00:00Z",
        "2026-11-05T00:05:00Z",
        "2026-11-05T00:15:00Z",
    ])
    frame = pd.DataFrame({
        "open": [101.0, 99.5, 100.1],
        "high": [102.0, 100.7, 101.5],
        "low": [100.5, 98.8, 100.0],
        "close": [101.2, 100.6, 100.8],
        "volume": [10.0, 12.0, 11.0],
    }, index=idx)
    snap = dns_engine.validate_analysis("BTC", _analysis(), idx[-1], 100.8)
    snap["demand_zones"][0]["low"] = 100.0
    snap["demand_zones"][0]["high"] = 100.5
    frames = {"5m": frame, "1h": pd.DataFrame({"close": [100.8]})}
    assert dns_engine.detect_local_setup("BTC", frames, snap) == []


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


def _run_worker_refresh_case(now, state, mapper, refresh_check_fails=False, agent_reviewer=None, candidate_extra=None):
    """Run one isolated worker cycle and return detector/alert call counts."""
    import os
    import tempfile
    from unittest.mock import patch
    import dns_worker

    idx = pd.date_range(end=now - pd.Timedelta(minutes=5), periods=3, freq="5min")
    frame = pd.DataFrame({
        "open": [100.0, 100.0, 100.0],
        "high": [101.0, 101.0, 101.0],
        "low": [99.0, 99.0, 99.0],
        "close": [100.5, 100.5, 100.5],
        "volume": [10.0, 10.0, 10.0],
    }, index=idx)
    frames = {"5m": frame}
    map_state = {
        "schema_version": 1,
        "symbols": {
            "BTC": {
                "symbol": "BTC", "bias": "BULLISH",
                "mapped_at": (now - pd.Timedelta(hours=5)).isoformat(),
                "revision": 1, "demand_zones": [], "supply_zones": [],
            }
        },
        "history": {},
    }
    candidate = {
        "zone_id": "ZONE1", "setup_type": "DNS_LIQUIDITY_SWEEP_RECLAIM",
        "event_candle": idx[-1].isoformat(), "direction": "LONG",
        "zone_side": "DEMAND", "zone_low": 99.8, "zone_high": 100.2,
        "zone_timeframe": "1h", "zone_quality": 4,
        "entry": 100.5, "stop_loss": 98.0, "take_profit": 105.5, "rr": 2.0,
    }

    def save_map(map_data, symbol, analysis, observed_at, price):
        snapshot = {
            "symbol": symbol, "bias": "BULLISH", "revision": 2,
            "demand_zones": [], "supply_zones": [],
        }
        map_data.setdefault("symbols", {})[symbol] = snapshot
        return snapshot

    with tempfile.TemporaryDirectory(prefix="salty-worker-refresh-") as folder:
        with patch.dict(os.environ, {"DNS_RESEARCH_PATH": os.path.join(folder, "maps.jsonl")}):
            with patch.object(dns_worker.C, "SYMBOLS", {
                "BTC": {"delta_symbol": "BTCUSD", "kind": "crypto", "dp": 1}
            }), patch.object(dns_worker.st, "load", return_value=state), \
                 patch.object(dns_worker.st, "save"), \
                 patch.object(dns_worker.dns_engine, "load_map", return_value=map_state), \
                 patch.object(dns_worker.data, "fetch_bundle", return_value=frames), \
                 patch.object(dns_worker.data, "freshness", return_value=(True, "fresh")), \
                 patch.object(dns_worker.main, "manage_positions"), \
                 patch.object(
                     dns_worker.dns_engine, "refresh_reasons",
                     side_effect=RuntimeError("simulated map validation failure") if refresh_check_fails else None,
                     return_value=["SCHEDULED_REFRESH"]
                 ), \
                 patch.object(dns_worker.dns_engine, "save_analysis", side_effect=save_map), \
                 patch.object(dns_worker.main, "build_context", return_value={}), \
                 patch.object(dns_worker, "render_symbol_chart", return_value=b"test-png"), \
                 patch.object(dns_worker.main, "_save_zone_review_chart"), \
                 patch.object(
                     dns_worker.dns_engine, "detect_local_setup",
                     return_value=[candidate] + ([candidate_extra] if candidate_extra else [])
                 ) as detector, \
                 patch.object(dns_worker.discord, "send_ai_trade", return_value=True) as alert:
                dns_worker.run(
                    now=now, fetcher=lambda *args, **kwargs: None,
                    mapper=mapper, agent_reviewer=agent_reviewer
                )
                return detector.call_count, alert.call_count


def test_worker_allows_candidate_after_explicit_agent_approval():
    from unittest.mock import Mock
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    state = {"positions": {}, "pending_alerts": {}, "pending_outcomes": {}}
    mapper = lambda *args, **kwargs: ({"analyses": [{"symbol": "BTC"}]}, {"model": "test"})
    reviewer = Mock(return_value={
        "status": "APPROVED", "decision": "APPROVE",
        "bull": {"stance": "SUPPORT"}, "bear": {"stance": "CHALLENGE"},
        "trader": {"rationale": "The setup survived the debate."},
    })
    detector_calls, alert_calls = _run_worker_refresh_case(
        now, state, mapper, agent_reviewer=reviewer
    )
    assert detector_calls == 1
    assert alert_calls == 1
    reviewer.assert_called_once()


def test_worker_debates_only_the_highest_ranked_candidate_per_symbol_cycle():
    from unittest.mock import Mock
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    state = {"positions": {}, "pending_alerts": {}, "pending_outcomes": {}}
    mapper = lambda *args, **kwargs: ({"analyses": [{"symbol": "BTC"}]}, {"model": "test"})
    second = {
        "zone_id": "ZONE2", "setup_type": "DNS_LIQUIDITY_SWEEP_RECLAIM",
        "event_candle": "2026-11-05T14:55:00+00:00", "direction": "LONG",
        "zone_side": "DEMAND", "zone_low": 99.7, "zone_high": 100.3,
        "zone_timeframe": "4h", "zone_quality": 5,
        "entry": 100.5, "stop_loss": 98.0, "take_profit": 105.5, "rr": 2.2,
    }
    reviewer = Mock(return_value={
        "status": "APPROVED", "decision": "APPROVE",
        "bull": {"stance": "SUPPORT"}, "bear": {"stance": "CHALLENGE"},
        "trader": {"rationale": "Reviewed."},
    })
    detector_calls, alert_calls = _run_worker_refresh_case(
        now, state, mapper, agent_reviewer=reviewer, candidate_extra=second
    )
    assert detector_calls == 1
    assert alert_calls == 1
    reviewer.assert_called_once()
    assert reviewer.call_args.args[0]["zone_quality"] == 5


def test_worker_vetoes_candidate_when_agents_reject_or_error():
    from unittest.mock import Mock
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    mapper = lambda *args, **kwargs: ({"analyses": [{"symbol": "BTC"}]}, {"model": "test"})
    for review in (
        {"status": "REJECTED", "decision": "NO_TRADE"},
        {"status": "ERROR", "error": "quota"},
        {"status": "COOLDOWN", "reason": "cooldown"},
    ):
        state = {"positions": {}, "pending_alerts": {}, "pending_outcomes": {}}
        reviewer = Mock(return_value=review)
        detector_calls, alert_calls = _run_worker_refresh_case(
            now, state, mapper, agent_reviewer=reviewer
        )
        assert detector_calls == 1
        assert alert_calls == 0
        reviewer.assert_called_once()


def test_worker_blocks_new_entries_while_refresh_is_throttled():
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    state = {
        "positions": {}, "pending_alerts": {}, "pending_outcomes": {},
        "dns_refresh_attempts": {"BTC": (now - pd.Timedelta(minutes=10)).isoformat()},
    }
    def mapper_must_not_run(*args, **kwargs):
        raise AssertionError("refresh should be throttled in this test")
    detector_calls, alert_calls = _run_worker_refresh_case(now, state, mapper_must_not_run)
    assert detector_calls == 0
    assert alert_calls == 0


def test_worker_blocks_new_entries_when_ai_refresh_fails():
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    state = {"positions": {}, "pending_alerts": {}, "pending_outcomes": {}}
    def failed_mapper(*args, **kwargs):
        raise RuntimeError("simulated API quota failure")
    detector_calls, alert_calls = _run_worker_refresh_case(now, state, failed_mapper)
    assert detector_calls == 0
    assert alert_calls == 0


def test_worker_blocks_new_entries_when_refresh_omits_symbol():
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    state = {"positions": {}, "pending_alerts": {}, "pending_outcomes": {}}
    def partial_mapper(*args, **kwargs):
        return {"analyses": []}, {"model": "test"}
    detector_calls, alert_calls = _run_worker_refresh_case(now, state, partial_mapper)
    assert detector_calls == 0
    assert alert_calls == 0


def test_worker_scans_again_after_successful_map_refresh():
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    state = {"positions": {}, "pending_alerts": {}, "pending_outcomes": {}}
    def successful_mapper(*args, **kwargs):
        return {"analyses": [{"symbol": "BTC"}]}, {"model": "test"}
    detector_calls, alert_calls = _run_worker_refresh_case(now, state, successful_mapper)
    assert detector_calls == 1
    assert alert_calls == 1


def test_worker_blocks_new_entries_when_refresh_check_raises():
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    state = {"positions": {}, "pending_alerts": {}, "pending_outcomes": {}}
    def mapper_must_not_run(*args, **kwargs):
        raise AssertionError("AI refresh should not run after map validation failed")
    detector_calls, alert_calls = _run_worker_refresh_case(
        now, state, mapper_must_not_run, refresh_check_fails=True
    )
    assert detector_calls == 0
    assert alert_calls == 0


def _pending_trade(direction="long"):
    if direction == "long":
        stop, target = 98.0, 104.0
        primary_side = "DEMAND"
    else:
        stop, target = 102.0, 96.0
        primary_side = "SUPPLY"
    zone = {"low": 99.8, "high": 100.2, "timeframe": "1h", "evidence": "AI visual zone"}
    return {
        "signal_id": "PENDING1", "sym": "BTC", "dir": direction,
        "entry": 100.0, "sl": stop, "tp": target, "rr": 2.0,
        "analysis_time": "2026-11-05T15:10:00Z",
        "triggered_at": "2026-11-05T15:10:00Z",
        "selected_entry_zone": zone,
        "primary_zone": {
            "side": primary_side, "low": 99.8, "high": 100.2,
            "timeframe": "1h", "quality": 4, "evidence": "AI visual zone",
        },
    }


def _pending_snapshot(direction="long"):
    zone = {
        "low": 99.8, "high": 100.2, "timeframe": "1h",
        "quality": 4, "evidence": "Current AI visual map",
    }
    return {
        "demand_zones": [zone] if direction == "long" else [],
        "supply_zones": [zone] if direction == "short" else [],
    }


def test_pending_alert_revalidation_reprices_only_if_still_actionable():
    trade = _pending_trade("long")
    snapshot = _pending_snapshot("long")
    accepted = dns_worker._reprice_pending_alert(trade, 99.95, snapshot)
    assert accepted is not None
    assert accepted["entry"] == 99.95
    assert accepted["rr"] >= 2.0
    assert accepted["primary_zone"]["quality"] == 4

    # A 0.5% move is beyond the existing entry-deviation limit.
    assert dns_worker._reprice_pending_alert(trade, 100.5, snapshot) is None
    # A small move can still destroy the required 2R even while near the zone.
    assert dns_worker._reprice_pending_alert(trade, 100.1, snapshot) is None


def test_pending_alert_revalidation_supports_short_side():
    trade = _pending_trade("short")
    accepted = dns_worker._reprice_pending_alert(
        trade, 100.05, _pending_snapshot("short")
    )
    assert accepted is not None
    assert accepted["entry"] == 100.05
    assert accepted["rr"] >= 2.0
    assert accepted["primary_zone"]["side"] == "SUPPLY"


def test_pending_alert_revalidation_requires_current_directional_map_overlap():
    trade = _pending_trade("long")
    stale_map = {
        "demand_zones": [{
            "low": 101.0, "high": 102.0, "timeframe": "1h",
            "quality": 5, "evidence": "Different zone",
        }],
        "supply_zones": [],
    }
    assert dns_worker._reprice_pending_alert(trade, 99.95, stale_map) is None


def _run_pending_alert_case(current_price):
    now = pd.Timestamp("2026-11-05T15:15:00Z")
    index = pd.date_range("2026-11-05T15:00:00Z", periods=3, freq="5min")
    frame = pd.DataFrame({
        "open": [100.0, 100.0, current_price],
        "high": [100.2, 100.2, current_price + 0.1],
        "low": [99.8, 99.8, current_price - 0.1],
        "close": [100.0, 100.0, current_price],
        "volume": [10.0, 10.0, 10.0],
    }, index=index)
    trade = _pending_trade("long")
    state = {
        "positions": {}, "pending_alerts": {"PENDING1": trade},
        "pending_outcomes": {}, "dns_refresh_attempts": {},
    }
    snapshot = _pending_snapshot("long")
    map_state = {"symbols": {"BTC": snapshot}, "history": {}}

    with (
        patch.object(dns_worker.C, "SYMBOLS", {
            "BTC": {"delta_symbol": "BTCUSD", "kind": "crypto", "dp": 1}
        }),
        patch.object(dns_worker.st, "load", return_value=state),
        patch.object(dns_worker.st, "save"),
        patch.object(dns_worker.dns_engine, "load_map", return_value=map_state),
        patch.object(dns_worker.data, "fetch_bundle", return_value={"5m": frame}),
        patch.object(dns_worker.data, "freshness", return_value=(True, "fresh")),
        patch.object(dns_worker.dns_engine, "refresh_reasons", return_value=[]),
        patch.object(dns_worker.main, "manage_positions"),
        patch.object(dns_worker.dns_engine, "detect_local_setup", return_value=[]),
        patch.object(dns_worker.discord, "send_ai_trade", return_value=True) as alert,
    ):
        dns_worker.run(now=now, fetcher=lambda *args, **kwargs: None)
        return state, alert


def test_worker_reprices_pending_alert_at_latest_closed_candle_before_delivery():
    state, alert = _run_pending_alert_case(99.95)
    assert alert.call_count == 1
    sent_trade = alert.call_args.args[1]
    assert sent_trade["entry"] == 99.95
    assert sent_trade["rr"] >= 2.0
    assert sent_trade["triggered_at"] == "2026-11-05T15:15:00+00:00"
    assert state["positions"]["PENDING1"]["entry"] == 99.95
    assert "PENDING1" not in state["pending_alerts"]


def test_worker_discards_pending_alert_when_price_has_moved_too_far():
    state, alert = _run_pending_alert_case(100.5)
    assert alert.call_count == 0
    assert "PENDING1" not in state["pending_alerts"]


def test_worker_keeps_managing_positions_when_dns_map_is_unreadable():
    now = pd.Timestamp("2026-11-05T15:00:00Z")
    idx = pd.date_range(end=now - pd.Timedelta(minutes=5), periods=3, freq="5min")
    frame = pd.DataFrame({
        "open": [100.0, 100.0, 100.0],
        "high": [101.0, 101.0, 101.0],
        "low": [99.0, 99.0, 99.0],
        "close": [100.5, 100.5, 100.5],
        "volume": [10.0, 10.0, 10.0],
    }, index=idx)
    state = {
        "positions": {"OPEN1": {"sym": "BTC", "signal_id": "OPEN1"}},
        "pending_alerts": {}, "pending_outcomes": {}, "dns_refresh_attempts": {},
    }

    def mapper_must_not_run(*args, **kwargs):
        raise AssertionError("an unreadable map must not be overwritten by an automatic refresh")

    with patch.object(dns_worker.C, "SYMBOLS", {
        "BTC": {"delta_symbol": "BTCUSD", "kind": "crypto", "dp": 1}
    }), patch.object(dns_worker.st, "load", return_value=state), \
         patch.object(dns_worker.st, "save") as save_state, \
         patch.object(dns_worker.dns_engine, "load_map", side_effect=RuntimeError("corrupt map")), \
         patch.object(dns_worker.data, "fetch_bundle", return_value={"5m": frame}), \
         patch.object(dns_worker.data, "freshness", return_value=(True, "fresh")), \
         patch.object(dns_worker.main, "manage_positions") as manage, \
         patch.object(dns_worker.dns_engine, "detect_local_setup") as detector, \
         patch.object(dns_worker.discord, "send_ai_trade") as alert:
        dns_worker.run(now=now, fetcher=lambda *args, **kwargs: None, mapper=mapper_must_not_run)

    manage.assert_called_once()
    detector.assert_not_called()
    alert.assert_not_called()
    save_state.assert_called_once()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
