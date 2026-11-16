# BTC EMT-inspired exhaustion/rejection event study — completed 2026-11-16

## Decision

**Reject this frozen event definition as a tradable candidate.** The event has a positive relative lift versus matched controls in both development and validation, with positive day-cluster bootstrap lower bounds. However, its absolute development forward returns are negative after the primary 12 bps assumed round-trip cost, and only 5 of 17 active development months are positive. Validation is positive at 12 bps but contains only 32 events across four active months. Neither horizon passes the preregistered development and validation gates. The final 15% remains untouched.

This is an event study, not a stop-defined trading system. R is not applicable. The event-sequence drawdown and profit factor below are descriptive forward-return statistics, not account-equity performance.

## Reproducibility

- Repository: \`undaviyabrijesh-sys/SMC-crypto-alerts\`
- Branch: \`ai-quant-rebuild\`
- Code: [\`research/btc_emt_exhaustion_event_study.py\`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/blob/ai-quant-rebuild/research/btc_emt_exhaustion_event_study.py)
- Workflow: [run 43798634857](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43798634857)
- Artifact: [BTC EMT event-study outputs](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43798634857/artifacts/14196170242)
- Workflow conclusion: success. Python compilation and deterministic synthetic tests passed; historical download, event study, summary publication and artifact upload all completed.
- Artifact SHA-256: \`35cbb7b1bbbb32acff0e62d29ca469022608e1e02fc9ab4058aa83b164f4199f\`

## Dataset

- Instrument: Delta Exchange India BTCUSD perpetual, traded-price OHLCV.
- Timeframe: native 5-minute candles; completed 1-hour returns for the extension threshold; completed 4-hour EMA50/EMA200 regime for matching.
- Coverage: 2024-11-16 03:35 UTC to 2026-11-16 03:25 UTC.
- Source rows: 210,240; valid closed rows: 210,239.
- Duplicates: 0; invalid timestamps/OHLC/shape: 0; missing volume: 0; zero-volume candles: 334; 5-minute gaps: 0.
- Normalized-data SHA-256: \`582045dbe1397ff05c09b308245e2dc3590799050a79d0a5af9923e2ba9eeb7b\`.

## Frozen event definition

1. The prior 12 completed 5-minute closes have a signed return whose absolute value exceeds the prior-only rolling 30-day 90th percentile of completed 1-hour absolute returns (minimum 200 hourly observations).
2. Current 5-minute volume is at or above the prior-only 30-day 95th percentile for the same UTC 5-minute time-of-day bucket (minimum 20 observations).
3. Current true range is at least 1.5 times the median of the previous 20 completed 5-minute true ranges.
4. After an upward extension, upper wick is at least 40% of range and close location is in the lower 40%; after a downward extension, lower wick is at least 40% and close location is in the upper 40%.
5. The next completed 5-minute candle closes in the reversal direction and beyond the exhaustion-candle midpoint. Entry reference is the following 5-minute open.
6. One global event stream, one position at a time, and an 8-hour timestamp-based cooldown across directions.

The implementation resets rolling structure/true-range windows at data gaps and does not fill missing candles. No stop or target is applied in this first-stage study.

## Matching and evaluation

- Chronological split by valid 5-minute row index: 70% development, 15% validation, final 15% untouched.
- Both 1-hour and 4-hour forward outcomes must finish inside their sample and cannot cross a gap. This is a conservative common event sample for the two horizons.
- Controls are non-event 5-minute entries with direction contrarian to the prior 12-bar return.
- 1:1 matching without replacement by exact UTC date, direction, completed 4-hour EMA50/EMA200 regime and 3-hour UTC time bucket. Controls within ±30 minutes of confirmed event entries in the same sample are excluded. Nearest timestamp wins; ties go to the earlier control.
- Paired confidence intervals: 2,000-replicate UTC-day cluster bootstrap, seed 20261116.
- Round-trip cost assumptions: 6/12/20 bps. Primary gate: 12 bps.
- Funding excluded because historical cashflow mapping remains unverified. Separate spread/slippage/market-impact modelling is not included; flat costs are assumptions.

## Results

All figures below are descriptive forward-return event statistics. Net mean is directional forward return less the assumed round-trip cost. Event-sequence drawdown is cumulative net basis points across events, not account drawdown.

| Sample | Horizon | Events / matched pairs | Win rate at 12bp | PF at 12bp | Mean net bps | Median net bps | Event-sequence max DD bps | Max loss streak | Positive active months |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Development | 1h | 153 / 153 | 42.48% | 0.652 | -10.684 | -10.510 | -2,034.58 | 9 | 5 / 17 |
| Development | 4h | 153 / 153 | 44.44% | 0.708 | -15.685 | -12.192 | -2,440.92 | 7 | 5 / 17 |
| Validation | 1h | 32 / 32 | 50.00% | 1.160 | +2.622 | -2.016 | -150.06 | 4 | 2 / 4 |
| Validation | 4h | 32 / 32 | 50.00% | 1.472 | +16.185 | -3.932 | -261.91 | 2 | 2 / 4 |

### Matched-control lift

| Sample | Horizon | Event gross mean | Control gross mean | Paired lift | 95% day-cluster CI |
|---|---:|---:|---:|---:|---:|
| Development | 1h | +1.316 bps | -51.891 bps | +53.207 bps | [+41.100, +65.555] |
| Development | 4h | -3.685 bps | -52.169 bps | +48.484 bps | [+34.515, +62.213] |
| Validation | 1h | +14.622 bps | -22.721 bps | +37.343 bps | [+18.923, +55.805] |
| Validation | 4h | +28.185 bps | -13.922 bps | +42.107 bps | [+22.093, +64.826] |

The event outperforms this matched control sample, but positive relative lift is not sufficient: the absolute development event return does not cover costs.

### Cost sensitivity

| Sample | Horizon | Net mean at 6bp | Net mean at 12bp | Net mean at 20bp |
|---|---:|---:|---:|---:|
| Development | 1h | -4.684 bps | -10.684 bps | -18.684 bps |
| Development | 4h | -9.685 bps | -15.685 bps | -23.685 bps |
| Validation | 1h | +8.622 bps | +2.622 bps | -5.378 bps |
| Validation | 4h | +22.185 bps | +16.185 bps | +8.185 bps |

### Side and regime diagnostics

Development results at 12 bps were negative across all three 4-hour regimes for both horizons. The weakest contribution was short-side events following upward extensions. Long-side results were mixed, with the 4-hour bear-regime subgroup positive, but this is a post-hoc subgroup diagnostic, not a separately validated strategy. Validation subgroup results are small and must not be used to select parameters or directions.

## Frozen gate outcome

Neither horizon passes both samples:

- Event and matched-pair count thresholds were met: development 153/153; validation 32/32.
- Mean paired lift was positive and its 95% day-cluster lower bound was above zero in both samples.
- Validation absolute net mean was positive at 12 bps for both horizons.
- **Development absolute net mean was negative for both horizons.**
- **Only 5/17 active development months were positive (29.4%), below the 50% requirement.**

Therefore: \`any_horizon_passes_both_gates = false\`. No OOS result was evaluated.

## Next research step

Do not tune the inspected validation sample and do not proceed to the stop/target grid for this event definition. Move to a distinct, independently preregistered BTC intraday hypothesis (for example, VWAP deviation/reclaim or range-break retest), retaining the untouched 15% and the same cost, chronology and no-lookahead discipline. The current EMT event definition is rejected as tested.

No production rules, approved strategies, live alerts, exchange orders or \`main\` branch were changed.
