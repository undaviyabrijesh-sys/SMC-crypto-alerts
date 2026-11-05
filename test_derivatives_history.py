"""Offline parser tests for Delta historical derivatives candles."""
import unittest

from smoke_derivatives_history import SERIES, validate_payload, validate_results


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


    def _complete_results(self):
        return [
            {"symbol_alias": symbol, "series": series_name,
             "status": "available", "row_count": 1}
            for symbol in ("BTC", "ETH", "XAU")
            for series_name in SERIES
        ]

    def test_requires_every_expected_symbol_series_pair(self):
        self.assertEqual(validate_results(self._complete_results()), [])

    def test_rejects_one_empty_series_even_when_others_are_available(self):
        results = self._complete_results()
        results[0]["status"] = "empty"
        results[0]["row_count"] = 0
        errors = validate_results(results)
        self.assertTrue(any("no usable historical candles" in error for error in errors))

    def test_rejects_missing_or_duplicate_series_results(self):
        results = self._complete_results()
        results.pop()
        results.append(dict(results[0]))
        errors = validate_results(results)
        self.assertTrue(any("duplicate" in error for error in errors))
        self.assertTrue(any("missing symbol/series" in error for error in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
