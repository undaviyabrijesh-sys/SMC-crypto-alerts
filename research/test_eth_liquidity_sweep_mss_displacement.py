"""Causality and stale-context tests for ETH/BTC 4h confirmation."""
import unittest

import numpy as np
import pandas as pd

import liquidity_sweep_mss_intraday_backtest as base
from eth_liquidity_sweep_mss_displacement_intraday_backtest import attach_btc_context


def make_frame(index, start_price):
    n = len(index)
    close = start_price + np.arange(n, dtype=float) * 0.01
    return pd.DataFrame(
        {
            "open": close - 0.002,
            "high": close + 0.01,
            "low": close - 0.01,
            "close": close,
            "volume": np.ones(n, dtype=float),
        },
        index=index,
    )


class TestCompletedBtcContext(unittest.TestCase):
    def test_only_closed_four_hour_bar_is_visible(self):
        index = pd.date_range(
            "2024-01-01T00:00:00Z", periods=48, freq="15min"
        )
        eth_d, _ = base.prepare(make_frame(index, 100.0))
        btc_d, _ = base.prepare(make_frame(index, 200.0))
        enriched, _ = attach_btc_context(eth_d, btc_d)

        self.assertTrue(pd.isna(enriched.loc[index[15], "btc_h4_time"]))
        self.assertEqual(enriched.loc[index[16], "btc_h4_time"], index[16])
        self.assertEqual(enriched.loc[index[17], "btc_h4_time"], index[16])
        self.assertEqual(
            enriched.loc[index[16], "btc_h4_close"],
            btc_d.loc[index[15], "close"],
        )

    def test_pre_gap_btc_context_is_invalidated_until_new_complete_bar(self):
        eth_index = pd.date_range(
            "2024-01-01T00:00:00Z", periods=49, freq="15min"
        )
        btc_index = eth_index.delete(np.arange(16, 32))
        eth_d, _ = base.prepare(make_frame(eth_index, 100.0))
        btc_d, _ = base.prepare(make_frame(btc_index, 200.0))
        enriched, _ = attach_btc_context(eth_d, btc_d)

        self.assertTrue(pd.isna(enriched.loc[eth_index[32], "btc_h4_time"]))
        self.assertTrue(pd.isna(enriched.loc[eth_index[32], "btc_h4_close"]))
        self.assertEqual(enriched.loc[eth_index[48], "btc_h4_time"], eth_index[48])
        self.assertTrue(np.isfinite(enriched.loc[eth_index[48], "btc_h4_close"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
