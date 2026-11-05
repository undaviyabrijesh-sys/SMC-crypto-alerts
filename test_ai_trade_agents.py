"""Offline contract tests for the opt-in Bull/Bear/Chief Trader review."""
import unittest

import pandas as pd

import ai_trade_agents


def _inputs():
    index = pd.date_range("2026-11-05T10:00:00Z", periods=3, freq="5min")
    frame = pd.DataFrame({
        "open": [100.0, 100.1, 100.2],
        "high": [100.4, 100.5, 100.8],
        "low": [99.8, 99.9, 100.0],
        "close": [100.2, 100.3, 100.7],
        "volume": [10.0, 11.0, 12.0],
    }, index=index)
    candidate = {
        "symbol": "BTC", "direction": "LONG", "setup_type": "DNS_LIQUIDITY_SWEEP_RECLAIM",
        "entry": 100.7, "stop_loss": 98.0, "take_profit": 106.1, "rr": 2.0,
        "zone_id": "ZONE1", "zone_side": "DEMAND",
    }
    snapshot = {
        "symbol": "BTC", "revision": 3, "mapped_at": "2026-11-05T08:00:00Z",
        "reference_price": 100.0, "bias": "BULLISH", "structure_summary": "Higher-timeframe demand.",
        "demand_zones": [{"low": 99.0, "high": 100.0, "timeframe": "1h", "quality": 4, "status": "ACTIVE", "evidence": "Base and displacement"}],
        "supply_zones": [{"low": 108.0, "high": 109.0, "timeframe": "4h", "quality": 4, "status": "ACTIVE", "evidence": "Bearish departure"}],
        "liquidity_levels": [{"price": 107.0, "kind": "EQH", "timeframe": "1h", "evidence": "Repeated highs"}],
        "key_observations": ["Price is holding above mapped demand."],
    }
    return candidate, snapshot, {"5m": frame}


class AgentReviewTests(unittest.TestCase):
    def test_disabled_review_does_not_call_any_agent(self):
        candidate, snapshot, frames = _inputs()

        def unexpected(*args):
            raise AssertionError("agent should not be called while disabled")

        result = ai_trade_agents.review_candidate(
            candidate, snapshot, frames, enabled_override=False, call_agent=unexpected
        )
        self.assertEqual(result["status"], "DISABLED")

    def test_runs_independent_bull_bear_then_chief_and_approves(self):
        candidate, snapshot, frames = _inputs()
        calls = []

        def fake_agent(role, evidence):
            calls.append(role)
            if role == "CHIEF_TRADER":
                self.assertIn("bull_researcher_report", evidence)
                self.assertIn("bear_researcher_report", evidence)
                return {
                    "decision": "APPROVE",
                    "rationale": "The demand reaction is supported.",
                    "key_risks": ["Nearby supply remains a target constraint."],
                }
            stance = "SUPPORT" if role == "BULL_RESEARCHER" else "CHALLENGE"
            return {
                "stance": stance,
                "summary": role,
                "evidence": ["Closed bar supports the report."],
                "risks": ["No order-book depth is available."],
            }

        result = ai_trade_agents.review_candidate(
            candidate, snapshot, frames, enabled_override=True, call_agent=fake_agent
        )
        self.assertEqual(calls, ["BULL_RESEARCHER", "BEAR_RESEARCHER", "CHIEF_TRADER"])
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(result["trader"]["decision"], "APPROVE")
        self.assertEqual(result["bull"]["stance"], "SUPPORT")
        self.assertEqual(result["bear"]["stance"], "CHALLENGE")

    def test_no_trade_and_reject_are_both_fail_closed(self):
        candidate, snapshot, frames = _inputs()
        for decision in ("NO_TRADE", "REJECT"):
            def fake_agent(role, evidence, chosen=decision):
                if role == "CHIEF_TRADER":
                    return {
                        "decision": chosen,
                        "rationale": "Evidence is insufficient.",
                        "key_risks": ["Counter-evidence."],
                    }
                return {
                    "stance": "MIXED", "summary": "Mixed",
                    "evidence": [], "risks": ["Contradiction."],
                }

            result = ai_trade_agents.review_candidate(
                candidate, snapshot, frames, enabled_override=True, call_agent=fake_agent
            )
            self.assertEqual(result["status"], "REJECTED")

    def test_malformed_agent_output_fails_closed(self):
        candidate, snapshot, frames = _inputs()
        result = ai_trade_agents.review_candidate(
            candidate, snapshot, frames, enabled_override=True,
            call_agent=lambda role, evidence: {"unexpected": "shape"},
        )
        self.assertEqual(result["status"], "ERROR")

    def test_evidence_packet_uses_last_three_closed_bars(self):
        candidate, snapshot, frames = _inputs()
        evidence = ai_trade_agents._market_evidence(candidate, snapshot, frames)
        self.assertEqual(len(evidence["closed_ohlcv_last_three_bars_by_timeframe"]["5m"]), 3)
        self.assertEqual(evidence["market_map"]["revision"], 3)
        self.assertIn("No order-book depth", evidence["data_limits"][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
