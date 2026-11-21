# BTC/ETH train-only residual stationarity and cointegration diagnostic — preregistration

**Date:** 2026-11-20  
**Branch:** ai-quant-rebuild  
**Classification:** statistical research diagnostic only; not a trading strategy or backtest

## Motivation and prior art

The completed BTC/ETH rolling-residual pair mean-reversion study tested 576 nominal configurations (288 distinct metric sets after a non-binding correlation filter). No training configuration qualified, no validation configuration passed, and the reserved final 15% was not evaluated. The study explicitly identified a missing prerequisite: rolling return correlation does not establish that the log-price spread is stationary or cointegrated.

This diagnostic addresses only that prerequisite. It does not alter the prior strategy result, search new entry thresholds, select a trading configuration, or evaluate the reserved validation/OOS periods.

## Frozen dataset and boundary

- Venue: Delta Exchange India public traded-price OHLCV.
- Instruments: BTCUSD and ETHUSD perpetuals.
- Bars: 15-minute UTC candles.
- Start inclusive: 2025-09-08T12:00:00Z.
- Training end exclusive: 2026-07-12T04:45:00Z.
- Expected aligned training rows: 29,443 per leg.
- The end is the exact 70% chronological boundary recorded by the prior pair study. The last included candle opens at 04:30 UTC and closes at 04:45 UTC.
- Download only this training interval. Do not download, read, or evaluate validation or OOS rows.
- Require identical BTC/ETH timestamps, no duplicates, no missing 15-minute intervals, valid positive OHLC, and exact expected row count. Fail closed if any check fails.
- Record source CSV SHA-256 hashes, manifest, first/last candle timestamps, row counts, package versions and test parameters.

## Primary statistical specification

Use one fixed regression orientation, matching the prior strategy's hedge-ratio convention:

\[
\log(ETH_t) = \alpha + \beta \log(BTC_t) + \epsilon_t
\]

- Deterministic specification: intercept, no deterministic time trend (trend="c").
- Primary test: Engle–Granger two-step cointegration test using statsmodels.tsa.stattools.coint.
- Autolag: AIC; library-selected maximum lag; record the library version.
- Null hypothesis: no cointegration.
- No reverse regression, trend alternative, lag grid, pair selection or alternative deterministic specification will be tried.
- Run the primary test once on the entire frozen training interval.

## Pre-registered stability family and multiple-testing control

Run the identical Engle–Granger specification on four contiguous, non-overlapping, chronological blocks formed by splitting the training rows into four equal positional blocks (the final block may contain one extra row).

The inferential family contains exactly five p-values:
1. Full training interval (primary).
2. Training block 1.
3. Training block 2.
4. Training block 3.
5. Training block 4.

Apply Holm–Bonferroni adjustment across all five p-values. Report raw and adjusted p-values, test statistic, 1%/5%/10% critical values, sample size, and block boundaries. No other cointegration tests or specifications may be added after seeing results.

Predefined evidence classification:
- First check the I(1) precondition: ADF on each log-price level should fail to reject a unit root at 5%, while ADF on each first difference should reject at 5%. Report these four precondition diagnostics separately; they are not part of the five-test Engle–Granger family.
- “Persistent train-only cointegration evidence” requires the I(1) precondition, Holm-adjusted full-training p-value < 0.05, and at least three of four Holm-adjusted block p-values < 0.05.
- If the I(1) precondition fails, classify the cointegration interpretation as inconclusive.
- Otherwise report either no full-training evidence or evidence that is not stable across blocks. Do not reinterpret thresholds after seeing output.

## Descriptive rolling-hedge-ratio stability (not a hypothesis search)

Reuse the existing pair-study feature_frame implementation, which computes rolling OLS baselines with a one-bar lag. Calculate only the already-used 10-day (960 bar) and 30-day (2,880 bar) lookbacks on the training-only frame, with the existing 3-day residual lookback for feature warm-up.

Report non-null count, beta median, 5th/95th percentiles, IQR, minimum/maximum, positive-beta fraction, fraction inside the existing 0.25–4.0 strategy range, and rolling return-correlation median/minimum. These are descriptive stability statistics, not additional tests and not a basis for selecting a new lookback.

## Execution, costs and funding

This is a statistical time-series diagnostic, not a trade simulation:
- No entries, exits, positions, PnL, win rate, profit factor, drawdown or trading return are generated.
- Transaction costs, funding, spread and slippage are not applicable to the statistical test. Do not present this result as evidence of executable profitability.
- Delta's unresolved historical funding mechanics are irrelevant to this no-position diagnostic and must not be silently treated as solved.

## Reproducibility and fail-closed rules

- Use the existing bootstrap_historical_data.py downloader and research/btc_eth_pairs_mean_reversion_backtest.py data validation/alignment/rolling-feature functions; do not create a second candle downloader or hedge-ratio implementation.
- Pin the diagnostic dependency and record Python, pandas, NumPy, SciPy and statsmodels versions.
- Run deterministic self-tests for Holm adjustment, exact four-block coverage, synthetic cointegrated and independent random-walk examples, and future-perturbation invariance of the reused rolling beta features.
- Preserve raw inputs, hashes, coverage and all result CSV/JSON/Markdown outputs as a workflow artifact.
- Never inspect validation or OOS data in this workflow.
- No strategy promotion, parameter optimisation, live alerts, paper-state mutation, exchange orders, production changes, main-branch changes or deployment.

## Decision and next step

This test can establish only whether the specified BTC/ETH log-price relationship shows train-only cointegration evidence under the frozen regression and block-stability criteria. Even a positive result would not reverse the rejected pair-strategy matrix or establish a tradable edge. Any further strategy research would require a separately preregistered design and genuinely new prospective data.
