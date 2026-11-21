# BTCUSDT multi-month true-footprint / VP / TPO reconstruction — frozen preregistration

Date: 2026-11-19 UTC  
Branch: `ai-quant-rebuild`  
Parent: `BINANCE_BTCUSDT_TRUE_FOOTPRINT_FEATURE_STUDY_PREREGISTRATION_2026-11-18.md`  
Status: data/feature reconstruction only. No strategy PnL, threshold search, candidate ranking or promotion.

## Scope and months

Rebuild the exact same monthly feature pipeline independently for:
- 2026-06
- 2026-07
- 2026-08
- 2026-09 (reference month, rebuilt with the stricter contiguous-value-area and 48-bracket gates below)

Each run downloads the official Binance USD-M BTCUSDT monthly aggTrades archive and matching 5m kline archive, plus each archive's official `.CHECKSUM`. Months remain separate outputs; do not concatenate raw files across month boundaries or infer a pooled strategy result.

## Frozen data definitions

- Market: Binance USD-M BTCUSDT perpetual.
- Price grid: exact aggTrade price validated on a 0.1 USDT tick; store the integer price tick `round(price * 10)` and derive display price as tick / 10. Reject any off-grid row.
- Aggressor side: `buyer_maker=false` is taker buy; `buyer_maker=true` is taker sell.
- 5m bucket: `floor(transact_time_ms / 300000) * 300000` UTC.
- At each (5m bucket, integer price tick), sum base quantity separately for taker buys and sells, total volume, delta and aggTrade record count.
- Preserve aggregate-trade ID order, uniqueness, timestamp monotonicity, first/last underlying trade IDs, ID gaps and archive bounds. ID gaps are reported; duplicate or non-increasing IDs and timestamp regressions fail integrity.
- Matching official 5m klines must contain exactly the expected contiguous calendar-month timestamps. Reconcile total volume and taker-buy volume within 0.10%; report per-bar median/p95/max errors and unmatched bars. No silent fill or interpolation.
- Daily profile: exact-price total volume, taker buy, taker sell and delta.
- Daily TPO: one count per distinct UTC 30-minute bracket in which an exact price traded; a price is counted at most once per bracket.
- Every UTC day must contain trades in all 48 aligned 30-minute brackets. Missing brackets are explicitly listed and fail the profile gate; do not impute them.
- Daily volume POC and TPO POC are the highest-weight price tick; ties choose the lower tick.
- Contiguous 70% value area starts at POC and expands one 0.1 USDT tick at a time toward the side with the larger next-tick weight. Untraded intervening ticks have zero weight but remain adjacent ticks. Ties choose the lower side.
- Require unique (5m bucket, integer price tick) keys, exact quantity conservation between price levels and source aggTrades, and delta = taker buy - taker sell.

## Validation gates

For each month independently:
1. Both official ZIP checksums match and ZIP CRC passes.
2. AggTrade IDs are strictly increasing, timestamps never regress, all timestamps are within the requested UTC month, and every price is on the 0.1 USDT grid.
3. Matching 5m kline timestamps are exact and contiguous for the calendar month.
4. Total volume and taker-buy reconciliation are within 0.10%; no unmatched 5m bars.
5. All expected UTC days have daily profiles.
6. Every day has all 48 30m TPO brackets; report the exact missing bracket timestamps on failure.
7. Value-area coverage is at least 70% for both volume and TPO profiles, using the contiguous zero-filled tick grid.
8. Price-level keys are unique and quantity/delta sums reconcile to the source.

A failed month remains failed and must not be used for feature-event statistics. Do not relax gates after seeing the month.

## Methodological correction versus the September pilot

The earlier September implementation expanded value areas over observed price rows only, which could skip an untraded intervening 0.1 tick. This extension corrects that by explicitly inserting zero-weight ticks during contiguous expansion. It also makes integer price ticks explicit and enforces all 48 TPO brackets per UTC day. Therefore the rebuilt September value-area levels may differ from the previous September artifact. Preserve the old artifact as historical provenance; do not overwrite it or present the new result as a byte-for-byte reproduction.

## Outputs

Each month produces its own artifact containing:
- source aggTrades and kline ZIPs plus verified CHECKSUM metadata;
- exact-price 5m footprint rows with integer price ticks, volume, buy, sell and delta;
- 5m bar delta and kline reconciliation;
- daily volume/TPO profile by price;
- daily POC/VAH/VAL summaries;
- metadata and a report including all integrity, reconciliation, price-grid, daily-profile, bracket-coverage and value-area gates.

## Interpretation boundary

This is a data-engineering and feature-reconstruction study only. No absorption/continuation event statistics, entries, stops, targets, costs, funding, leverage or PnL are computed in this workflow. The existing September event definitions remain frozen; a separate preregistration is required before any multi-month event study. No best-month selection, parameter tuning, promotion, live alerts or exchange orders.
