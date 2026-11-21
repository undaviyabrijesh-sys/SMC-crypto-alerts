"""Offline contract tests for the read-only Quant Terminal API."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from quant_terminal.api import main


class ReadOnlyApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "market_data"
        self.data_dir.mkdir()
        self.state_path = self.root / "state.json"
        self.signals_path = self.root / "quant_signals.jsonl"
        self.ledger_path = self.root / "RESEARCH_LEDGER.md"
        self.discovery_dir = self.root / "quant_discovery"
        self.discovery_dir.mkdir()
        self.patches = [
            patch.object(main, "DATA_DIR", self.data_dir),
            patch.object(main, "STATE_PATH", self.state_path),
            patch.object(main, "SIGNALS_PATH", self.signals_path),
            patch.object(main, "LEDGER_PATH", self.ledger_path),
            patch.object(main, "DISCOVERY_DIR", self.discovery_dir),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def write_candles(self, symbol="BTC", timeframe="5m", last_open="2026-11-19T12:25:00Z", count=15):
        minutes = main.TIMEFRAME_MINUTES[timeframe]
        index = pd.date_range(end=pd.Timestamp(last_open), periods=count, freq=f"{minutes}min", tz="UTC")
        frame = pd.DataFrame({"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 5.0}, index=index)
        frame.index.name = "timestamp"
        frame.to_csv(self.data_dir / f"{symbol}_{timeframe}.csv")

    def test_market_snapshot_uses_only_persisted_closed_candles(self):
        self.write_candles()
        result = main.build_market_snapshot(now="2026-11-19T12:35:00Z", symbols=["BTC"])
        market = result["markets"][0]
        self.assertEqual(result["source"], "local persisted Delta public OHLCV cache")
        self.assertEqual(market["status"], "live")
        self.assertEqual(market["last_price"], 101.0)
        self.assertEqual(market["last_closed_5m_candle_open"], "2026-11-19T12:25:00+00:00")

    def test_incomplete_latest_candle_is_excluded(self):
        self.write_candles(last_open="2026-11-19T12:30:00Z")
        result = main.build_market_snapshot(now="2026-11-19T12:34:00Z", symbols=["BTC"])
        market = result["markets"][0]
        self.assertEqual(market["last_closed_5m_candle_open"], "2026-11-19T12:25:00+00:00")
        self.assertEqual(market["last_price"], 101.0)

    def test_stale_market_is_not_reported_live(self):
        self.write_candles(last_open="2026-11-19T11:00:00Z")
        result = main.build_market_snapshot(now="2026-11-19T12:35:00Z", symbols=["BTC"])
        self.assertEqual(result["markets"][0]["status"], "stale")

    def test_missing_market_cache_is_unavailable_not_zero(self):
        result = main.build_market_snapshot(now="2026-11-19T12:35:00Z", symbols=["BTC"])
        market = result["markets"][0]
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(market["last_price"])
        self.assertEqual(market["status"], "unavailable")

    def test_unknown_symbol_fails_closed(self):
        with self.assertRaises(ValueError):
            main.build_market_snapshot(symbols=["DOGE"])

    def test_missing_paper_state_is_unavailable_not_empty_account(self):
        result = main.get_paper_positions()
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["positions"])
        self.assertIsNone(result["position_count"])

    def test_paper_reads_do_not_mutate_state_file(self):
        payload = {"positions": {"A1": {"signal_id": "A1", "sym": "BTC", "dir": "long", "entry": 100, "sl": 95, "tp": 110}}, "trade_history": []}
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")
        before = self.state_path.read_bytes()
        result = main.get_paper_positions()
        after = self.state_path.read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(result["position_count"], 1)
        self.assertEqual(result["positions"][0]["signal_id"], "A1")

    def test_scanner_reads_latest_symbol_record_and_marks_stale(self):
        self.signals_path.write_text(
            json.dumps({"timestamp": "2026-11-19T12:00:00Z", "symbol": "BTC", "decision_status": "RESEARCH_ONLY", "candidates": []}) + "\n",
            encoding="utf-8",
        )
        result = main.build_scanner_snapshot(now="2026-11-19T12:35:00Z")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["symbols"][0]["symbol"], "BTC")

    def test_research_ledger_headings_are_exposed_without_mutation(self):
        self.ledger_path.write_text("## 2026-11-19 — Audit\n\nA verified audit.\n\n## Next step\n\nA frozen next step.\n", encoding="utf-8")
        result = main.build_research_snapshot()
        self.assertEqual(result["entry_count"], 2)
        self.assertEqual(result["entries"][0]["title"], "Next step")

    def test_backtest_artifact_metadata_and_metrics_are_read(self):
        metadata = self.discovery_dir / "ETH_TEST_METADATA.json"
        metadata.write_text(json.dumps({
            "status": "completed_inconclusive",
            "research_type": "descriptive_event_study",
            "data_classification": "event_study_only",
            "validation_state": "inconclusive",
            "symbol": "ETHUSDT",
            "strategy": "EMA20 pullback event study",
            "run_id": "test-run",
            "oos_evaluated": False,
            "decision": "no_promotion",
            "parent_workflow_run_id": 44693535437,
            "funding_records": 1483,
            "funding_sha256": "23d7d5796e5d5691ff5ee93e8280f18d15c5235bbb7b50533be545c41abb53d6",
            "funding_accounting_status": "actual_event_time_with_boundary_bounds",
            "primary_cost_bps_round_trip": 12,
        }), encoding="utf-8")
        metrics = self.discovery_dir / "ETH_TEST_METRICS.csv"
        metrics.write_text("horizon,events,mean_net_bps" + chr(10) + "4h,16,30.18" + chr(10), encoding="utf-8")

        result = main.build_backtest_snapshot()
        self.assertEqual(result["status"], "available")
        artifacts = {item["name"]: item for item in result["artifacts"]}
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["status"], "completed_inconclusive")
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["research_type"], "descriptive_event_study")
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["data_classification"], "event_study_only")
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["validation_state"], "inconclusive")
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["symbol"], "ETHUSDT")
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["oos_evaluated"], False)
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["decision"], "no_promotion")
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["funding_records"], 1483)
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["funding_accounting_status"], "actual_event_time_with_boundary_bounds")
        self.assertEqual(artifacts["ETH_TEST_METADATA.json"]["metadata"]["primary_cost_bps_round_trip"], 12)
        self.assertEqual(artifacts["ETH_TEST_METRICS.csv"]["columns"], ["horizon", "events", "mean_net_bps"])
        self.assertEqual(artifacts["ETH_TEST_METRICS.csv"]["rows"][0]["mean_net_bps"], "30.18")

    def test_backtest_all_csv_artifacts_are_indexed_with_bounded_preview(self):
        metrics = self.discovery_dir / "ETH_TEST_MONTHLY.csv"
        metrics.write_text("month,net_R" + chr(10) + "2026-01,1.5" + chr(10), encoding="utf-8")
        trades = self.discovery_dir / "ETH_TEST_TRADES.csv"
        rows = ["entry_time,side,net_R"]
        rows.extend(f"2026-01-{day:02d}T00:00:00Z,long,{day / 100:.2f}" for day in range(1, 31))
        trades.write_text(chr(10).join(rows) + chr(10), encoding="utf-8")

        result = main.build_backtest_snapshot()
        artifacts = {item["name"]: item for item in result["artifacts"]}
        self.assertIn("ETH_TEST_MONTHLY.csv", artifacts)
        self.assertIn("ETH_TEST_TRADES.csv", artifacts)
        self.assertEqual(artifacts["ETH_TEST_MONTHLY.csv"]["rows"][0]["net_R"], "1.5")
        preview = artifacts["ETH_TEST_TRADES.csv"]["rows"]
        self.assertEqual(len(preview), 25)
        self.assertEqual(preview[0]["entry_time"], "2026-01-06T00:00:00Z")
        self.assertEqual(preview[-1]["entry_time"], "2026-01-30T00:00:00Z")

    def test_api_has_no_mutating_data_routes(self):
        data_routes = [route for route in main.app.routes if getattr(route, "path", "").startswith("/api/v1/")]
        self.assertTrue(data_routes)
        for route in data_routes:
            self.assertEqual(route.methods, {"GET"}, route.path)

    def test_http_health_and_market_routes_are_read_only(self):
        self.write_candles()
        with patch.dict("os.environ", {"QUANT_API_TOKEN": ""}, clear=False), patch.object(
            main, "_now_utc", return_value=pd.Timestamp("2026-11-19T12:35:00Z")
        ):
            client = TestClient(main.app)
            health = client.get("/api/v1/health")
            markets = client.get("/api/v1/markets?symbols=BTC")
            mutation = client.post("/api/v1/markets")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "available")
        self.assertEqual(markets.status_code, 200)
        self.assertEqual(markets.json()["markets"][0]["last_price"], 101.0)
        self.assertEqual(mutation.status_code, 405)

    def test_configured_api_token_is_required(self):
        with patch.dict("os.environ", {"QUANT_API_TOKEN": "test-secret"}, clear=False):
            client = TestClient(main.app)
            denied = client.get("/api/v1/health")
            allowed = client.get("/api/v1/health", headers={"Authorization": "Bearer test-secret"})
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)


if __name__ == "__main__":
    unittest.main()
