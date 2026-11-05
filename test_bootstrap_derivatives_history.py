"""Offline tests for the resumable derivatives-history archive builder."""
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import requests

import bootstrap_derivatives_history as archive


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, records):
        self.records = records

    def raise_for_status(self):
        return None

    def json(self):
        return {"success": True, "result": self.records}


class TestDerivativesArchive(unittest.TestCase):
    def test_chunk_windows_are_adjacent_and_bounded(self):
        chunks = list(archive.build_chunks(0, 9000, 300, max_candles=10))
        self.assertEqual(chunks[0], (0, 2999))
        self.assertEqual(chunks[1][0], chunks[0][1] + 1)
        self.assertEqual(chunks[-1][1], 8999)
        for left, right in chunks:
            self.assertLessEqual((right - left) // 300 + 1, 10)

    def test_parser_preserves_negative_funding_rates(self):
        payload = {"success": True, "result": [
            {"time": 3600, "open": -0.0002, "high": -0.0001,
             "low": -0.0003, "close": -0.00015}
        ]}
        frame = archive.parse_payload(payload, "FUNDING:BTCUSD", "funding", 0, 7200)
        self.assertEqual(len(frame), 1)
        self.assertLess(frame.iloc[0]["open"], 0)

    def test_parser_rejects_negative_mark_prices(self):
        payload = {"success": True, "result": [
            {"time": 300, "open": -1, "high": 2, "low": -2, "close": 1}
        ]}
        with self.assertRaises(archive.DerivativesArchiveError):
            archive.parse_payload(payload, "MARK:BTCUSD", "mark", 0, 900)

    def test_parser_rejects_nonfinite_and_invalid_ohlc(self):
        payload = {"success": True, "result": [
            {"time": 3600, "open": 1, "high": 0.5, "low": 0.9, "close": 1}
        ]}
        with self.assertRaises(archive.DerivativesArchiveError):
            archive.parse_payload(payload, "FUNDING:BTCUSD", "funding", 0, 7200)

    def test_download_is_resumable_and_excludes_partial_last_candle(self):
        class InterruptedSession:
            def get(self, *args, **kwargs):
                raise requests.ConnectionError("test interruption")

        class WorkingSession:
            def __init__(self):
                self.calls = 0
            def get(self, url, params, headers, timeout):
                self.calls += 1
                records = [
                    {"time": stamp, "open": 100, "high": 102,
                     "low": 99, "close": 101, "volume": 5}
                    for stamp in (0, 300, 600, 900)
                    if int(params["start"]) <= stamp <= int(params["end"])
                ]
                return FakeResponse(records)

        with tempfile.TemporaryDirectory(prefix="salty-derivatives-") as folder:
            root = Path(folder)
            try:
                archive.download_dataset(
                    "BTC", "mark", 0, 1000, root,
                    session=InterruptedSession(), request_delay=0,
                    retries=0, sleep=lambda _: None,
                )
            except requests.ConnectionError:
                pass
            else:
                self.fail("expected interrupted first attempt")
            client = WorkingSession()
            result = archive.download_dataset(
                "BTC", "mark", 0, 1000, root,
                session=client, request_delay=0, retries=0,
                sleep=lambda _: None,
            )
            self.assertEqual(client.calls, 1)
            self.assertEqual(result["row_count"], 3)
            frame = pd.read_csv(root / "BTC_mark_5m.csv", parse_dates=["timestamp"])
            self.assertEqual(len(frame), 3)
            self.assertEqual(frame["timestamp"].max(), pd.Timestamp("1970-01-01T00:10:00Z"))
            self.assertTrue((root / "manifest.json").exists())
            self.assertTrue((root / "coverage.csv").exists())
            self.assertEqual(archive.sha256(root / "BTC_mark_5m.csv"), result["sha256"])
            self.assertFalse((root / ".work" / "BTC_mark_5m").exists())

    def test_empty_series_is_written_and_reported_without_fabricating_rows(self):
        class EmptySession:
            def get(self, *args, **kwargs):
                return FakeResponse([])
        with tempfile.TemporaryDirectory(prefix="salty-derivatives-empty-") as folder:
            root = Path(folder)
            result = archive.download_dataset(
                "XAU", "funding", 0, 3600, root,
                session=EmptySession(), request_delay=0, retries=0,
                sleep=lambda _: None,
            )
            self.assertEqual(result["row_count"], 0)
            self.assertEqual(result["gap_count"], 0)
            frame = pd.read_csv(root / "XAU_funding_1h.csv")
            self.assertEqual(len(frame), 0)


    def test_resume_checkpoint_must_align_to_candle_boundary(self):
        with tempfile.TemporaryDirectory(prefix="salty-derivatives-progress-") as folder:
            path = Path(folder) / "progress.json"
            expected = {
                "symbol_alias": "BTC", "contract_symbol": "BTCUSD",
                "api_symbol": "MARK:BTCUSD", "series": "mark",
                "timeframe": "5m", "start_epoch": 0,
                "end_epoch": 10000, "max_candles": 2000,
            }
            progress = {
                **expected, "next_start": 301,
                "request_count": 1, "empty_chunk_count": 0,
            }
            path.write_text(__import__("json").dumps(progress), encoding="utf-8")
            self.assertIsNone(archive.read_progress(path, expected))
            progress["next_start"] = 300
            path.write_text(__import__("json").dumps(progress), encoding="utf-8")
            self.assertEqual(archive.read_progress(path, expected), progress)


if __name__ == "__main__":
    unittest.main(verbosity=2)
