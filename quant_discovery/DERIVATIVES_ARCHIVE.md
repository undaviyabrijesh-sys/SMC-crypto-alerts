# Derivatives-history archive — collection handoff

## Public endpoint probe

The public Delta India `GET /v2/history/candles` endpoint returned non-empty data for all nine combinations over a three-day pilot on 2026-11-05:

| Series | API symbol format | Resolution | Pilot observation |
|---|---|---:|---|
| Funding | `FUNDING:<contract>` | 1h | 67 BTC, 67 ETH, 71 XAUT candles |
| Mark price | `MARK:<contract>` | 5m | 864 candles per contract |
| Open interest | `OI:<contract>` | 1h | 72 candles per contract |

The parser accepts negative funding values, rejects malformed OHLC, and preserves raw numeric values. The public docs describe these prefixes and the 2,000-candle per-response limit: https://docs.delta.exchange/

## Full collection

`bootstrap_derivatives_history.py` downloads a requested three-year window for BTCUSD, ETHUSD and XAUTUSD. It stores nine CSVs, a hash-bearing manifest and a coverage report under `derivatives_history/`. It is resumable, rate-limited and does not fill missing candles.

The three-year window is only a request. Actual available history and gaps must be read from the output. Funding values are retained in raw API units; do not assume whether a value is per-hour, per-funding event or a percentage until the API semantics are independently verified.

The one-time GitHub Actions workflow retains the archive as a 14-day artifact for analysis. It does not commit raw market data to Git. The workflow is guarded and runs only for a tagged commit or manual workflow dispatch.

## Research use

- First inspect actual first/last timestamps, candle cadence, gaps and hash checks for every series.
- Align funding events to positions without look-ahead. Determine sign convention and units before applying any funding cost.
- Use mark price only for the intended valuation/liquidation checks; traded-price OHLC remains the trade execution proxy until bid/ask/depth history is available.
- Use open interest as a separately lagged research feature, never as an unlagged future-known input.
- Do not convert a price-only paper result into an exchange PnL claim. Spread, depth, contract rules, margin and settlement conversion still require dedicated validation.


## Current bounded automation run — 2026-11-12

The one-time GitHub Actions workflow has been scoped to **two years of BTC and ETH only** for the first full coverage audit. It requests six raw series: BTC/ETH funding (1h), mark price (5m) and open interest (1h). This is a workflow-specific override; the collector CLI still supports the broader three-year BTC/ETH/XAUT archive.

The run is not considered complete until the six expected dataset keys, non-empty CSVs, row counts, SHA-256 hashes, first/last timestamps, requested and observed coverage, and gaps are verified. Funding values remain raw API units. Do not infer per-event rate scaling or apply funding to trade P&L until settlement timing and sign convention are established. Mark-price history remains separate from traded-price OHLCV.

The first workflow attempt exposed a verifier variable-reference bug after download. Its full artifact was nevertheless uploaded and independently audited: all six CSVs, row counts and SHA-256 hashes match the manifest (490,818 candles total). The job's failure was in the final verifier only, not in the downloader. See [DERIVATIVES_ARCHIVE_AUDIT_2026-11-12.md](DERIVATIVES_ARCHIVE_AUDIT_2026-11-12.md) for exact coverage, hashes and funding diagnostics. The verifier expression is corrected on the research branch; the retry was cancelled by branch concurrency, so the manual artifact audit is the evidence used here.


## Verified two-year BTC/ETH archive — 2026-11-14

The guarded workflow completed successfully: [run 43570739333](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43570739333), [artifact 14104591074](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43570739333/artifacts/14104591074). The artifact contains six verified CSVs, manifest, coverage report and archive validation report (490,818 candles total). All six dataset hashes and row counts match; no validation errors.

| Dataset | Rows per asset | Observed coverage | Gaps |
|---|---:|---:|---:|
| Mark price, 5m | 210,383 | 100.0000% | 0 |
| Open interest, 1h | 17,531 | 100.0000% | 0 timestamp gaps |
| Funding, 1h | 17,495 | 99.8174% | 8 per asset, each a 5-hour gap |

**Quality caveats:** BTC and ETH OI each contain two rows with a zero low and positive open/close (2026-04-12 21:00 UTC and 2026-05-19 13:00 UTC). Keep the source rows in the raw archive, but quarantine them from OI feature calculations. Funding values remain raw and their units, sign convention and settlement cadence are not yet independently verified; do not apply them to strategy PnL. The funding gaps are not filled.

The artifact expires 2026-11-28. It is not committed to Git; download it before expiry if a later research run needs the source CSVs.
