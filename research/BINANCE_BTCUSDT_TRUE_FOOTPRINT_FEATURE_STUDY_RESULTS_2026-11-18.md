# BTCUSDT true footprint + volume profile + TPO pilot — 18 November 2026

## Decision

**Data reconstruction: PASS. Predictive edge: not established. No strategy promoted.**

This study reconstructs exact traded-price levels and aggressor-side volume from Binance USD-M BTCUSDT aggregate trades. It also builds daily volume profiles and 30-minute UTC TPO profiles. A fixed one-month event study is included only as a diagnostic; it is not a strategy validation.

## Source and integrity

- Market: Binance USD-M BTCUSDT perpetual.
- Period: 2026-09-01 00:00:00.003 UTC to 2026-09-30 23:59:59.591 UTC.
- Official aggTrades ZIP: 437,374,990 compressed bytes; 2,394,164,622 uncompressed CSV bytes.
- aggTrades SHA-256: `252e92894886c2f752744656e4f1d7a278a75e1456aa32442451b07ee9703b80`.
- Matching 5m klines SHA-256: `3a2d163a2bd28ca614fa0840a92ecbcde0d9c4962b278dd619d5bf81a9918e26`.
- Both checksums matched official companion CHECKSUM files; both ZIP CRC checks passed.
- 36,036,629 aggregate-trade records; zero aggregate-ID gaps, duplicates, ordering violations, timestamp regressions or out-of-month records.
- Buyer-maker=true means taker sell; false means taker buy.

Sources:
- https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-09.zip
- https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2026-09.zip
- https://github.com/binance/binance-public-data

## Exact 5-minute footprint

- Verified 0.1 USDT price grid; all source prices mapped exactly to integer tenths.
- Each record assigned to UTC 5m bucket using its transaction timestamp.
- At each (5m bucket, exact price tick), base quantity is separated into taker buys and taker sells; delta = buy − sell.
- 8,510,392 unique 5m price-level rows across 8,640 bars.
- Sum of price-level aggregate-trade counts = 36,036,629.
- POC = maximum volume at a price, ties lower price.
- Contiguous 70% value area expands one 0.1 USDT tick at a time; larger next-level volume first, ties lower; empty ticks count as zero.
- Diagonal buy imbalance: buy(p) >= 3 × sell(p−0.1) and buy(p) >= 0.10 BTC. Sell imbalance is inverse at p vs buy(p+0.1). A stack is at least three consecutive ticks.

### Reconciliation

| Check | Result |
|---|---:|
| 5m bars | 8,640 / 8,640 |
| aggTrade base volume | 4,267,354.779 BTC |
| Official kline base volume | 4,267,354.779 BTC |
| Total-volume relative error | 0.0 |
| Taker-buy volume | 2,112,553.238 BTC |
| Official kline taker-buy volume | 2,112,553.238 BTC |
| Taker-buy relative error | 0.0 |
| Per-bar volume error p95 / max | 0.00438% / 2.6441% |
| Per-bar taker-buy error p95 / max | 0.000683% / 7.9392% |
| POC mismatches in 8,640 bars | 0 |
| Minimum value-area coverage | 70.0000% |

Monthly totals reconcile exactly. The few larger per-bar outliers are retained and reported rather than hidden.

## Daily volume profile + TPO

- 30 UTC daily profiles.
- TPO bracket = 30 minutes aligned to UTC midnight.
- A price receives one TPO for a bracket if at least one aggregate trade occurred at that exact price during the bracket.
- Every day has all 48/48 expected brackets.
- 4,028,233 unique 30m bracket-price keys; 692,614 daily profile rows.
- Daily volume and TPO value areas both cover at least 70%.
- Daily volume POC and TPO POC differed on all 30 days. Median absolute gap: $163.80; mean: $528.20; maximum: $4,461.80. This is descriptive, not predictive.
- Monthly taker-buy volume: 2,112,553.238 BTC; taker-sell: 2,154,801.541 BTC; signed delta: −42,248.303 BTC (−0.9900% of monthly base volume).

## Frozen exploratory event study

This is **not a stop-defined strategy backtest**. No R-multiple, account return or funding-adjusted PnL is implied.

Common rules:
- Signal known after 5m close; entry next 5m open.
- Forward horizons: 12 bars (1h) and 48 bars (4h), exit at corresponding horizon close.
- 10 bps round-trip cost deducted.
- 48-bar global cooldown per event family, across directions.
- No stop, target, funding, spread, slippage or market-impact model.
- 10,000 day-cluster bootstrap resamples for mean-return intervals.

Event definitions:
1. Absorption proxy: delta fraction z-score vs preceding 288 completed 5m bars (minimum 96; rolling statistics shifted one bar). Short if z >= +2 and close location <= 0.25; long if z <= −2 and close location >= 0.75.
2. Continuation proxy: at least 3 consecutive diagonal imbalance ticks (ratio >= 3, numerator >= 0.10 BTC), with close location confirming direction.

| Family / direction | Horizon | Events | Win rate | Descriptive PF | Mean net bps | Median net bps | 95% day-cluster CI | Event-sequence max DD | Losing streak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Absorption short | 1h | 6 | 66.67% | 1.225 | +1.68 | +6.72 | −12.89 to +15.62 | −22.97 bps | 1 |
| Absorption short | 4h | 6 | 50.00% | 2.088 | +14.53 | +3.65 | −24.96 to +55.78 | −77.03 bps | 2 |
| Absorption long | 1h | 6 | 33.33% | 0.365 | −10.97 | −12.83 | −36.53 to +4.55 | −74.43 bps | 2 |
| Absorption long | 4h | 6 | 33.33% | 0.144 | −19.15 | −8.79 | −39.36 to −1.81 | −118.54 bps | 2 |
| Continuation short | 1h | 87 | 32.18% | 0.466 | −9.89 | −13.77 | −16.09 to −2.99 | −924.91 bps | 8 |
| Continuation short | 4h | 87 | 44.83% | 0.656 | −9.08 | −5.98 | −18.46 to +0.48 | −870.27 bps | 4 |
| Continuation long | 1h | 87 | 35.63% | 0.839 | −2.61 | −7.20 | −12.92 to +8.72 | −672.67 bps | 10 |
| Continuation long | 4h | 87 | 48.28% | 1.010 | +0.27 | −2.39 | −19.23 to +21.85 | −753.98 bps | 7 |

Interpretation:
- Absorption short 4h is positive on six events, but its confidence interval is wide and crosses zero.
- Absorption long is negative in this small sample; it does not definitively reject the broader idea.
- Continuation long is approximately flat at 4h after costs (mean +0.27 bps, median −2.39 bps).
- Continuation short is negative at both horizons in this month; the 1h interval is below zero, but this remains one-month exploratory evidence with no independent period or multiple-testing correction.
- No event family is promoted; no thresholds were optimized after seeing results.

## Independent audit

The independent audit verified source SHA-256 and ZIP CRC, all 8,640 contiguous 5m bars, 8,510,392 price-level rows, 36,036,629 aggTrade records, POC and value-area calculations, monthly volume/taker-buy reconciliation, all 186 event return calculations and cost deductions, and 30 daily profiles with 48 TPO brackets each.

Audit: **PASS**. See `quant_discovery/BINANCE_BTCUSDT_TRUE_FOOTPRINT_AUDIT_2026-11-18.json`.

## Decision and next step

1. Treat this as a true-footprint/VP/TPO data-engineering pass, not an edge.
2. Keep the candle-volume VP/TPO proxy family rejected; do not substitute it for exact price-level data.
3. Acquire multiple chronological months of BTCUSDT and ETHUSDT aggTrades plus matching klines. Verify every archive checksum, ordering, date coverage and per-month reconciliation before feature generation.
4. Freeze a separate stop-defined execution study only after multi-month data is assembled; use development/validation and a prospectively untouched holdout, with realistic fees, spread/slippage and funding.
5. Recheck the previously reported Binance 2026-10-28 archive gap before including October; repair only from raw trades after independently validating aggregation rules, otherwise exclude and document.

No production, main-branch, live-alert or exchange-order changes were made.
