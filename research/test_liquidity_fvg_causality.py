"""Regression tests for causal liquidity/FVG entry and exit handling."""
import numpy as np
import pandas as pd

from liquidity_sweep_mss_intraday_backtest import confirmed_local_swings
from liquidity_sweep_mss_fvg_retrace_intraday_backtest import simulate


def make_frame(side="long"):
    n = 40
    index = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    if side == "long":
        op = np.full(n, 102.0)
        hi = np.full(n, 103.0)
        lo = np.full(n, 101.0)
        cl = np.full(n, 102.0)
    else:
        op = np.full(n, 100.0)
        hi = np.full(n, 101.0)
        lo = np.full(n, 99.0)
        cl = np.full(n, 100.0)
    return pd.DataFrame({
        "open": op, "high": hi, "low": lo, "close": cl,
        "segment": np.zeros(n, dtype=int),
        "h4_close": np.full(n, np.nan),
        "h4_ema50_close": np.full(n, np.nan),
        "h4_ema200_close": np.full(n, np.nan),
        "regime": np.full(n, "mixed_or_unavailable", dtype=object),
    }, index=index)


def make_event(side="long"):
    if side == "long":
        return {
            "sweep_i": 0, "mss_i": 0, "side": "long",
            "external_level": 90.0, "extreme": 95.0, "atr_sweep": 1.0,
            "pivot_time": pd.Timestamp("2026-01-01", tz="UTC"),
            "fvg_bottom": 99.0, "fvg_top": 101.0, "fvg_width": 2.0,
        }
    return {
        "sweep_i": 0, "mss_i": 0, "side": "short",
        "external_level": 110.0, "extreme": 105.0, "atr_sweep": 1.0,
        "pivot_time": pd.Timestamp("2026-01-01", tz="UTC"),
        "fvg_bottom": 100.0, "fvg_top": 102.0, "fvg_width": 2.0,
    }


def make_config(side="long"):
    return {
        "config_id": "synthetic_regression",
        "external_strength": 3, "local_strength": 3, "mss_wait": 8,
        "displacement_mode": "body_0.5_atr_close_quartile",
        "entry_depth": 0.50, "stop_buffer": 0.0, "target_r": 1.5,
        "htf_filter": "none", "sample": "test",
    }


def run_one(d, side="long"):
    rows = simulate(d, [make_event(side)], make_config(side), 0, len(d))
    assert len(rows) == 1, f"expected one synthetic trade, got {len(rows)}"
    return rows[0]


def test_local_pivot_is_only_consumed_after_confirmation_bar_closes():
    index = pd.date_range("2026-01-01", periods=10, freq="15min", tz="UTC")
    d = pd.DataFrame({
        "high": [10, 9, 8, 7, 8, 9, 10, 11, 12, 13],
        "low":  [8, 7, 6, 1, 5, 6, 4, 5, 6, 7],
        "segment": np.zeros(10, dtype=int),
    }, index=index)
    _, last_lo = confirmed_local_swings(d, strength=2)
    # Pivot at index 3 is confirmed by the rightmost bar at index 5.
    # build_events reads last_lo[k-1], so it can first use this level for
    # a sweep at k=6, after confirmation bar 5 has closed.
    assert np.isnan(last_lo[4])
    assert last_lo[5] == 1.0
    assert last_lo[6] == 1.0


def test_long_target_gap_is_filled_at_fixed_target_not_better_open():
    d = make_frame("long")
    d.loc[d.index[1], ["low", "high", "close"]] = [100.0, 103.0, 102.0]
    d.loc[d.index[2], ["open", "high", "low", "close"]] = [108.0, 109.0, 107.0, 108.0]
    row = run_one(d, "long")
    assert row["outcome"] == "TP"
    assert row["entry"] == 100.0
    assert row["target"] == 107.5
    assert row["exit"] == 107.5
    assert row["gross_R"] == 1.5


def test_short_target_gap_is_filled_at_fixed_target_not_better_open():
    d = make_frame("short")
    d.loc[d.index[1], ["high", "low", "close"]] = [101.0, 99.0, 100.0]
    d.loc[d.index[2], ["open", "high", "low", "close"]] = [94.0, 95.0, 93.0, 94.0]
    row = run_one(d, "short")
    assert row["outcome"] == "TP"
    assert row["entry"] == 101.0
    assert row["target"] == 95.0
    assert row["exit"] == 95.0
    assert row["gross_R"] == 1.5


def test_stop_gap_keeps_adverse_open_fill():
    d = make_frame("long")
    d.loc[d.index[1], ["low", "high", "close"]] = [100.0, 103.0, 102.0]
    d.loc[d.index[2], ["open", "high", "low", "close"]] = [94.0, 95.0, 93.0, 94.0]
    row = run_one(d, "long")
    assert row["outcome"] == "SL"
    assert row["exit"] == 94.0
    assert row["gross_R"] == -1.2


def test_intrabar_fill_bar_does_not_receive_same_bar_target_credit():
    d = make_frame("long")
    d.loc[d.index[1], ["low", "high", "close"]] = [100.0, 108.0, 107.0]
    row = run_one(d, "long")
    assert row["outcome"] == "TIME"
    assert row["exit_time"] == d.index[32]


if __name__ == "__main__":
    tests = [
        test_local_pivot_is_only_consumed_after_confirmation_bar_closes,
        test_long_target_gap_is_filled_at_fixed_target_not_better_open,
        test_short_target_gap_is_filled_at_fixed_target_not_better_open,
        test_stop_gap_keeps_adverse_open_fill,
        test_intrabar_fill_bar_does_not_receive_same_bar_target_credit,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS {len(tests)} regression tests")
