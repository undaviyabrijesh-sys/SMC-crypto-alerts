import unittest

import numpy as np
import pandas as pd

from expanded_screen import (
    HYPOTHESES,
    add_expanded_features,
    build_signals_from_frames,
)


def make_bars(count: int, frequency: str, start: str, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range(start, periods=count, freq=frequency, tz="UTC")
    drift = np.linspace(0.0, 18.0, count)
    wave = 2.5 * np.sin(np.arange(count) / 13.0)
    noise = rng.normal(0.0, 0.18, count)
    close = 100.0 + drift + wave + noise
    open_price = np.r_[close[0], close[:-1]] + rng.normal(0.0, 0.08, count)
    high = np.maximum(open_price, close) + rng.uniform(0.05, 0.55, count)
    low = np.minimum(open_price, close) - rng.uniform(0.05, 0.55, count)
    volume = rng.uniform(80.0, 180.0, count)
    return pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


class ExpandedScreenTests(unittest.TestCase):
    def test_registry_contains_seven_distinct_additional_hypotheses(self):
        expected = {
            "ema_crossover",
            "adx_dmi_trend",
            "macd_momentum",
            "bollinger_squeeze_breakout",
            "utc_daily_vwap_reclaim",
            "stochastic_trend_pullback",
            "supertrend_flip",
        }
        self.assertEqual(set(HYPOTHESES), expected)

    def test_feature_calculation_is_causal(self):
        bars = make_bars(700, "15min", "2026-01-01")
        full = add_expanded_features(bars, 15)
        prefix = add_expanded_features(bars.iloc[:520], 15)
        columns = [
            "macd_hist",
            "plus_di",
            "minus_di",
            "adx14",
            "bb_width",
            "squeeze_recent",
            "daily_vwap",
            "stoch_k",
            "stoch_d",
            "supertrend_direction",
        ]
        for column in columns:
            np.testing.assert_allclose(
                full[column].iloc[:520].to_numpy(dtype=float),
                prefix[column].to_numpy(dtype=float),
                equal_nan=True,
                err_msg=f"Future bars changed prior {column} values",
            )

    def test_indicator_and_supertrend_state_reset_after_timestamp_gap(self):
        bars = make_bars(520, "15min", "2026-01-01")
        gap_start = 260
        index = bars.index.to_list()
        for i in range(gap_start, len(index)):
            index[i] = index[i] + pd.Timedelta(hours=3)
        bars.index = pd.DatetimeIndex(index)
        features = add_expanded_features(bars, 15)

        self.assertTrue(features["ema20"].iloc[gap_start:gap_start + 19].isna().all())
        self.assertTrue(
            (features["supertrend_direction"].iloc[gap_start:gap_start + 13] == 0).all()
        )
        self.assertIn(
            int(features["supertrend_direction"].iloc[gap_start + 13]),
            (-1, 1),
        )

    def test_all_new_hypotheses_return_only_discrete_directions(self):
        lower = make_bars(1_200, "15min", "2026-01-01", seed=11)
        higher = make_bars(330, "1h", "2026-01-01", seed=13)
        frame, signals, minutes = build_signals_from_frames(lower, higher, "15m")

        self.assertEqual(minutes, 15)
        self.assertEqual(set(signals), set(HYPOTHESES))
        self.assertEqual(len(frame), len(lower))
        for strategy, values in signals.items():
            self.assertEqual(values.shape, (len(lower),), strategy)
            self.assertTrue(set(np.unique(values)).issubset({-1, 0, 1}), strategy)

    def test_unsupported_timeframe_fails_closed(self):
        lower = make_bars(300, "5min", "2026-01-01")
        higher = make_bars(250, "1h", "2026-01-01")
        with self.assertRaises(ValueError):
            build_signals_from_frames(lower, higher, "5m")


if __name__ == "__main__":
    unittest.main()
