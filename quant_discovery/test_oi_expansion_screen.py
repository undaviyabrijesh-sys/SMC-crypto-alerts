"""Offline tests for the exploratory OI expansion research screen."""
import unittest

import numpy as np
import pandas as pd

from oi_expansion_screen import (
    add_features,
    align_oi_close_time,
    resample_complete_hours,
    simulate,
)


class OIExpansionScreenTests(unittest.TestCase):
    def test_resampler_excludes_incomplete_hours(self):
        index = pd.date_range("2026-01-01T00:00:00Z", periods=23, freq="5min")
        frame = pd.DataFrame({
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
        }, index=index)
        result = resample_complete_hours(frame)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.index[0], pd.Timestamp("2026-01-01T01:00:00Z"))

    def test_oi_close_is_aligned_to_end_of_hour(self):
        oi = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z"]),
            "close": [123.0],
        })
        result = align_oi_close_time(oi)
        self.assertEqual(result.index[0], pd.Timestamp("2026-01-01T01:00:00Z"))
        self.assertEqual(result.iloc[0], 123.0)

    def test_rolling_thresholds_exclude_the_current_bar(self):
        index = pd.date_range("2026-01-01T00:00:00Z", periods=200, freq="1h")
        close = 100.0 * (1.0001 ** np.arange(200))
        close[-1] = close[-2] * 1.02
        oi = 100.0 + np.arange(200)
        oi[-1] = 1000.0
        frame = pd.DataFrame({
            "open": close, "high": close * 1.001, "low": close * 0.999,
            "close": close, "oi": oi,
        }, index=index)
        result = add_features(frame)
        self.assertLess(result.iloc[-1].absret_q90, abs(result.iloc[-1].ret1))
        self.assertLess(result.iloc[-1].oi_q80, result.iloc[-1].oi_pct)

    def test_same_bar_stop_and_target_is_resolved_stop_first(self):
        index = pd.date_range("2026-01-01T00:00:00Z", periods=10, freq="1h")
        frame = pd.DataFrame({
            "open": [100.0] * 10, "high": [101.0] * 10,
            "low": [99.0] * 10, "close": [100.0] * 10,
            "ret1": [0.0] * 10, "absret_q90": [0.001] * 10,
            "oi_q80": [0.001] * 10, "oi_q90": [0.001] * 10,
            "oi_pct": [0.002] * 10, "atr14": [1.0] * 10,
        }, index=index)
        frame.loc[index[0], "ret1"] = 0.01
        frame.loc[index[1], "high"] = 103.0
        frame.loc[index[1], "low"] = 98.0
        trades = simulate(frame, 0, 10, oi_quantile=0.80, stop_atr=1.0, target_r=2.0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["outcome"], "SL")
        self.assertLess(trades[0]["net_R"], -1.0)

    def test_higher_round_trip_cost_reduces_expectancy(self):
        index = pd.date_range("2026-01-01T00:00:00Z", periods=10, freq="1h")
        frame = pd.DataFrame({
            "open": [100.0] * 10, "high": [101.0] * 10,
            "low": [99.0] * 10, "close": [100.0] * 10,
            "ret1": [0.0] * 10, "absret_q90": [0.001] * 10,
            "oi_q80": [0.001] * 10, "oi_q90": [0.001] * 10,
            "oi_pct": [0.002] * 10, "atr14": [1.0] * 10,
        }, index=index)
        frame.loc[index[0], "ret1"] = 0.01
        frame.loc[index[1], ["high", "low", "close"]] = [103.0, 100.0, 102.0]
        low_cost = simulate(frame, 0, 10, oi_quantile=0.80, stop_atr=1.0, target_r=2.0, cost_bps=10)
        high_cost = simulate(frame, 0, 10, oi_quantile=0.80, stop_atr=1.0, target_r=2.0, cost_bps=20)
        self.assertEqual(len(low_cost), 1)
        self.assertEqual(len(high_cost), 1)
        self.assertLess(high_cost[0]["net_R"], low_cost[0]["net_R"])


if __name__ == "__main__":
    unittest.main()
