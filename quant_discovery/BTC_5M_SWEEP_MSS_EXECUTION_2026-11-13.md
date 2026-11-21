# BTC 5m execution after 1H liquidity sweep + 15m MSS — 13 November 2026

## Decision

**Reject this mechanical variant. Zero validation passes; OOS was not evaluated.**

The 5m FVG-midpoint and MSS-midpoint retest entries did not demonstrate a robust improvement over the next-5m-open baseline. The best training configuration was next-open, not either retest confirmation.

## Reproducibility

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts`
- Branch: `ai-quant-rebuild`
- Workflow: [43288853309](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43288853309)
- Artifact: [btc-5m-sweep-mss-43288853309](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43288853309/artifacts/13975253117)
- Code: `research/btc_5m_sweep_mss_execution_backtest.py`
- Workflow file: `.github/workflows/btc-5m-sweep-mss-execution.yml`
- Corrected code commit used by the run: `fb3728bef9cc7b4b0ecf404de39a0b8556ac74e0`
- Eight deterministic causality, FVG, gap-reset and execution tests passed.
- Dataset SHA-256: `85934a5753f7cb00003ba3d60788209dd042aab2cee27a6e0593041297b15192`

## Data

Delta BTCUSD traded-price OHLCV, 5m candles, 12 Nov 2024 19:20 UTC through 12 Nov 2026 19:10 UTC.

| Series | Complete rows |
|---|---:|
| 5m | 210,239 |
| Derived 15m | 70,079 |
| Derived 1h | 17,519 |
| Derived 4h | 4,379 |

- Missing 5m intervals: 0
- Duplicate rows removed: 0
- Zero-volume rows: 335
- Chronological split: 70/15/15
- Training end: 7 Apr 2026 19:15 UTC
- Validation end: 26 Jul 2026 07:15 UTC
- OOS period reserved but not evaluated.

## Exact hypothesis

- Confirmed 1h swing high/low using 2 or 3 bars on each side.
- The pivot is usable only from the first 15m close strictly after the right-side confirmation close. This uses `searchsorted(side="right")`, not the confirmation candle itself.
- Sweep = wick beyond the frozen 1h level and 15m close back across it.
- Structure reference = last already-confirmed 15m opposite swing before the sweep.
- MSS = 15m close through that structure within 4 or 8 bars while the reclaim remains valid.
- 5m entries: (a) first 5m open after MSS; (b) latest same-direction 5m FVG midpoint retest plus directional body/close; (c) 15m MSS candle midpoint retest plus directional body/close.
- Retest expiry: 12 5m candles. Stop = full sweep-to-MSS extreme plus 0 or 0.1 x ATR14(5m). Targets 1.5R/2R/3R. Maximum holding 4h.
- Filters: none or completed 4h EMA50/200 alignment; both/long-only/short-only; all hours or 07:00–19:00 UTC.
- 1,728 configurations.
- Flat round-trip cost sensitivities: 6/12/20bp. Funding excluded pending verified settlement-time attribution.
- Same-bar stop first; adverse stop gaps at worse open; target gaps filled at target; no trades cross sample boundaries or data gaps.

## Results at 12bp assumed round-trip cost

### Selection funnel

| Metric | Result |
|---|---:|
| Configurations | 1,728 |
| Training-eligible | 63 |
| Validation passes | 0 |
| OOS evaluated | No |

Training gate: at least 40 trades, PF >= 1.05, positive net R, positive active months >= 50%, max drawdown >= -15R.

Validation gate: at least 20 trades, PF >= 1.05, positive net R, positive active months >= 50%, max drawdown >= -10R.

### Best training candidate

Next-5m-open baseline; 1h and 15m pivot strength 3; MSS window 8; no stop buffer; 1.5R target; no 4h filter; short-only; 07:00–19:00 UTC.

| Metric | Training | Validation |
|---|---:|---:|
| Trades | 47 | 8 |
| Win rate | 53.19% | 62.50% |
| Profit factor | 1.649 | 3.631 |
| Net R | +9.47R | +4.09R |
| Average R/trade | +0.201R | +0.511R |
| Maximum drawdown | -3.25R | -1.39R |
| Maximum losing streak | 2 | 2 |
| Positive active months | 55.6% | 50.0% |

This is not a validation pass: eight validation trades are below the 20-trade minimum.

### Best validation result with at least 20 trades

Next-5m-open baseline; pivot strengths 3/3; MSS window 8; no buffer; 3R target; no 4h filter; both directions; all hours.

| Metric | Training | Validation |
|---|---:|---:|
| Trades | 96 | 24 |
| Win rate | 51.04% | 37.50% |
| Profit factor | 1.289 | 1.000 |
| Net R | +7.98R | -0.001R |
| Average R/trade | +0.083R | -0.000R |
| Maximum drawdown | -3.80R | -4.77R |
| Maximum losing streak | 5 | 6 |
| Positive active months | 50.0% | 50.0% |

It fails the validation PF and net-R gates.

### Entry-mode comparison

| Entry mode | Training-eligible | Validation passes | Maximum validation trades |
|---|---:|---:|---:|
| Next 5m open | 51 | 0 | 33 |
| FVG midpoint retest | 0 | 0 | 5 |
| MSS midpoint retest | 12 | 0 | 13 |

Neither retest mode produced enough stable trades to pass.

### Cost sensitivity — best validation candidate with >=20 trades

| Round-trip cost | Training net R / PF | Validation net R / PF |
|---|---:|---:|
| 6bp | +14.53R / 1.583 | +1.69R / 1.220 |
| 12bp | +7.98R / 1.289 | -0.001R / 1.000 |
| 20bp | -0.75R / 0.976 | -2.25R / 0.773 |

The candidate is cost-sensitive and does not survive the 12bp primary assumption.

## Timestamp-convention audit

The older `research/liquidity_sweep_mss_intraday_backtest.py` keeps its source 15m candles on their original **open timestamps**, while its derived 1h candles are right-labelled at their close. Therefore `searchsorted(side="left")` maps a 1h pivot-confirmation close to the 15m candle that **opens** at that timestamp—the first 15m candle after the 1h confirmation. That mapping is causal; no lookahead defect is established in the older engine by this code.

The new study instead derives 15m candles with right-labelled close timestamps, so it correctly uses `searchsorted(side="right")` to skip the 15m candle that ends at the 1h confirmation timestamp. These are different timestamp conventions with consistent availability rules, not a defect in the older engine. Earlier 15m results do not need to be re-run for this specific reason.

## Next research step

1. Correct and re-run the original 15m sweep + MSS and displacement engines with strict-right pivot availability.
2. Add trade-level diagnostic outputs for the best training candidate and best validation candidate even when no validation gate passes, so month/regime details remain auditable.
3. Only after that, test a different entry family; do not optimize the inspected validation window.

No production rules changed, no live trades or execution alerts were generated, and `main` remains untouched.
