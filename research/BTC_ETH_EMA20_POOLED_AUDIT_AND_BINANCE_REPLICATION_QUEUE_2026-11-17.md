# BTC/ETH EMA20 pullback pooled audit and Binance replication queue — 2026-11-17

## Scope

This is an independent audit of the already completed Delta BTC/ETH 15m EMA20 pullback/reclaim event-study artifacts. It is not a new backtest, not a new strategy family and not an OOS evaluation. The purpose is to check whether the apparently positive 4h relative lift is robust enough to justify a stop/target study, and to preregister an independent exchange replication before fetching new data.

## Pooled Delta event-study audit

Inputs:
- `results/btc/event_returns.csv`, `results/btc/control_returns.csv`
- `results/eth/event_returns.csv`, `results/eth/control_returns.csv`
- Only matched event/control pairs; 10 bps round-trip cost.
- BTC uses Delta BTCUSD 5m-derived 15m bars; ETH uses Delta ETHUSD native 15m bars.
- Fixed-horizon returns only. No stop, target, R, executable account PnL or portfolio drawdown is inferred.

### 1h horizon

- 32 matched events across BTC and ETH, on 29 UTC date clusters.
- Pooled event mean: -5.94 bps; median: -12.17 bps; net-positive fraction: 37.5%; descriptive PF: 0.728.
- Matched-control mean: -2.01 bps; paired lift: -3.94 bps.
- Day-cluster bootstrap (30,000 resamples): event-mean 95% interval [-21.39, +11.55] bps; paired-lift interval [-37.37, +24.47] bps.
- Conclusion: no evidence of a positive 1h effect.

### 4h horizon

- 32 matched events across BTC and ETH, on 29 UTC date clusters.
- Pooled event mean: +32.37 bps; median: -4.61 bps; net-positive fraction: 43.8%; descriptive PF: 2.521.
- Matched-control mean: -2.87 bps; paired lift: +35.24 bps.
- Day-cluster bootstrap (30,000 resamples): event-mean 95% interval [-6.98, +76.39] bps; paired-lift interval [+2.88, +73.25] bps.
- Robustness checks: pooled 20%-trimmed event mean +2.89 bps; BTC trimmed mean -1.98 bps; ETH trimmed mean +8.85 bps. The three largest positive events account for 51.6% of the total positive-return sum. BTC's 4h event mean is +29.60 bps (median -4.09); ETH's is +35.51 bps (median -5.13).
- Interpretation: the paired lift is positive in this small sample, but the absolute event-mean confidence interval crosses zero, the median is negative, the trimmed mean is only +2.89 bps after the 10 bps cost assumption, and a weak control group contributes materially to the lift. The bootstrap is conditional on one deterministic matched control per event and does not integrate control-selection uncertainty.
- Conclusion: interesting relative-performance hypothesis, not a demonstrated tradable edge. Do not proceed to stop/target fitting or select side/regime subsets.

## New cross-exchange replication preregistered

A frozen Binance USDⓈ-M ETHUSDT 15m replication has been registered before data retrieval:
- Preregistration: `research/BINANCE_ETHUSDT_15M_EMA20_4H_CROSS_EXCHANGE_REPLICATION_PREREGISTRATION_2026-11-17.md`
- Script: `research/binance_ethusdt_ema20_cross_exchange_replication.py`
- Workflow: `.github/workflows/eth-binance-ema20-cross-exchange.yml`
- Data window: 2025-03-08 00:00 UTC to 2026-07-15 00:00 UTC (end-exclusive); six-month warm-up; evaluation 2025-09-08 12:00 UTC to 2026-07-15 00:00 UTC. The final four months beginning 2026-07-15 are not downloaded.
- Rules, controls, 1h/4h horizons, settlement cutoff, 4/7/10/20 bps sensitivities and decision gates are frozen in the preregistration.
- Workflow commit: `0afba7edaeea89db5c123fd9c00a46138e1c1213`; script commit: `a65e23ad6980e981c2329ad83042e2ab82a554bf`; preregistration commit: `254e27e079055975cd10f23f4d361ee99f539344`.
- At the time of this audit, the available GitHub connector returned no run metadata or commit status for the workflow commit. Therefore **the Binance download/backtest is pending/unverified and no Binance result is claimed**. If Actions is disabled or the run cannot be observed, the missing evidence is a completed workflow run plus its uploaded artifact.

## Decision and next step

- Keep the Delta EMA20 pullback study experimental/inconclusive.
- Do not optimise it or fit stops/targets from the inspected samples.
- Verify the preregistered Binance ETHUSDT replication and inspect its raw data-quality report before interpreting any metrics.
- If the cross-exchange replication is also weak or underpowered, archive the EMA family as rejected under these definitions and move to a distinct, independently sourced signal family.
- No `main`, production, approved-strategy, live-alert or exchange-order changes.
