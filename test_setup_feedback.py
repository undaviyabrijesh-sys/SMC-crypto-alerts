"""Tests for historical/live setup feedback passed to the visual analyst."""
import unittest
from datetime import datetime, timedelta, timezone

from main import build_recent_setup_feedback


class SetupFeedbackTests(unittest.TestCase):
    def test_groups_only_closed_finite_trades_by_symbol_and_setup(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        trades = [
            {"sym": "BTC", "setup_type": "SWEEP", "exit_time": (base + timedelta(hours=i)).isoformat(),
             "gross_R": 1.0 if i % 2 == 0 else -1.0, "status": "TP" if i % 2 == 0 else "SL"}
            for i in range(10)
        ]
        trades.append({"sym": "ETH", "setup_type": "TREND", "gross_R": 1.0})
        trades.append({"sym": "BTC", "setup_type": "SWEEP",
                       "exit_time": base.isoformat(), "gross_R": float("nan")})
        result = build_recent_setup_feedback(trades)
        btc = result["BTC|SWEEP"]
        self.assertEqual(btc["closed_paper_trades"], 10)
        self.assertEqual(btc["wins"], 5)
        self.assertEqual(btc["losses"], 5)
        self.assertEqual(btc["sum_gross_R"], 0.0)
        self.assertEqual(btc["sample_reliability"], "LOW_SAMPLE")
        self.assertNotIn("ETH|TREND", result)

    def test_lookback_uses_only_the_most_recent_observations(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        trades = [
            {"sym": "ETH", "setup_type": "BREAKOUT",
             "exit_time": (base + timedelta(days=i)).isoformat(),
             "gross_R": -1.0 if i < 5 else 2.0, "status": "TP"}
            for i in range(35)
        ]
        result = build_recent_setup_feedback(trades, lookback_per_setup=30)
        row = result["ETH|BREAKOUT"]
        self.assertEqual(row["closed_paper_trades"], 30)
        self.assertEqual(row["wins"], 30)
        self.assertEqual(row["sample_reliability"], "OBSERVATIONAL_ONLY")

    def test_empty_history_returns_no_feedback(self):
        self.assertEqual(build_recent_setup_feedback([]), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
