# Binance USD-M BTCUSDT September 2026 aggTrades pilot — preregistration

**Frozen:** 2026-11-18 UTC  
**Branch:** `ai-quant-rebuild`  
**Purpose:** data-ingestion and provenance validation only; no strategy backtest is authorized by this pilot.

## Research question

Can the official Binance Vision monthly USD-M BTCUSDT aggregate-trade archive be downloaded, checksum-verified, parsed and reconciled to the same month's official 5-minute USD-M klines well enough to support genuine trade-level volume-at-price and aggressor-side research?

## Frozen source files

- AggTrades ZIP: `https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-09.zip`
- AggTrades checksum: same URL plus `.CHECKSUM`
- 5m klines ZIP: `https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2026-09.zip`
- 5m klines checksum: same URL plus `.CHECKSUM`
- Expected UTC interval: `2026-09-01T00:00:00Z` inclusive to `2026-10-01T00:00:00Z` exclusive.
- Official schema references: Binance Public Data README and python downloader documentation. Preserve exact source URLs, retrieval time, checksum text, ZIP SHA-256 and member names.

## Required validation

1. Download both ZIP files and companion CHECKSUM files with bounded retries; retain originals.
2. Verify SHA-256 of each ZIP against the official CHECKSUM before parsing. A checksum mismatch is a hard failure.
3. Run ZIP CRC validation and require exactly one CSV member per archive.
4. Parse aggTrades as seven fields: aggregate ID, price, quantity, first underlying trade ID, last underlying trade ID, timestamp in milliseconds, buyer-maker boolean.
5. Require finite positive prices and quantities; integer IDs/timestamps; first trade ID <= last trade ID; buyer-maker values limited to true/false.
6. Require aggregate IDs strictly increasing in source order and timestamps non-decreasing in aggregate-ID order. Do not silently sort away an ordering defect. Record aggregate-ID gaps but do not require ID contiguity unless Binance documents that as a guarantee.
7. Require every aggTrade timestamp to fall inside September 2026. Report first/last IDs, first/last timestamps, row count, duplicate IDs, ordering violations, timestamp regressions, and quantity totals.
8. Infer taker side from Binance's buyer-maker flag: buyer-maker=true means seller was taker (negative signed quantity); false means buyer was taker (positive signed quantity). Report buy, sell and signed delta totals.
9. Aggregate aggTrade quantity and taker-buy quantity into UTC 5-minute buckets. Reconcile them with the official kline base volume and taker-buy base volume by exact 5-minute open time. Report missing/extra buckets, total-volume relative error, taker-buy relative error, median/p95/max absolute per-bar relative errors, and exact-match fraction. Do not force exact equality or silently drop unmatched bars.
10. Retain the raw ZIPs, checksum files, a compact per-5m reconciliation CSV, and machine-readable JSON/Markdown reports as the workflow artifact. Do not commit raw market data to Git.

## Pass/fail interpretation

- **Integrity pass:** both official checksums match, both ZIP CRC checks pass, schema is valid, no duplicate aggregate IDs, IDs are strictly increasing, timestamps are non-decreasing and inside the requested month.
- **Reconciliation pass:** all 8,640 expected 5-minute kline buckets exist and aggregate-trade bucket coverage is reported; total volume and taker-buy volume relative errors are each <=0.10%. Per-bar discrepancies are diagnostic and must be reported, not hidden.
- If integrity passes but reconciliation fails, retain the data but classify it as **not ready for signal research** pending explanation. Do not invent a tolerance after seeing the results.
- If the monthly archive is missing or checksum/schema/order validation fails, stop. Do not substitute candles or silently reconstruct from raw trades.

## What this pilot does not test

- No footprint, POC, VAH/VAL, TPO, absorption or strategy PnL is computed.
- No trading signal, entry, stop, target, fees, funding or slippage is tested.
- One month is a data-source pilot, not enough for a strategy backtest or OOS claim.
- The aggregate-trade feed is Binance USD-M BTCUSDT, not Delta BTCUSD; cross-exchange price/fill differences must be handled in any later study.
- Buyer-maker identifies the taker side for the aggregate trade; it does not expose queue position or full order-book depth.

## Next step after this pilot

Only if the integrity and reconciliation checks pass: freeze a separate two-year BTC/ETH trade-level data acquisition plan, explicitly exclude or repair any documented archive gaps (notably the reported 2026-10-28 USD-M futures aggTrades gap), then build true trade-level volume-at-price/delta features. Any later strategy must have its own preregistration and chronological development/validation/untouched holdout.