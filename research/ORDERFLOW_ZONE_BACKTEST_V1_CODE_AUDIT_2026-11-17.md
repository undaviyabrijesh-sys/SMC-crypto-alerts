# BTC/ETH order-flow zone backtest — implementation audit and V2 correction

**Date:** 2026-11-17  
**Research branch:** `ai-quant-rebuild`  
**Status:** V1 results are negative but not an exact implementation of the frozen specification; corrected V2 run queued, not yet verified.

## What was inspected

- Existing implementation: `research/orderflow_profile_backtest.py`
- Existing results: `quant_discovery/ORDERFLOW_ZONE_BACKTEST_LATEST.md`, `ORDERFLOW_ZONE_BACKTEST_METRICS_LATEST.csv`, `ORDERFLOW_ZONE_BACKTEST_MONTHLY_LATEST.csv`, and `ORDERFLOW_ZONE_BACKTEST_REGIME_LATEST.csv`
- Frozen hypothesis: `research/ORDERFLOW_ZONE_BACKTEST_PREREGISTRATION_2026-11-17.md`
- Dataset: Binance USD-M BTCUSDT and ETHUSDT 5-minute perpetual klines with total volume and taker-buy base volume. V1 metadata reports 209,925 valid bars per asset, 2024-11-17 02:15 UTC to 2026-11-15 23:55 UTC, zero timestamp gaps, 728 complete prior UTC-day profiles and 549 bars without a prior-day profile.

## V1 primary results as recorded in the repository

2R target, 10 bps assumed round-trip cost:

| Asset | Model | Split | Trades | Win rate | PF | Net R | Max DD R | Max losing streak | Positive active months |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | VP_ONLY | Development | 567 | 27.69% | 0.155 | -780.39R | -785.07R | 16 | 5.6% |
| BTC | VP_ONLY | Validation | 112 | 16.07% | 0.093 | -198.76R | -198.76R | 26 | 0% |
| BTC | TPO_DELTA | Development | 243 | 16.87% | 0.055 | -495.14R | -495.73R | 25 | 0% |
| BTC | TPO_DELTA | Validation | 55 | 21.82% | 0.063 | -114.60R | -114.60R | 11 | 0% |
| BTC | VP_TPO_DELTA_MSS | Development | 27 | 40.74% | 0.279 | -23.87R | -23.94R | 5 | 25% |
| BTC | VP_TPO_DELTA_MSS | Validation | 6 | 16.67% | 0.113 | -8.38R | -8.38R | 4 | 25% |
| ETH | VP_ONLY | Development | 571 | 33.80% | 0.343 | -419.47R | -420.84R | 12 | 0% |
| ETH | VP_ONLY | Validation | 115 | 31.30% | 0.242 | -110.21R | -110.21R | 10 | 0% |
| ETH | TPO_DELTA | Development | 226 | 30.97% | 0.195 | -265.84R | -265.84R | 20 | 0% |
| ETH | TPO_DELTA | Validation | 66 | 19.70% | 0.080 | -103.73R | -104.91R | 12 | 0% |
| ETH | VP_TPO_DELTA_MSS | Development | 32 | 40.63% | 0.498 | -15.66R | -18.50R | 4 | 23.1% |
| ETH | VP_TPO_DELTA_MSS | Validation | 12 | 50.00% | 0.809 | -1.87R | -4.92R | 3 | 25% |

The recorded OOS diagnostics were also negative for every asset/model. OOS is not a tuning set.

At 2R and 4 bps, every development row remained negative. ETH VP_TPO_DELTA_MSS validation was +3.57R at 4 bps, but only 12 trades and its development result was -1.35R; this is underpowered and does not pass. At 20 bps every development and validation row was negative.

## Implementation discrepancies found

1. **ATR seed did not match the preregistered Wilder definition.** V1 used `ewm(alpha=1/14, adjust=False, min_periods=14)`, which recursively starts from the first true-range observation rather than seeding the first ATR with the SMA of the first 14 true ranges. This can change penetration offsets and stop distances.
2. **Undocumented maximum-risk filter.** V1 excluded trades when stop risk exceeded 2.5 × ATR. This rule is not in the frozen preregistration and could alter the candidate/trade sample.
3. **Split event attribution was not strict.** V1 checked the entry index against a split but did not require the rejection and (for MSS) confirmation indices to belong to the same split. The V2 implementation requires rejection, confirmation and entry all inside the same split and excludes any trade whose exit is at or beyond split end rather than truncating it.
4. **Proxy limitations remain.** VP is candle-range volume allocation, TPO is 5-minute bar-range occupancy, and delta is aggregate taker-buy minus taker-sell volume per 5-minute bar. This is not true exchange-native volume-at-price, 30-minute TPO or delta-at-price/footprint absorption. Fees are sensitivities; spread, slippage, impact and funding cashflows are not modeled.

## V2 correction

A separate implementation was added to preserve the V1 code and its historical outputs:

- `research/orderflow_profile_backtest_v2.py`
- `.github/workflows/btc-eth-orderflow-zone-backtest-v2.yml`
- Frozen specification copied to the research branch at `research/ORDERFLOW_ZONE_BACKTEST_PREREGISTRATION_2026-11-17.md`

V2 uses canonical Wilder ATR (SMA seed, recursive smoothing, reset after gaps), removes the unregistered 2.5 ATR risk cap, enforces split-local rejection/confirmation/entry and excludes cross-split exits. Deterministic regression tests cover the ATR seed, funding cutoff, stop-first ambiguity and split isolation.

The push-triggered GitHub Actions workflow was committed with message prefix `RUN_ORDERFLOW_PROFILE_V2:`. At the time of this audit, the available GitHub connector returned no push-run metadata or commit status. **V2 market execution and results are therefore pending/unverified.** No V2 performance numbers are claimed.

## Branch hygiene finding

A commit comparison showed `main` was one commit ahead of `ai-quant-rebuild`; the extra main commit `2d415d81249ff5e1751bed6ce37698a8297e3f6b` adds the frozen order-flow preregistration. This is a pre-existing branch divergence, not a change made in this run. The exact preregistration was copied onto `ai-quant-rebuild` so the research workflow has its own copy. **No write, revert or other mutation was made to `main`.**

## Decision and next step

- Do not promote any V1 VP/TPO/delta model. The V1 recorded development/validation results are decisively negative, but treat them as provisional until the specification-aligned V2 replay is complete.
- Do not tune thresholds or use OOS to select a variant.
- Verify the V2 workflow, inspect raw-data hashes and quality metadata first, then compare the corrected 2R/10 bps development and validation results with the V1 report.
- If V2 remains negative, close this candle-proxy family and require actual trade-level price/quantity/aggressor-side data before revisiting footprint or delta-at-price hypotheses.

No production strategy, approved rule, live alert, exchange order or `main` branch was changed.
