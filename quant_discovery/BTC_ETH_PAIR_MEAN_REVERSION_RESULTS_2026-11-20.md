# BTC/ETH rolling-residual pair mean-reversion study — 20 November 2026

## Decision

**Reject the tested mechanical pair-mean-reversion family. No training configuration qualified, no validation configuration passed, and the final 15% OOS segment was not evaluated. No strategy is promoted.**

## Workflow and reproducibility

- GitHub Actions workflow: [run 44764311936](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44764311936)
- Artifact: [14643076972](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44764311936/artifacts/14643076972)
- Artifact ZIP digest: `sha256:1ffb5b14966440e335497ee898a196f5aa69d6f590869c628f21e71db2695fea`
- The workflow completed successfully. Its deterministic tests, historical data download, 576-configuration matrix, summary generation and artifact upload all passed.
- The artifact was downloaded and inspected. It contains both raw 15m inputs, a source manifest, coverage report, full matrix, diagnostic trade ledger, monthly and regime tables, metadata and the cost-sensitivity output.

## Dataset

- Venue: Delta Exchange India, public traded-price OHLCV.
- Instruments: BTCUSD and ETHUSD perpetuals, 15-minute bars.
- Raw inputs: 70,127 rows per instrument; zero missing 15m intervals; zero duplicate rows.
- Post-transition aligned sample: 42,062 rows, from 2025-09-08 12:00 UTC through 2026-11-20 15:15 UTC.
- BTC SHA-256: `d346c5e093db13036f1701245660f44824fc6fbd4ad0b1fcdfc6516cf26bd23c`
- ETH SHA-256: `6fd2db89debc6a4888dc1c08810ce0a02784d407dccd7d1967eb23e61a019d2b`
- Zero-volume bars: BTC 80; ETH 85. They remain in the price series; volume is not a pair-signal input.
- Train ends: 2026-07-12 04:45 UTC.
- Validation ends: 2026-09-15 22:00 UTC.
- Chronological split: 70% train / 15% validation / 15% reserved OOS. OOS was not evaluated.

## Frozen model and execution

- Rolling OLS of log(ETH) on log(BTC), using prior-only 10d or 30d lookbacks; positive hedge ratio constrained to 0.25–4.0.
- Residual mean/std use prior-only 3d or 7d lookbacks.
- Signal: completed 15m residual z-score crosses ±1.5, ±2.0 or ±2.5; signal becomes available at candle close and both legs enter at the next 15m open.
- Stops: residual z 3.5 or 4.0. Targets: z 0.0 or 0.5. Maximum holds: 4h or 6h. Direction: both, long-spread-only or short-spread-only. Correlation threshold: 0 or 0.6.
- One position at a time per exact configuration. Completed 1H BTC EMA50/EMA200 regime is recorded.
- Synthetic log-spread OHLC uses adverse cross-leg extremes; stop is checked before target, adverse stop gaps are filled at the observed open, and time exits use the final close.
- Costs: 6/12/20 bps round-trip per leg; primary 12 bps per leg (scenario assumes 5 bps fee plus 1 bp slippage per side). Actual account fee tier, order-book spread/depth and market impact are not verified.
- Pair `net_R` is normalized by the fixed residual-spread z-distance to stop. It is not account-equity return or portfolio risk.

## Funding treatment — conditional, not a historical cashflow model

The sample starts at Delta's documented 2025-09-08 12:00 UTC funding-mechanism transition. At run time, current BTCUSD and ETHUSD product metadata both reported an 28,800-second exchange interval. The script then used the standard 00:00/08:00/16:00 UTC schedule, rejected exact-boundary entries, forced positions flat at the 15m open before each assumed snapshot and asserted that no recorded trade overlapped that grid.

**Important limitation:** current product metadata does not prove that the contract-specific interval remained unchanged throughout the entire historical sample. The historical schedule was not independently reconstructed event-by-event in this run. No funding cashflow is imputed. The result must be described as funding-avoiding under the assumed standard 8h post-transition schedule, not as a fully funding-accounted backtest.

## Matrix result at 12 bps

- Nominal configurations: 576.
- Training-eligible configurations: **0**.
- Validation passes: **0**.
- OOS evaluations: **0**.
- Every configuration had negative train net R and negative validation net R; no train or validation row had PF above 1.
- The `corr_min=0.6` filter produced identical metrics to `corr_min=0` for every paired configuration. Independent reconstruction found rolling return correlation never fell below 0.6 after warm-up: minimum 0.7107 for the 10d lookback and 0.7520 for the 30d lookback. Thus the nominal 576 rows collapse to 288 distinct result sets; the correlation filter was non-binding in this sample.

### Best training configuration (ranked by training net R)

- Config: beta 30d, residual z 7d, entry z 1.5, stop z 4.0, target z 0.5, 6h max hold, long-spread-only.
- Train: 139 trades, 53.96% profitable, PF 0.9073, -2.248R, average -0.0162R, max DD -4.923R, losing streak 6, 40% positive active months.
- Matching validation: 21 trades, 38.10% profitable, PF 0.5178, -2.173R, average -0.1035R, max DD -2.681R, losing streak 4, 0% positive active months.

### Best validation diagnostic with at least 20 trades

This row is selected by validation ranking for diagnosis only; its validation performance is not an independent estimate.

- Config: beta 10d, residual z 7d, entry z 2.0, stop z 4.0, target z 0.5, 6h max hold, both directions.
- Train: 206 trades, 40.29% profitable, PF 0.4879, -38.902R, average -0.1888R, max DD -38.902R, losing streak 8, 1/11 positive months.
- Validation: 34 trades, 44.12% profitable, PF 0.8025, -1.635R, average -0.0481R, max DD -4.873R, losing streak 5, 1/3 positive months.
- Outcomes: train 45 TP / 48 SL / 28 TIME / 85 FUNDING_FLAT; validation 8 TP / 5 SL / 5 TIME / 16 FUNDING_FLAT.

### Diagnostic candidate cost sensitivity

Recalculated from the saved 12 bps trade ledger by scaling the recorded linear cost component. This is not the workflow's selected-candidate cost table; the official `cost_sensitivity.csv` is empty because no configuration passed the selection gates.

| Cost per leg, round trip | Train net R / PF | Validation net R / PF |
|---:|---:|---:|
| 6 bps | -19.908R / 0.693 | +1.245R / 1.183 |
| 12 bps | -38.902R / 0.488 | -1.635R / 0.802 |
| 20 bps | -64.227R / 0.307 | -5.474R / 0.483 |

The validation-only positive result at 6 bps is paired with a strongly negative training result and therefore does not establish a stable edge.

## Monthly and regime diagnostics

For the validation-ranked diagnostic candidate, training monthly net R was negative in 10 of 11 active months; only May 2026 was positive (+0.823R). Validation was negative in July (-1.297R) and August (-1.844R), with September +1.507R.

Training regime net R was negative in bear (-17.833R / 95 trades), bull (-15.598R / 55) and range/unavailable (-5.471R / 56). Validation regime totals were bear -2.488R / 4 trades, bull +0.262R / 21 and range/unavailable +0.592R / 9; the two positive buckets are small and do not offset the negative aggregate.

## Limitations

1. Rolling residual mean reversion is not proof of cointegration or stationarity; no Engle–Granger, Johansen, ADF or KPSS test was part of this run.
2. Historical funding interval continuity is not verified; funding cashflow is excluded.
3. Synthetic spread OHLC cannot reconstruct exact intrabar ordering across two independently traded legs.
4. Costs are assumed per leg and do not include measured order-book depth or market impact.
5. The validation-ranked diagnostic was chosen after inspecting validation and must not be treated as an unbiased validation estimate.
6. OOS remains untested and must stay untouched.

## Decision and next step

Reject this exact rolling-residual pair-mean-reversion matrix. Do not tune the inspected train/validation data or evaluate the reserved OOS. Before any further pair strategy work, preregister a separate train-only residual-stationarity/cointegration diagnostic with a fixed test family and multiple-testing control; do not assume that a high rolling return correlation establishes a stationary tradable spread.

No production rules, approved strategies, live alerts, paper state, exchange orders or main branch were changed.
