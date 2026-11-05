"""Offline parser tests for Delta historical derivatives candles."""
import unittest

from smoke_derivatives_history import validate_payload


class DerivativesHistoryTests(unittest.TestCase):
    def test_funding_candles_allow_negative_rates(self):
        payload = {"success": True, "result": [
            {"time": 1000, "open": -0.0002, "high": -0.0001,
             "low": -0.0003, "close": -0.00015},
            {"time": 4600, "open": 0.0001, "high": 0.0002,
             "low": 0.00005, "close": 0.00015, "volume": 0},
        ]}
        frame = validate_payload(payload, "funding:BTC", allow_negative=True)
        self.assertEqual(len(frame), 2)
        self.assertLess(frame.iloc[0]["open"], 0)

    def test_mark_prices_must_be_positive(self):
        payload = {"success": True, "result": [
            {"time": 1000, "open": 0, "high": 2, "low": 0, "close": 1}
        ]}
        with self.assertRaises(ValueError):
            validate_payload(payload, "mark:BTC", allow_negative=False)

    def test_rejects_duplicate_timestamps(self):
        candle = {"time": 1000, "open": 1, "high": 2, "low": 0.5, "close": 1.5}
        with self.assertRaises(ValueError):
            validate_payload({"success": True, "result": [candle, candle]},
                             "open_interest:BTC", allow_negative=False)

    def test_empty_series_is_reported_as_empty_frame(self):
        frame = validate_payload({"success": True, "result": []},
                                 "funding:BTC", allow_negative=True)
        self.assertTrue(frame.empty)


if __name__ == "__main__":
    unittest.main(verbosity=2)
