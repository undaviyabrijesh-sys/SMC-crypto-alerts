"""Tests for IST end-of-day paper P&L notifications."""
import unittest
from datetime import date

from daily_reports import build_daily_report, is_enabled, maybe_send_daily_report


class DailyReportTests(unittest.TestCase):
    def test_report_counts_only_trade_exit_day_in_ist(self):
        trades = [
            {"exit_time": "2026-11-05T17:00:00Z", "gross_R": 2.0, "status": "TP",
             "sym": "BTC", "setup_type": "SWEEP"},
            {"exit_time": "2026-11-05T18:10:00Z", "gross_R": -1.0, "status": "SL",
             "sym": "ETH", "setup_type": "TREND"},
            {"exit_time": "2026-11-05T18:40:00Z", "gross_R": 1.0, "status": "TP",
             "sym": "XAU", "setup_type": "BREAKOUT"},
        ]
        message = build_daily_report(date(2026, 11, 6), trades, {})
        self.assertIn("Closed trades: **1**", message)
        self.assertIn("Realized result: **+1.00R**", message)
        self.assertIn("XAU", message)
        self.assertNotIn("BTC", message)

    def test_report_includes_setup_and_symbol_breakdown(self):
        trades = [
            {"exit_time": "2026-11-05T19:00:00Z", "gross_R": 1.5, "status": "TP",
             "sym": "BTC", "setup_type": "LIQUIDITY_SWEEP"},
            {"exit_time": "2026-11-05T20:00:00Z", "gross_R": -1.0, "status": "SL",
             "sym": "BTC", "setup_type": "TREND_PULLBACK"},
        ]
        message = build_daily_report(date(2026, 11, 6), trades, {"OPEN1": {}})
        self.assertIn("Realized result: **+0.50R**", message)
        self.assertIn("LIQUIDITY_SWEEP", message)
        self.assertIn("TREND_PULLBACK", message)
        self.assertIn("Open paper positions at report time: **1**", message)

    def test_sends_only_after_five_minutes_past_midnight_ist(self):
        state = {"trade_history": [], "positions": {}}
        sent = []
        sender = lambda msg: sent.append(msg) or True
        self.assertFalse(maybe_send_daily_report(state, "2026-11-05T18:34:00Z", sender))
        self.assertEqual(sent, [])
        self.assertTrue(maybe_send_daily_report(state, "2026-11-05T18:35:00Z", sender))
        self.assertEqual(len(sent), 1)
        self.assertIn("2026-11-05 IST", sent[0])

    def test_retries_failed_delivery_and_marks_sent_only_after_success(self):
        state = {"trade_history": [], "positions": {}}
        calls = []
        self.assertFalse(maybe_send_daily_report(state, "2026-11-05T18:35:00Z",
            lambda message: calls.append(message) or False))
        self.assertIn("2026-11-05", state["pending_daily_reports"])
        self.assertTrue(maybe_send_daily_report(state, "2026-11-05T18:40:00Z",
            lambda message: calls.append(message) or True))
        self.assertEqual(calls[0], calls[1])
        self.assertIn("2026-11-05", state["daily_reports_sent"])
        self.assertNotIn("2026-11-05", state["pending_daily_reports"])

    def test_does_not_send_twice_for_the_same_day(self):
        state = {"trade_history": [], "positions": {}, "daily_reports_sent": ["2026-11-05"]}
        calls = []
        self.assertFalse(maybe_send_daily_report(state, "2026-11-05T18:40:00Z",
            lambda message: calls.append(message) or True))
        self.assertEqual(calls, [])


    def test_daily_reports_are_opt_in_and_default_off(self):
        self.assertFalse(is_enabled())
        self.assertFalse(is_enabled(""))
        self.assertFalse(is_enabled("false"))
        self.assertFalse(is_enabled("0"))
        self.assertTrue(is_enabled("true"))
        self.assertTrue(is_enabled("1"))
        self.assertTrue(is_enabled("yes"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
