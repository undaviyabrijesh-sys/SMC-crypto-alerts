"""Synthetic/offline checks for the options research event-replay engine."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import options_research as research


def option_bars(index, rows):
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index), columns=["open", "high", "low", "close", "volume"])


def cfg(**overrides):
    values = {
        "min_dte_days": 1, "max_dte_days": 90,
        "max_entry_delay_hours": 1.0, "stop_loss_pct": 0.30,
        "take_profit_pct": 0.50, "max_hold_hours": 2,
        "fee_bps_per_side": 0.0, "spread_bps_per_side": 0.0,
        "slippage_bps_per_side": 0.0, "gap_penalty_bps": 100.0,
        "initial_equity": 10_000.0, "risk_fraction": 0.01,
        "max_premium_notional_pct": 0.25, "min_qty": 0.01, "qty_step": 0.01,
    }
    values.update(overrides)
    return research.ResearchConfig(**values)


class TestInputValidation(unittest.TestCase):
    def test_parses_contract_identity(self):
        meta = research.parse_option_symbol("BTC-261225-65000-C")
        self.assertEqual(meta["asset"], "BTC")
        self.assertEqual(meta["option_type"], "CALL")
        self.assertEqual(meta["strike"], 65000.0)
        self.assertEqual(meta["expiry"], pd.Timestamp("2026-12-25T00:00:00Z"))
        self.assertIsNone(research.parse_option_symbol("BTCUSDT"))

    def test_rejects_duplicate_and_invalid_candles(self):
        idx = pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"])
        bad = option_bars(idx, [[100, 102, 99, 101, 10], [101, 103, 100, 102, 10]])
        with self.assertRaises(research.OptionsResearchError):
            research.validate_ohlcv(bad, "test")
        bad2 = option_bars(pd.date_range("2026-01-01", periods=1, freq="h", tz="UTC"), [[100, 98, 99, 97, 10]])
        with self.assertRaises(research.OptionsResearchError):
            research.validate_ohlcv(bad2, "test")

    def test_no_trade_placeholder_rows_are_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / "BTC-261225-65000-C.csv"
            pd.DataFrame({
                "open_time_utc": ["2026-11-01T00:00:00Z", "2026-11-01T01:00:00Z"],
                "open": [100, 100], "high": [101, 101], "low": [99, 99], "close": [100, 100],
                "volume": [0, 2], "trade_count": [0, 1],
            }).to_csv(path, index=False)
            bars = research._read_time_indexed_csv(path, "fixture")
            self.assertEqual(len(bars), 1)
            self.assertEqual(float(bars.iloc[0]["volume"]), 2.0)


class TestSignals(unittest.TestCase):
    def test_strategies_are_named_and_do_not_signal_before_lookback(self):
        idx = pd.date_range("2026-01-01T00:00:00Z", periods=180, freq="h")
        close = pd.Series(np.linspace(100, 150, len(idx)), index=idx)
        frame = pd.DataFrame({"open": close.shift(1).fillna(close.iloc[0]),
                              "high": close * 1.01, "low": close * 0.99,
                              "close": close, "volume": 1000.0}, index=idx)
        signals = research.generate_signals(frame)
        self.assertEqual(set(signals), {
            "OPT-01_MOMENTUM", "OPT-02_SWEEP_MSS", "OPT-03_EMA_PULLBACK",
            "OPT-04_LONG_STRADDLE", "OPT-05_LONG_STRANGLE",
        })
        for signal_frame in signals.values():
            if not signal_frame.empty:
                self.assertTrue((signal_frame.index >= idx[50]).all())

    def test_gap_invalidates_recent_signal_window(self):
        idx = pd.date_range("2026-01-01T00:00:00Z", periods=130, freq="h").delete(80)
        close = pd.Series(np.linspace(100, 140, len(idx)), index=idx)
        frame = pd.DataFrame({"open": close.shift(1).fillna(close.iloc[0]),
                              "high": close * 1.01, "low": close * 0.99,
                              "close": close, "volume": 1000.0}, index=idx)
        signals = research.generate_signals(frame)
        # No signal may be generated until 50 consecutive hourly observations have followed the gap.
        gap_time = pd.Timestamp("2026-01-04T08:00:00Z")
        for signal_frame in signals.values():
            if signal_frame.empty:
                continue
            post_gap = signal_frame.index[signal_frame.index > gap_time]
            if len(post_gap):
                self.assertGreaterEqual(post_gap.min(), gap_time + pd.Timedelta(hours=50))


class TestSingleLegReplay(unittest.TestCase):
    def setUp(self):
        self.signal_time = pd.Timestamp("2026-11-01T09:00:00Z")
        self.entry_time = self.signal_time + pd.Timedelta(hours=1)
        self.signal = pd.Series({"strategy_id": "OPT-01_MOMENTUM", "direction": "LONG", "reason": "fixture"})
        self.meta = research.parse_option_symbol("BTC-261125-65000-C")

    def test_enters_after_signal_and_stop_wins_same_bar_ambiguity(self):
        bars = option_bars(
            [self.entry_time, self.entry_time + pd.Timedelta(hours=1)],
            [[100, 160, 60, 120, 10], [120, 125, 110, 115, 10]],
        )
        contract = {**self.meta, "symbol": "BTC-261125-65000-C", "bars": bars}
        trade, equity = research._single_trade(self.signal_time, self.signal, 65000,
                                               contract, self.entry_time, bars.iloc[0], cfg(), 10000)
        self.assertIsNotNone(trade)
        self.assertEqual(trade["entry_time"], self.entry_time.isoformat())
        self.assertEqual(trade["exit_reason"], "SL_SAME_BAR_AMBIGUITY")
        self.assertTrue(trade["same_bar_ambiguous"])
        self.assertEqual(trade["held_hours"], 1.0)
        self.assertLess(equity, 10000)

    def test_gap_guard_does_not_infer_unobserved_tp_or_sl(self):
        bars = option_bars(
            [self.entry_time, self.entry_time + pd.Timedelta(hours=3)],
            [[100, 110, 95, 105, 10], [200, 230, 180, 210, 10]],
        )
        contract = {**self.meta, "symbol": "BTC-261125-65000-C", "bars": bars}
        trade, _ = research._single_trade(self.signal_time, self.signal, 65000,
                                          contract, self.entry_time, bars.iloc[0], cfg(), 10000)
        self.assertEqual(trade["exit_reason"], "DATA_GAP_GUARD_EXIT")
        self.assertEqual(trade["exit_premium_raw"], 105.0)
        self.assertEqual(trade["data_quality_flag"], "GAP_GUARD_EXIT")

    def test_time_exit_after_configured_hold(self):
        times = [self.entry_time + pd.Timedelta(hours=i) for i in range(4)]
        bars = option_bars(times, [
            [100, 110, 95, 105, 10], [105, 110, 100, 106, 10],
            [106, 112, 101, 107, 10], [107, 111, 100, 108, 10],
        ])
        contract = {**self.meta, "symbol": "BTC-261125-65000-C", "bars": bars}
        trade, _ = research._single_trade(self.signal_time, self.signal, 65000,
                                          contract, self.entry_time, bars.iloc[0], cfg(), 10000)
        self.assertEqual(trade["exit_reason"], "TIME_EXIT")
        self.assertEqual(trade["held_hours"], 2.0)


class TestPairReplay(unittest.TestCase):
    def test_straddle_requires_synchronous_traded_call_and_put_bars(self):
        signal_time = pd.Timestamp("2026-11-01T09:00:00Z")
        entry_time = signal_time + pd.Timedelta(hours=1)
        times = [entry_time + pd.Timedelta(hours=i) for i in range(4)]
        cbars = option_bars(times, [[100, 110, 90, 100, 10], [100, 115, 95, 110, 10],
                                    [110, 120, 100, 115, 10], [115, 125, 105, 120, 10]])
        pbars = option_bars(times, [[100, 110, 90, 100, 10], [100, 115, 95, 110, 10],
                                    [110, 120, 100, 115, 10], [115, 125, 105, 120, 10]])
        call = research.parse_option_symbol("BTC-261125-65000-C")
        put = research.parse_option_symbol("BTC-261125-65000-P")
        option_data = {
            call["symbol"]: {**call, "bars": cbars},
            put["symbol"]: {**put, "bars": pbars},
        }
        underlying = pd.DataFrame({"open": [65000], "high": [65100], "low": [64900],
                                   "close": [65000], "volume": [10]}, index=[signal_time])
        signals = pd.DataFrame([{"strategy_id": "OPT-04_LONG_STRADDLE", "direction": "LONG_VOLATILITY",
                                 "reason": "compression"}], index=[signal_time])
        trades = research._run_pair_strategy("BTC", "OPT-04_LONG_STRADDLE", signals,
                                             underlying, option_data, cfg(max_hold_hours=2), strangle=False)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["option_type"], "STRADDLE")
        self.assertEqual(trades[0]["exit_reason"], "TIME_EXIT")
        self.assertEqual(trades[0]["held_hours"], 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
