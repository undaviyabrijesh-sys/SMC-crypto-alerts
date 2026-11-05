"""Offline tests for the deterministic OHLCV event-replay engine."""
import unittest

import numpy as np
import pandas as pd

from quant_backtest import (
    BacktestConfig,
    BacktestError,
    chronological_splits,
    run_backtest,
    validate_ohlcv,
)


def make_bars(rows, offsets=None):
    base = pd.Timestamp("2026-01-01T00:00:00Z")
    if offsets is None:
        offsets = [i * 300 for i in range(len(rows))]
    index = base + pd.to_timedelta(offsets, unit="s")
    return pd.DataFrame(rows, index=index, columns=["open", "high", "low", "close"])


def make_signals(index, signals):
    rows = [{"side": 0, "stop_price": np.nan, "target_price": np.nan}
            for _ in index]
    for bar_number, side, stop, target in signals:
        rows[bar_number] = {
            "side": side, "stop_price": stop, "target_price": target
        }
    return pd.DataFrame(rows, index=index)


def config(**overrides):
    values = {
        "timeframe_seconds": 300,
        "fee_bps_per_side": 0.0,
        "slippage_bps_per_side": 0.0,
        "initial_capital": 100_000.0,
        "risk_fraction": 0.01,
        "max_leverage": 10.0,
    }
    values.update(overrides)
    return BacktestConfig(**values)


class TestBacktestInputValidation(unittest.TestCase):
    def test_rejects_duplicate_timestamps(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [101, 103, 100, 102],
        ], offsets=[0, 0])
        with self.assertRaises(BacktestError):
            validate_ohlcv(bars, 300)

    def test_rejects_out_of_order_timestamps_instead_of_sorting(self):
        bars = make_bars([
            [101, 103, 100, 102],
            [100, 102, 99, 101],
        ], offsets=[300, 0])
        with self.assertRaises(BacktestError):
            validate_ohlcv(bars, 300)

    def test_rejects_non_finite_or_invalid_ohlc(self):
        for row in (
            [100, np.inf, 99, 101],
            [100, 98, 99, 97],
            [0, 102, 99, 101],
        ):
            with self.subTest(row=row):
                with self.assertRaises(BacktestError):
                    validate_ohlcv(make_bars([row]), 300)

    def test_rejects_signal_timestamp_not_in_bars(self):
        bars = make_bars([[100, 102, 99, 101]])
        signal = make_signals(bars.index, [])
        signal.index = signal.index + pd.Timedelta(minutes=1)
        with self.assertRaises(BacktestError):
            run_backtest(bars, signal, config())

    def test_rejects_invalid_signal_side(self):
        bars = make_bars([[100, 102, 99, 101], [101, 103, 100, 102]])
        signal = pd.DataFrame(
            [{"side": 2, "stop_price": 98, "target_price": 105}],
            index=[bars.index[0]],
        )
        with self.assertRaises(BacktestError):
            run_backtest(bars, signal, config())


class TestDeterministicReplay(unittest.TestCase):
    def test_enters_next_bar_and_exits_at_target(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [102, 104, 101, 103],
            [103, 109, 102, 108],
            [108, 109, 107, 108],
        ])
        signals = make_signals(bars.index, [(0, 1, 98, 108)])
        result = run_backtest(bars, signals, config())
        trade = result["trades"].iloc[0]
        self.assertEqual(trade["signal_time"], bars.index[0])
        self.assertEqual(trade["entry_time"], bars.index[1])
        self.assertEqual(trade["exit_time"], bars.index[2])
        self.assertGreater(trade["entry_time"], trade["signal_time"])
        self.assertEqual(trade["exit_reason"], "TP")
        self.assertAlmostEqual(trade["net_r"], 1.5, places=8)
        self.assertAlmostEqual(result["metrics"]["ending_equity_cash_units"], 101_500.0, places=6)

    def test_same_bar_stop_and_target_is_stop_first(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [100, 106, 94, 100],
            [100, 101, 99, 100],
        ])
        signals = make_signals(bars.index, [(0, 1, 95, 105)])
        result = run_backtest(bars, signals, config())
        trade = result["trades"].iloc[0]
        self.assertEqual(trade["exit_reason"], "SL_SAME_BAR_AMBIGUITY")
        self.assertTrue(bool(trade["same_bar_ambiguous"]))
        self.assertAlmostEqual(trade["net_r"], -1.0, places=8)
        self.assertEqual(result["metrics"]["same_bar_ambiguous_exits"], 1)

    def test_short_side_stop_and_target(self):
        bars = make_bars([
            [100, 101, 98, 99],
            [99, 100, 96, 97],
            [97, 98, 92, 93],
        ])
        signals = make_signals(bars.index, [(0, -1, 103, 93)])
        result = run_backtest(bars, signals, config())
        trade = result["trades"].iloc[0]
        self.assertEqual(trade["side"], "SHORT")
        self.assertEqual(trade["exit_reason"], "TP")
        self.assertAlmostEqual(trade["net_r"], 1.5, places=8)

    def test_fees_and_slippage_are_charged_on_both_sides(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [102, 104, 101, 103],
            [103, 109, 102, 108],
        ])
        signals = make_signals(bars.index, [(0, 1, 98, 108)])
        result = run_backtest(
            bars, signals,
            config(fee_bps_per_side=10.0, slippage_bps_per_side=10.0),
        )
        trade = result["trades"].iloc[0]
        self.assertGreater(trade["fees_cash_units"], 0)
        self.assertGreater(trade["slippage_r"], 0)
        self.assertLess(trade["net_r"], trade["gross_r"])
        self.assertFalse(result["metrics"]["funding_included"])
        self.assertEqual(result["metrics"]["cost_model_status"], "PARTIAL_FEES_AND_SLIPPAGE_ONLY")

    def test_gap_forces_flat_at_next_observed_open_and_is_reported(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [102, 104, 101, 103],
            [100, 103, 99, 101],
            [101, 102, 100, 101],
        ], offsets=[0, 300, 900, 1200])
        signals = make_signals(bars.index, [(0, 1, 98, 110)])
        result = run_backtest(bars, signals, config())
        trade = result["trades"].iloc[0]
        self.assertEqual(trade["exit_reason"], "DATA_GAP")
        self.assertEqual(result["metrics"]["data_gap_events"], 1)
        self.assertEqual(result["metrics"]["missing_intervals_observed"], 1)
        self.assertEqual(len(result["data_gaps"]), 1)

    def test_pending_entry_is_cancelled_when_next_bar_follows_a_gap(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [101, 103, 100, 102],
            [102, 103, 101, 102],
        ], offsets=[0, 600, 900])
        signals = make_signals(bars.index, [(0, 1, 98, 110)])
        result = run_backtest(bars, signals, config())
        self.assertTrue(result["trades"].empty)
        self.assertEqual(result["metrics"]["skipped_entries"], 1)
        self.assertEqual(result["metrics"]["data_gap_events"], 1)

    def test_open_position_is_closed_at_end_of_data(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [101, 103, 100, 102],
            [102, 104, 101, 103],
        ])
        signals = make_signals(bars.index, [(0, 1, 90, 120)])
        result = run_backtest(bars, signals, config())
        self.assertEqual(result["trades"].iloc[0]["exit_reason"], "END_OF_DATA")
        self.assertFalse(bool(result["equity_curve"].iloc[-1]["position_open"]))

    def test_none_signals_means_no_trades(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [101, 103, 100, 102],
        ])
        result = run_backtest(bars, None, config())
        self.assertTrue(result["trades"].empty)
        self.assertEqual(result["metrics"]["total_trades"], 0)

    def test_pending_signal_on_last_bar_is_not_filled(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [101, 103, 100, 102],
        ])
        signals = make_signals(bars.index, [(1, 1, 98, 110)])
        result = run_backtest(bars, signals, config())
        self.assertTrue(result["trades"].empty)
        self.assertEqual(result["metrics"]["skipped_entries"], 1)

    def test_equity_does_not_subtract_fees_twice(self):
        bars = make_bars([
            [100, 102, 99, 101],
            [102, 104, 101, 103],
            [103, 109, 102, 108],
        ])
        signals = make_signals(bars.index, [(0, 1, 98, 108)])
        result = run_backtest(bars, signals, config(fee_bps_per_side=10.0))
        trade = result["trades"].iloc[0]
        self.assertAlmostEqual(
            trade["net_pnl_cash"],
            trade["gross_pnl_cash_units"] - trade["fees_cash_units"],
            places=6,
        )
        self.assertAlmostEqual(
            trade["equity_after"],
            trade["equity_before"] + trade["net_pnl_cash"],
            places=6,
        )


class TestChronologicalValidation(unittest.TestCase):
    def test_splits_are_ordered_and_apply_purge_embargo(self):
        frame = pd.DataFrame({"x": range(100)})
        parts = chronological_splits(
            frame, 0.60, 0.20, 0.20, purge_bars=2, embargo_bars=3
        )
        self.assertEqual(len(parts["train"]), 58)
        self.assertEqual(len(parts["validation"]), 15)
        self.assertEqual(len(parts["test"]), 17)
        self.assertLess(parts["train"].index.max(), parts["validation"].index.min())
        self.assertLess(parts["validation"].index.max(), parts["test"].index.min())

    def test_rejects_invalid_split_fractions(self):
        frame = pd.DataFrame({"x": range(100)})
        with self.assertRaises(BacktestError):
            chronological_splits(frame, 0.7, 0.2, 0.2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
