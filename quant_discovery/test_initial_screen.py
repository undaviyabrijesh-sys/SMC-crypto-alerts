import unittest
import numpy as np
import pandas as pd

from initial_screen import add_closed_htf_context, indicators, simulate, summarize


class InitialScreenTests(unittest.TestCase):
    def test_higher_timeframe_context_is_only_visible_after_close(self):
        lower_index=pd.date_range("2026-01-01 00:00",periods=5,freq="15min",tz="UTC")
        lower=pd.DataFrame({"open":1.0,"high":1.0,"low":1.0,"close":1.0,
                            "ema50":1.0,"ema200":0.5},index=lower_index)
        higher_index=pd.to_datetime(["2025-12-31 23:00Z","2026-01-01 00:00Z"])
        higher=pd.DataFrame({"ema50":[10.0,20.0],"ema200":[5.0,5.0]},index=higher_index)
        result=add_closed_htf_context(lower,higher,60)
        self.assertEqual(result.iloc[0]["ema50_y"],10.0)
        self.assertEqual(result.iloc[3]["ema50_y"],20.0)

    def _frame(self,count=260):
        index=pd.date_range("2026-01-01",periods=count,freq="1h",tz="UTC")
        return pd.DataFrame({"open":np.full(count,100.0),"high":np.full(count,101.0),
          "low":np.full(count,99.0),"close":np.full(count,100.0),
          "atr14":np.ones(count),"atr_ratio":np.ones(count),
          "ema50_y":np.full(count,2.0),"ema200_y":np.ones(count)},index=index)

    def test_next_bar_fill_and_same_bar_ambiguity_are_sl_first(self):
        frame=self._frame()
        frame.iloc[206,frame.columns.get_loc("high")]=104.0
        frame.iloc[206,frame.columns.get_loc("low")]=98.0
        signal=np.zeros(len(frame),dtype=int); signal[205]=1
        trades=simulate(frame,signal,"donchian_breakout",60,0,len(frame))
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0]["entry_time"],frame.index[206])
        self.assertEqual(trades[0]["entry"],100.0)
        self.assertEqual(trades[0]["outcome"],"SL")
        self.assertEqual(trades[0]["exit"],98.5)

    def test_split_boundary_does_not_create_artificial_time_exit(self):
        frame=self._frame(220)
        signal=np.zeros(len(frame),dtype=int); signal[205]=1
        self.assertEqual(simulate(frame,signal,"donchian_breakout",60,0,len(frame)),[])

    def test_higher_cost_assumption_reduces_net_expectancy(self):
        trades=[{"gross_R":1.0,"entry":100.0,"risk":10.0,"hold_hours":0.0,"outcome":"TP"},
                {"gross_R":-1.0,"entry":100.0,"risk":10.0,"hold_hours":0.0,"outcome":"SL"}]
        low=summarize(trades,1.0,5.0)["expectancy_net_R"]
        high=summarize(trades,1.0,20.0)["expectancy_net_R"]
        self.assertLess(high,low)


    def test_final_closed_bar_is_included_in_end_of_data_exit(self):
        frame=self._frame()
        frame.iloc[-1,frame.columns.get_loc("high")]=104.0
        signal=np.zeros(len(frame),dtype=int); signal[-25]=1
        trades=simulate(frame,signal,"donchian_breakout",60,0,len(frame))
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0]["entry_time"],frame.index[-24])
        self.assertEqual(trades[0]["exit_time"],frame.index[-1])
        self.assertEqual(trades[0]["outcome"],"TP")
        self.assertEqual(trades[0]["exit"],103.0)


    def test_indicators_restart_rolling_and_ema_state_after_a_timestamp_gap(self):
        first = pd.date_range("2026-01-01T00:00:00Z", periods=205, freq="1h")
        second = pd.date_range("2026-01-20T00:00:00Z", periods=205, freq="1h")
        index = first.append(second)
        close = np.r_[np.full(205, 100.0), np.full(205, 200.0)]
        frame = pd.DataFrame({
            "open": close, "high": close + 1.0, "low": close - 1.0,
            "close": close, "volume": np.full(len(index), 100.0),
        }, index=index)
        result = indicators(frame, 60)
        start = 205
        self.assertTrue(np.isnan(result.iloc[start]["ema20"]))
        self.assertTrue(np.isnan(result.iloc[start + 18]["ema20"]))
        self.assertAlmostEqual(result.iloc[start + 19]["ema20"], 200.0)
        self.assertTrue(np.isnan(result.iloc[start + 12]["atr14"]))
        self.assertAlmostEqual(result.iloc[start + 13]["atr14"], 2.0)
        self.assertTrue(np.isnan(result.iloc[start + 198]["ema200"]))
        self.assertAlmostEqual(result.iloc[start + 199]["ema200"], 200.0)
        self.assertTrue(np.isnan(result.iloc[start + 19]["prior_high20"]))
        self.assertAlmostEqual(result.iloc[start + 20]["prior_high20"], 201.0)

    def test_closed_higher_timeframe_context_expires_after_a_gap(self):
        lower_index = pd.to_datetime([
            "2026-01-01T00:00:00Z",
            "2026-01-01T01:15:00Z",
            "2026-01-01T01:30:00Z",
        ])
        lower = pd.DataFrame({
            "open": [1.0] * 3, "high": [1.0] * 3, "low": [1.0] * 3,
            "close": [1.0] * 3, "ema50": [1.0] * 3, "ema200": [0.5] * 3,
        }, index=lower_index)
        higher_index = pd.to_datetime([
            "2025-12-31T23:00:00Z",
            "2026-01-01T02:00:00Z",
        ])
        higher = pd.DataFrame({
            "ema50": [10.0, 20.0], "ema200": [5.0, 5.0],
        }, index=higher_index)
        result = add_closed_htf_context(lower, higher, 60, 15)
        self.assertEqual(result.iloc[0]["ema50_y"], 10.0)
        self.assertEqual(result.iloc[1]["ema50_y"], 10.0)
        self.assertTrue(np.isnan(result.iloc[2]["ema50_y"]))
        self.assertGreater(result.iloc[2]["htf_age_minutes"], 90.0)


if __name__=="__main__":
    unittest.main()
