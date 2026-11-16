"""Offline tests for defined-risk option-selling research replay."""
import unittest

import pandas as pd

from options_research import ResearchConfig
from options_selling import _select_vertical, _simulate_vertical


def bars(times, rows):
    return pd.DataFrame(rows, index=pd.DatetimeIndex(times),
                        columns=["open", "high", "low", "close", "volume"])


def test_cfg():
    return ResearchConfig(
        min_dte_days=1, max_dte_days=300, max_entry_delay_hours=2,
        stop_loss_pct=0.30, take_profit_pct=0.50, max_hold_hours=2,
        fee_bps_per_side=0.0, spread_bps_per_side=0.0,
        slippage_bps_per_side=0.0, gap_penalty_bps=100.0,
        initial_equity=10000.0, risk_fraction=0.01,
    )


def contract(symbol, strike, opt_type, expiry, frame):
    return {"symbol": symbol, "strike": float(strike), "option_type": opt_type,
            "expiry": pd.Timestamp(expiry), "bars": frame}


class TestCreditSpreadReplay(unittest.TestCase):
    def setUp(self):
        self.signal_time = pd.Timestamp("2026-05-20T00:00:00Z")
        self.entry_time = self.signal_time + pd.Timedelta(hours=1)
        self.expiry = pd.Timestamp("2026-12-25T00:00:00Z")
        self.signal = pd.Series({"strategy_id": "OPT-01_MOMENTUM", "direction": "LONG"})

    def test_selects_same_expiry_otm_put_and_lower_protective_put(self):
        idx = [self.entry_time, self.entry_time + pd.Timedelta(hours=1)]
        frame = bars(idx, [[100, 101, 99, 100, 1], [90, 91, 89, 90, 1]])
        data = {
            "short": contract("BTC-261225-70000-P", 70000, "PUT", self.expiry, frame),
            "hedge": contract("BTC-261225-65000-P", 65000, "PUT", self.expiry, frame),
            "wrong_side": contract("BTC-261225-80000-P", 80000, "PUT", self.expiry, frame),
        }
        selected = _select_vertical(data, "PUT", "PUT", 76000, self.signal_time, test_cfg())
        self.assertIsNotNone(selected)
        short, hedge, entry = selected
        self.assertEqual(short["symbol"], "BTC-261225-70000-P")
        self.assertEqual(hedge["symbol"], "BTC-261225-65000-P")
        self.assertEqual(entry, self.entry_time)

    def test_entry_candle_is_not_reused_for_stop_or_target(self):
        idx = [self.entry_time, self.entry_time + pd.Timedelta(hours=1)]
        short_frame = bars(idx, [[100, 100, 100, 100, 1], [250, 260, 240, 250, 1]])
        hedge_frame = bars(idx, [[50, 50, 50, 50, 1], [50, 55, 45, 50, 1]])
        short = contract("BTC-261225-70000-P", 70000, "PUT", self.expiry, short_frame)
        hedge = contract("BTC-261225-65000-P", 65000, "PUT", self.expiry, hedge_frame)
        trade, equity = _simulate_vertical(
            "BTC", "OPT-06_BULL_PUT_CREDIT", self.signal_time, "LONG",
            76000, short, hedge, self.entry_time, test_cfg(), 10000, "train"
        )
        self.assertIsNotNone(trade)
        self.assertEqual(trade["exit_reason"], "SL")
        self.assertEqual(trade["exit_time"], (self.entry_time + pd.Timedelta(hours=2)).isoformat())
        self.assertLess(equity, 10000)

    def test_sparse_synchronized_observations_are_flagged(self):
        idx = [self.entry_time, self.entry_time + pd.Timedelta(hours=10)]
        short_frame = bars(idx, [[100, 100, 100, 100, 1], [110, 115, 105, 110, 1]])
        hedge_frame = bars(idx, [[50, 50, 50, 50, 1], [50, 55, 45, 50, 1]])
        short = contract("BTC-261225-70000-P", 70000, "PUT", self.expiry, short_frame)
        hedge = contract("BTC-261225-65000-P", 65000, "PUT", self.expiry, hedge_frame)
        trade, _ = _simulate_vertical(
            "BTC", "OPT-06_BULL_PUT_CREDIT", self.signal_time, "LONG",
            76000, short, hedge, self.entry_time, test_cfg(), 10000, "train"
        )
        self.assertEqual(trade["exit_reason"], "GAP_GUARD_EXIT")
        self.assertEqual(trade["data_quality_flag"], "GAP_GUARD_EXIT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
