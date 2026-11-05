import unittest
import numpy as np
import pandas as pd

from initial_screen import add_closed_htf_context, simulate, summarize


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


if __name__=="__main__":
    unittest.main()
