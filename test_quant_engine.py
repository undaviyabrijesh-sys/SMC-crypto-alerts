"""Offline tests for the AI-free multi-strategy quant supervisor."""
import unittest

import numpy as np
import pandas as pd

import quant_strategies
import quant_supervisor
import quant_worker
import discord
import trade_lifecycle
from unittest.mock import patch


def candidate(strategy_id="TREND_PULLBACK", direction="LONG", score=84):
    entry, stop, target = (100.0, 98.0, 104.4) if direction == "LONG" else (100.0, 102.0, 95.6)
    return {
        "strategy_id": strategy_id,
        "setup_type": strategy_id,
        "direction": direction,
        "entry": entry,
        "stop_loss": stop,
        "take_profit": target,
        "rr": 2.2,
        "quality_score": score,
        "score_type": "RULE_QUALITY_POINTS_NOT_PROBABILITY",
        "atr_15m": 2.0,
        "stop_atr": 1.0,
        "signal_candle": "2026-11-05T12:00:00+00:00",
        "triggered_at": "2026-11-05T12:05:00+00:00",
        "timeframes_in_agreement": ["4h", "1h", "15m", "5m"],
        "rationale": "Deterministic test fixture.",
        "invalidation": "Stop level.",
    }


def frames_with_optional_gap(timeframe_gap=None):
    minutes = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
    rows = {}
    for timeframe, step in minutes.items():
        count = 100
        index = pd.date_range("2026-01-01T00:00:00Z", periods=count, freq=f"{step}min")
        close = np.linspace(100.0, 120.0, count)
        frame = pd.DataFrame({
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(count, 100.0),
        }, index=index)
        if timeframe == timeframe_gap:
            frame = frame.drop(index[-10])
        rows[timeframe] = frame
    return rows


class TestDeterministicCandidateEngine(unittest.TestCase):
    def test_strategy_families_are_independent_and_explicit(self):
        names = {strategy.__name__ for strategy in quant_strategies.STRATEGIES}
        self.assertEqual(names, {
            "_trend_pullback",
            "_breakout_retest",
            "_volatility_expansion",
            "_liquidity_sweep",
            "_mean_reversion",
            "_momentum_continuation",
        })

    def test_gap_in_recent_closed_candles_blocks_strategy_evaluation(self):
        frames = frames_with_optional_gap("5m")
        self.assertEqual(quant_strategies.generate_candidates("BTC", frames), [])

    def test_valid_complete_data_returns_a_list_without_raising(self):
        candidates = quant_strategies.generate_candidates("BTC", frames_with_optional_gap())
        self.assertIsInstance(candidates, list)

    def test_candidate_generation_does_not_require_ai_or_dns_modules(self):
        self.assertNotIn("ai_analyst", quant_worker.__dict__)
        self.assertNotIn("dns_worker", quant_worker.__dict__)
        self.assertNotIn("main", quant_worker.__dict__)

    def test_short_gold_weekly_history_keeps_lower_timeframe_evaluation_available(self):
        frames = frames_with_optional_gap()
        frames["1w"] = frames["1w"].tail(29)
        self.assertEqual(len(frames["1w"]), 29)
        self.assertIsInstance(quant_strategies.generate_candidates("XAU", frames), list)


class TestQuantSupervisor(unittest.TestCase):
    def test_unapproved_candidate_is_research_only_and_never_selected(self):
        item = candidate()
        result = quant_supervisor.select_candidate(
            [item], 100.0, latest_candle=item["signal_candle"], approved_strategy_ids=()
        )
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertIsNone(result["selected"])
        self.assertEqual(result["preview"]["strategy_id"], "TREND_PULLBACK")

    def test_approved_candidate_is_selected_only_after_all_mechanical_gates(self):
        item = candidate()
        result = quant_supervisor.select_candidate(
            [item], 100.0, latest_candle=item["signal_candle"],
            approved_strategy_ids={"TREND_PULLBACK"},
        )
        self.assertEqual(result["status"], "SELECTED")
        self.assertEqual(result["selected"]["strategy_id"], "TREND_PULLBACK")

    def test_opposing_candidates_with_close_scores_return_no_trade(self):
        long = candidate("TREND_PULLBACK", "LONG", 84)
        short = candidate("MEAN_REVERSION", "SHORT", 80)
        result = quant_supervisor.select_candidate(
            [long, short], 100.0, latest_candle=long["signal_candle"],
            approved_strategy_ids={"TREND_PULLBACK", "MEAN_REVERSION"},
        )
        self.assertEqual(result["status"], "NO_TRADE")
        self.assertIsNone(result["selected"])
        self.assertIn("conflicting", result["reason"])

    def test_open_position_blocks_new_candidate(self):
        item = candidate()
        result = quant_supervisor.select_candidate(
            [item], 100.0, latest_candle=item["signal_candle"],
            has_open_position=True, approved_strategy_ids={"TREND_PULLBACK"},
        )
        self.assertEqual(result["status"], "NO_TRADE")
        self.assertIsNone(result["selected"])

    def test_invalid_rr_stop_and_stale_candidate_are_rejected(self):
        item = candidate()
        item["take_profit"] = 103.0
        ok, reason = quant_supervisor.validate_candidate(item, 100.0, item["signal_candle"])
        self.assertFalse(ok)
        self.assertIn("2R", reason)

        item = candidate()
        item["stop_loss"] = 99.8
        item["rr"] = 22.0  # Keep the fixture internally consistent so the ATR gate is reached.
        ok, reason = quant_supervisor.validate_candidate(item, 100.0, item["signal_candle"])
        self.assertFalse(ok)
        self.assertIn("ATR", reason)

        item = candidate()
        ok, reason = quant_supervisor.validate_candidate(item, 100.0, "2026-11-05T12:05:00+00:00")
        self.assertFalse(ok)
        self.assertIn("stale", reason)

    def test_bad_quality_score_and_nonfinite_price_are_rejected(self):
        for bad_score in (True, 74, 75.5, 101):
            item = candidate()
            item["quality_score"] = bad_score
            ok, _ = quant_supervisor.validate_candidate(item, 100.0, item["signal_candle"])
            self.assertFalse(ok)
        item = candidate()
        item["entry"] = float("nan")
        ok, _ = quant_supervisor.validate_candidate(item, 100.0, item["signal_candle"])
        self.assertFalse(ok)

    def test_quant_discord_alert_is_execution_focused_and_does_not_claim_probability(self):
        captured = {}
        original = discord._post
        discord._post = lambda message: captured.setdefault("message", message) and True
        trade = {
            "signal_id": "QNT001", "dir": "long", "setup_type": "TREND_PULLBACK",
            "strategy_id": "TREND_PULLBACK", "quality_score": 84, "entry": 100.0,
            "sl": 98.0, "tp": 104.4, "rr": 2.2,
            "timeframes_in_agreement": ["4h", "1h", "15m", "5m"],
            "rationale": "4h/1h trend with a confirmed 15m pullback.",
            "invalidation": "Close below the pullback swing low.",
        }
        try:
            self.assertTrue(discord.send_quant_trade("BTC", trade, lambda value: f"{value:.1f}"))
        finally:
            discord._post = original
        message = captured["message"]
        self.assertIn("SALTY QUANT — LONG BTC", message)
        self.assertIn("Rule quality: **84/100** (rubric points, not probability)", message)
        self.assertIn("Validated R:R: **2.20R**", message)
        self.assertNotIn("Confidence", message)
        self.assertNotIn("WATCH", message)

    def test_quant_worker_lifecycle_closes_tp_on_contiguous_closed_candles(self):
        triggered = pd.Timestamp("2026-11-05T12:00:00Z")
        index = pd.date_range(triggered, periods=2, freq="5min")
        bars = pd.DataFrame({
            "open": [100.0, 104.0], "high": [104.5, 105.0],
            "low": [99.0, 103.0], "close": [104.0, 104.5],
            "volume": [10.0, 10.0],
        }, index=index)
        trade = {
            "signal_id": "LIFECYCLE1", "sym": "BTC", "dir": "long",
            "entry": 100.0, "sl": 98.0, "tp": 104.0,
            "triggered_at": triggered.isoformat(),
        }
        state = {"positions": {"LIFECYCLE1": trade}, "trade_history": []}
        with patch.object(trade_lifecycle.discord, "send_outcome", return_value=True):
            trade_lifecycle.manage_positions(
                state, "BTC", bars, triggered + pd.Timedelta(minutes=10),
                lambda value: f"{value:.1f}",
            )
        self.assertNotIn("LIFECYCLE1", state["positions"])
        self.assertEqual(state["trade_history"][0]["status"], "TP")

    def test_quant_worker_lifecycle_leaves_position_open_across_missing_5m_bar(self):
        triggered = pd.Timestamp("2026-11-05T12:00:00Z")
        index = pd.to_datetime(
            ["2026-11-05T12:00:00Z", "2026-11-05T12:10:00Z"], utc=True
        )
        bars = pd.DataFrame({
            "open": [100.0, 104.0], "high": [101.0, 105.0],
            "low": [99.0, 103.0], "close": [100.5, 104.5],
            "volume": [10.0, 10.0],
        }, index=index)
        trade = {
            "signal_id": "GAPSAFE1", "sym": "BTC", "dir": "long",
            "entry": 100.0, "sl": 98.0, "tp": 104.0,
            "triggered_at": triggered.isoformat(),
        }
        state = {"positions": {"GAPSAFE1": trade}, "trade_history": []}
        with patch.object(trade_lifecycle.discord, "send_outcome", return_value=True):
            trade_lifecycle.manage_positions(
                state, "BTC", bars, triggered + pd.Timedelta(minutes=15),
                lambda value: f"{value:.1f}",
            )
        self.assertIn("GAPSAFE1", state["positions"])
        self.assertEqual(state["trade_history"], [])

    def test_quant_worker_records_shadow_candidate_without_discord_execution_alert(self):
        frames = frames_with_optional_gap()
        signal_time = frames["5m"].index[-1].isoformat()
        item = candidate()
        item.update({
            "entry": 120.0, "stop_loss": 118.0, "take_profit": 124.4,
            "signal_candle": signal_time,
            "triggered_at": (frames["5m"].index[-1] + pd.Timedelta(minutes=5)).isoformat(),
        })
        state = {"positions": {}, "pending_outcomes": {}, "quant_last_candle": {}}
        records = []
        with (
            patch.object(quant_worker.C, "SYMBOLS", {"BTC": {"delta_symbol": "BTCUSD", "dp": 1}}),
            patch.object(quant_worker.st, "load", return_value=state),
            patch.object(quant_worker.st, "save"),
            patch.object(quant_worker.data, "fetch_bundle", return_value=frames),
            patch.object(quant_worker.data, "freshness", return_value=(True, "fresh")),
            patch.object(quant_worker, "manage_positions"),
            patch.object(quant_worker.quant_strategies, "generate_candidates", return_value=[item]),
            patch.object(quant_worker, "_append_record", side_effect=records.append),
            patch.object(quant_worker.discord, "send_quant_trade") as send,
        ):
            quant_worker.run(now=pd.Timestamp("2026-11-05T12:10:00Z"), fetcher=lambda *args, **kwargs: None)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision_status"], "RESEARCH_ONLY")
        self.assertEqual(records[0]["research_preview_strategy"], "TREND_PULLBACK")
        send.assert_not_called()
        self.assertEqual(state["positions"], {})
        self.assertEqual(state["quant_last_candle"]["BTC"], signal_time)


if __name__ == "__main__":
    unittest.main(verbosity=2)
