# BTC previous-week range sweep → 1H reclaim → 15M MSS — Results (2026-11-17)

## Decision

**INSUFFICIENT SAMPLE — DO NOT PROMOTE.** The frozen primary 2R setup produced only 15 development trades and 2 validation trades. Development net expectancy was slightly negative at the 10 bps public-base taker/taker assumption. Validation's +0.52R is only two trades and cannot establish an edge. The final 15% OOS sample was not loaded into the feature pipeline and was not evaluated.

## Preregistration and source

- Frozen rules: [preregistration](BTC_PREV_WEEK_RANGE_SWEEP_MSS_PREREGISTRATION_2026-11-17.md).
- Source data: Delta BTCUSD perpetual traded-price 5m archive, workflow [43857702736](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43857702736), artifact [14221154137](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43857702736/artifacts/14221154137).
- The local implementation and complete CSV/metadata outputs are included in the accompanying research ZIP. No new GitHub Actions market run is claimed; this was a local rerun against the downloaded, previously archived source artifact.

## Data and chronology

- 210,239 valid 5m rows, 2024-11-16 11:30 UTC through 2026-11-16 11:20 UTC; 334 zero-volume rows, no duplicate timestamps and no missing 5m intervals.
- Raw CSV byte SHA-256: `5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb`.
- Features were constructed only from the first 178,703 rows, ending 2026-07-29 23:20 UTC. The final 31,536 rows (15%) were not loaded into the feature pipeline.
- Evaluated prefix: 59,567 complete 15m, 14,891 complete 1h and 3,722 complete 4h bars; 88 complete prior UTC weeks.
- Split: development 147,167 rows (70%); validation 31,536 rows (15%); OOS 31,536 rows reserved and untouched.

## Frozen method

A complete prior UTC week is Monday 00:00 to the next Monday 00:00, exactly 2,016 contiguous 5m bars. A completed 1h candle must sweep its prior-week high/low by at least 0.10 prior 1h ATR(14) and close back inside. Only the first qualifying attempt per side per week is allowed. After the 1h close, a 15m close must break the most recent pre-sweep confirmed 2-left/2-right swing within eight 15m bars. Entry is the next 15m open, provided it remains beyond the swept boundary. Stop is beyond the 1h sweep extreme by 0.10 prior 1h ATR; risk above 2.5 ATR is skipped. Targets are 1.5R, 2R (primary) and 3R. One position globally per target configuration. Maximum hold is eight hours, capped at the last completed 15m close before the next UTC 00:00/08:00/16:00 funding boundary.

Same-bar stop/target is stop-first; stop gaps fill at the worse open; target gaps fill at target. A missing 15m bar before first exit is unresolved. Funding cashflows are excluded; separate spread, slippage and market impact are not modelled.

## Results at 10 bps round-trip cost

Win rate is based on positive net R after fees. Drawdown is sequential trade-R drawdown assuming constant initial risk per trade, not a rupee account simulation.

| Target | Sample | Trades | Win rate | PF | Gross R | Net R | Max DD | Max loss streak | Positive months |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.5R | Development | 15 | 53.33% | 0.849 | +2.357 | -0.695 | -2.255 | 2 | 6/11 |
| 1.5R | Validation | 2 | 50.00% | 1.017 | +0.500 | +0.020 | -1.179 | 1 | 1/2 |
| **2R (primary)** | **Development** | **15** | **53.33%** | **0.957** | **+2.857** | **-0.195** | **-2.255** | **2** | **6/11** |
| **2R (primary)** | **Validation** | **2** | **50.00%** | **1.441** | **+1.000** | **+0.520** | **-1.179** | **1** | **1/2** |
| 3R | Development | 15 | 53.33% | 0.871 | +2.462 | -0.590 | -2.255 | 2 | 6/11 |
| 3R | Validation | 2 | 50.00% | 1.094 | +0.591 | +0.111 | -1.179 | 1 | 1/2 |

### Primary 2R cost sensitivity

| Round-trip cost | Development net R / PF | Validation net R / PF |
|---:|---:|---:|
| 4 bps | +1.636 / 1.463 | +0.808 / 1.754 |
| 7 bps | +0.721 / 1.177 | +0.664 / 1.590 |
| 10 bps | -0.195 / 0.957 | +0.520 / 1.441 |
| 20 bps | -3.247 / 0.509 | +0.040 / 1.030 |

Development does not survive the 10 bps base taker/taker fee assumption. Validation values are only two observations.

## Primary 2R diagnostics at 10 bps

- Development: 15 trades; 12 time exits, 2 SL and 1 TP; no unresolved paths; average hold 3.18h.
- Validation: 2 trades; 1 SL and 1 TP; no unresolved paths; average hold 3.38h.
- Development side split: 11 longs, +1.449R (PF 1.545); 4 shorts, -1.644R (PF 0.148). Validation contains only two shorts. This post-hoc contrast is not a basis for selecting a long-only strategy.
- Development regimes: bear 8 trades / +1.605R; bull 2 / +0.100R; mixed 4 / -1.386R; unknown 1 / -0.515R. Validation has only one bull and one mixed trade. No regime conclusion is supportable.
- Positive active months: development 6/11; validation 1/2. The denominators are too small for stability claims.

## Gate and tests

Development required at least 30 trades; 15 were observed. Validation required at least 12; 2 were observed. The primary 2R development net R was negative and PF below 1 at 10 bps. Neither gate passed, so OOS remains sealed.

Nine deterministic test groups passed: complete/incomplete UTC-week handling; pivot availability only after both right bars close; one attempt per side per week; funding-boundary-safe exits; same-bar stop-first; unresolved gap handling; future-week price perturbation invariance for prior-week levels; sample-boundary isolation; and full script compilation/execution.

## Limitations and decision

Only BTC was tested. Public base fees are assumptions, not the user's authenticated tier. Funding cashflows remain excluded; the time cap prevents crossing the next scheduled settlement. 15m OHLC cannot reveal all intrabar paths. No separate spread/slippage/impact model exists. The validation PF is not meaningful at n=2.

**Final decision: INSUFFICIENT SAMPLE / REJECT FOR PROMOTION.** Do not inspect OOS or tune this validation period. No production, main-branch, approved-strategy, live-alert or exchange-order changes were made.

## Next step

Move to a distinct family rather than tuning the underpowered weekly sweep. The next preregistration is a 1h volatility-compression release with 15m close-confirmed continuation. No result is claimed for that hypothesis yet.
