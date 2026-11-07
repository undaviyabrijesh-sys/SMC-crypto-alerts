import tempfile
import unittest
from pathlib import Path
import pandas as pd
from strategy_discovery import net_r, run_experiment, simulate_policy, summarize, validate_trades


def trade(asset, strategy, entry_time, exit_time, gross, timeframe="15m",
          regime="UP", vol="LOW", outcome="TP", entry=100.0, risk=1.0):
    return {"asset": asset, "timeframe": timeframe, "strategy": strategy,
        "entry_time": entry_time, "exit_time": exit_time, "entry": entry,
        "risk": risk, "gross_R": gross, "hold_hours": 0.25,
        "outcome": outcome, "regime": regime, "vol_regime": vol}


class StrategyDiscoveryTests(unittest.TestCase):
    def test_outcomes_available_after_exit_candle_close(self):
        for tf, exit_at, expected in (
            ("15m", "00:15", "00:30"), ("1h", "01:00", "02:00")):
            row = trade("BTC", "a", "2026-01-01T00:00Z", f"2026-01-01T{exit_at}Z",
                        1, timeframe=tf)
            result = validate_trades(pd.DataFrame([row]))
            self.assertEqual(result.iloc[0].outcome_available_at,
                             pd.Timestamp(f"2026-01-01T{expected}Z"))

    def test_same_candle_exit_is_valid_and_available_at_candle_close(self):
        row = trade("BTC", "a", "2026-01-01T00:00Z", "2026-01-01T00:00Z",
                    -1, hold_hours=0, outcome="SL")
        result = validate_trades(pd.DataFrame([row]))
        self.assertEqual(result.iloc[0].outcome_available_at,
                         pd.Timestamp("2026-01-01T00:15Z"))
        self.assertEqual(result.iloc[0].hold_hours, 0)

    def test_exit_before_entry_is_rejected(self):
        row = trade("BTC", "a", "2026-01-01T00:15Z", "2026-01-01T00:00Z", -1)
        with self.assertRaisesRegex(ValueError, "must not precede"):
            validate_trades(pd.DataFrame([row]))

    def test_duplicate_or_nonpositive_risk_fails_closed(self):
        row = trade("BTC", "a", "2026-01-01T00:00Z", "2026-01-01T00:15Z", 1)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_trades(pd.DataFrame([row, row]))
        row["risk"] = 0
        with self.assertRaisesRegex(ValueError, "positive"):
            validate_trades(pd.DataFrame([row]))

    def test_costs_are_converted_to_r_units(self):
        row = pd.Series(trade("BTC", "a", "2026-01-01T00:00Z",
                              "2026-01-01T00:15Z", 1, entry=100, risk=1))
        self.assertAlmostEqual(net_r(row, 10, 0), 0.9)

    def test_selector_cannot_use_future_unclosed_outcomes(self):
        seeds = [trade("BTC", "a", f"2025-12-31T23:{m:02d}Z",
                       f"2025-12-31T23:{m+15:02d}Z", 1)
                 for m in (0, 15, 30)]
        candidates = [
            trade("BTC", "a", "2025-12-31T23:45Z", "2026-01-01T00:00Z", 1),
            trade("BTC", "b", "2025-12-31T23:45Z", "2026-01-01T00:00Z", 1),
            trade("BTC", "a", "2026-01-01T00:00Z", "2026-01-01T00:15Z", 1)]
        selected, _ = simulate_policy(pd.DataFrame(seeds + candidates), "follow_the_winner", 0)
        self.assertEqual(selected.entry_time.tolist(), [pd.Timestamp("2026-01-01T00:00Z")])

    def test_selector_blocks_overlapping_asset_positions(self):
        seeds = [trade("BTC", "a", f"2025-12-31T22:{m:02d}Z",
                       f"2025-12-31T22:{m+15:02d}Z", 1)
                 for m in (0, 15, 30)]
        candidates = [
            trade("BTC", "a", "2025-12-31T23:00Z", "2025-12-31T23:45Z", 1),
            trade("BTC", "a", "2025-12-31T23:15Z", "2026-01-01T00:00Z", 1),
            trade("BTC", "a", "2026-01-01T00:00Z", "2026-01-01T00:15Z", 1)]
        selected, decisions = simulate_policy(pd.DataFrame(seeds + candidates), "follow_the_winner", 0)
        self.assertEqual(len(selected), 2)
        self.assertEqual((decisions.decision == "BLOCKED_OPEN_POSITION").sum(), 1)

    def test_loss_streak_counts_simultaneous_exit_as_one_event(self):
        rows = [
            trade("BTC", "a", "2026-01-01T00:00Z", "2026-01-01T00:15Z", -1, outcome="SL"),
            trade("ETH", "b", "2026-01-01T00:00Z", "2026-01-01T00:15Z", 0.5),
            trade("BTC", "a", "2026-01-01T01:00Z", "2026-01-01T01:15Z", -1, outcome="SL")]
        x = validate_trades(pd.DataFrame(rows))
        x["net_R"] = x.gross_R
        self.assertEqual(summarize(x, 1)["max_consecutive_losses"], 2)

    def test_synthetic_end_to_end_outputs(self):
        start = pd.Timestamp("2024-01-01T00:00Z")
        rows = []
        for asset in ("BTC", "ETH"):
            for tf, minutes in (("15m", 15), ("1h", 60)):
                for j, strategy in enumerate(("ema", "macd", "squeeze", "supertrend")):
                    for k in range(36):
                        entry = start + pd.Timedelta(hours=6*k, minutes=j*minutes)
                        exit_ = entry + pd.Timedelta(minutes=3*minutes)
                        gross = (1, .7, .4, -.1)[j] if k % 5 else (-.5, .8, .2, .1)[j]
                        rows.append(trade(asset, strategy, entry.isoformat(), exit_.isoformat(),
                            gross, timeframe=tf, regime="UP" if k % 2 == 0 else "DOWN",
                            vol="HIGH" if k % 3 == 0 else "LOW", entry=100+j,
                            outcome="TP" if gross > .5 else ("SL" if gross < 0 else "TIME")))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inp = root / "exp002_oos_trades.csv"
            pd.DataFrame(rows).to_csv(inp, index=False)
            output = run_experiment(inp, root / "result")
            self.assertEqual(len(output["summary"]), 4*3*3)
            self.assertEqual(len(output["walk_forward"]), 4*3*3*5)
            self.assertTrue((root / "result" / "exp003_manifest.json").is_file())

    def test_unknown_policy_fails_closed(self):
        with self.assertRaises(ValueError):
            simulate_policy(pd.DataFrame(), "always_long", 10)


if __name__ == "__main__":
    unittest.main()
