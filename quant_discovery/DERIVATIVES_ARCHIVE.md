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

The first workflow attempt exposed a verifier variable-reference bug after download; a corrected run is queued. No archive coverage result is claimed yet.
