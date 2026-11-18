# Binance USD-M BTCUSDT aggTrade historical-data availability audit

**Date:** 2026-11-18  
**Scope:** Data-source and schema probe only; no strategy backtest or signal test was run from trade-level data.

## Findings

### 1. Recent API pilot succeeded

A Binance USD-M BTCUSDT compressed aggregate-trade query for 2026-11-17 12:00:00.000–12:00:09.999 UTC returned 394 records.

Observed fields:

- a: aggregate trade ID
- p: price
- q: quantity
- f, l: first and last underlying trade IDs
- T: timestamp in milliseconds
- m: whether the buyer was maker
- nq: additional field returned by the connected market-data tool

The sample ran from aggregate ID 3,529,196,360 to 3,529,196,753. m=true occurred 209 times and m=false 185 times. Buyer-maker means the taker was selling; buyer-not-maker means the taker was buying.

A one-minute query beginning at the same time with limit=1000 returned exactly 1,000 records and stopped at 12:00:25.174 UTC, before the requested 12:00:59.999 end. The REST endpoint therefore requires pagination for busy intervals.

### 2. Historical REST retrieval is restricted

A historical USD-M aggTrades request for BTCUSDT on 2025-06-17 returned HTTP 400, Binance error code -4166: “Search window is restricted to recent 2 days only.”

Conclusion: the connected REST endpoint is suitable for recent samples and pagination, not for building a two-year archive. Use Binance Vision bulk files for historical research.

### 3. Official bulk archive route

The official binance/binance-public-data repository documents daily and monthly public market-data files. Its python/download-aggTrade.py supports market type um (USD-M Futures), symbol filters, date ranges and checksum downloads. Each ZIP has a companion .CHECKSUM file. Official references:

- https://github.com/binance/binance-public-data/blob/master/README.md
- https://github.com/binance/binance-public-data/blob/master/python/README.md
- https://github.com/binance/binance-public-data/blob/master/python/download-aggTrade.py

A monthly-only pilot can be requested with:

~~~bash
python3 download-aggTrade.py -t um -s BTCUSDT \
  -startDate 2026-09-01 -endDate 2026-09-30 \
  -skip-daily 1 -c 1
~~~

The official repository states that monthly files are published on the first Monday of the following month; daily files are made available the next day. Downloaded ZIPs must be verified against the published checksum before parsing.

### 4. Known archive completeness issue

Official repository issue #525 remains open on the issue page inspected on 2026-11-18. It reports that USD-M futures aggTrades and derived klines for 2026-10-28 are missing (404) across BTCUSDT and other symbols, while raw USD-M trades for that date are published. A Nov 2 comment says the October monthly BTCUSDT aggTrades archive also omitted 2026-10-28.

Reference: https://github.com/binance/binance-public-data/issues/525

Do not silently treat the October monthly file as complete. Before using October 2026:
1. Recheck whether the missing daily/monthly aggregate data has been repaired.
2. If still absent, either reconstruct from the raw trades archive only after reproducing the exact 100ms/same-price/same-taking-side aggregation against adjacent days, or exclude 2026-10-28 and document the gap.
3. Do not fill the gap from klines or a candle-volume proxy.

A separate official issue records that the October 2023 BTCUSDT aggTrades archive was previously disordered and was regenerated on 2026-10-07. This reinforces the need to sort by aggregate-trade ID, retain the original archive hash, and verify order/duplicates rather than trusting file row order blindly: https://github.com/binance/binance-public-data/issues/288

## Acquisition and validation plan

1. Download one full pilot month of BTCUSDT USD-M aggTrades (start with 2026-09) plus its .CHECKSUM.
2. Verify SHA-256 before extraction; retain the source ZIP, checksum text, URL, retrieval time and file hash.
3. Validate CSV schema, finite positive prices, nonnegative quantities, unique aggregate IDs, sorted ID order, timestamp range, duplicate rows and timestamp monotonicity after sorting by aggregate ID.
4. Reconcile total aggregate quantity and taker-side volume against the same month's USD-M klines, while accounting for 100ms boundary timestamps and documented archive issues. Do not require raw trade-ID contiguity without an exchange-defined rule for excluded events.
5. Confirm the buyer-maker sign convention and reconstruct signed delta from m.
6. Only after the pilot passes, acquire the two-year monthly archive and patch or exclude known missing days.
7. Build actual trade-level volume-at-price, TPO and delta features. Keep the existing candle-volume VP/TPO proxies rejected and separate.

## Current status

- Recent 10-second API sample: verified.
- One-minute API pagination limit: verified.
- Historical API restriction: verified.
- Official bulk archive route and checksum process: verified from the official repository.
- Historical ZIP acquisition and checksum verification: **not yet completed**; the binary archive download was not completed in this run.
- True footprint / trade-level backtest: **not run**.
- No production strategy, live alert or exchange-order changes.
