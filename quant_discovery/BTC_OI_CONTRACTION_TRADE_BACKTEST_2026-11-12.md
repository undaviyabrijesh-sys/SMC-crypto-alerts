# BTC OI contraction + price-impulse trade backtest — 2026-11-12

## Decision

**Reject as an intraday strategy. No validated candidate.** The raw-data primary matrix produced one training-eligible configuration and zero validation passes. A separate post-inspection outlier filter produced four apparent validation passes, but all four failed the untouched OOS segment decisively. The filtered result is diagnostic only and must not be treated as a strategy discovery.

## Hypothesis and exact rules

A sharp decrease in BTC open interest, coincident with an unusually large 1-hour traded-price move, may identify deleveraging/liquidation pressure. The tested trade hypothesis was reversal after the impulse; continuation was tested as a direction control.

- Signal uses a completed 1-hour OI candle. OI timestamp is treated as candle open; its close is available at open + 1 hour.
- OI percentage change must be negative. Its z-score must be at or below -1.5 or -2.5 versus the prior 168 hourly observations (minimum 72); current observation excluded from rolling mean/std.
- Absolute 1-hour traded-price close return must exceed its prior 168-hour rolling q90 or q95 threshold (shifted one hour).
- The 1-hour traded-price return is built from four complete BTCUSD 15-minute traded candles, not mark price.
- Signal becomes available at the OI candle close. Entry is at the next 15-minute candle open.
- Direction: continuation or reversal of the 1-hour price impulse.
- Initial stop: 1.0 or 1.5 × Wilder ATR(14) from the previous completed 15-minute candle.
- Target: 1.5R, 2R or 3R. Maximum holding period: 32 bars (8 hours).
- One position per configuration and an 8-hour global event cooldown.
- Configurations: 2 OI z-score thresholds × 2 price-return quantiles × 2 directions × 2 stop multipliers × 3 targets = 48.

## Dataset and reproducibility

Inputs were downloaded from the previously verified GitHub Actions artifacts:

- BTC OI 1h: [derivatives archive run 43118448037, artifact 13898484807](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43118448037/artifacts/13898484807)
  - 17,531 rows; 2024-11-11 12:00 UTC through 2026-11-11 22:00 UTC.
  - SHA-256: ae6b8ba594a9fd27fa1139601396aac2b4cf62f72b4679f5f7fea4394a215758
- BTCUSD traded 15m: [CRT regression run 43119326212, artifact 13900490808](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43119326212/artifacts/13900490808)
  - 70,079 rows; 2024-11-11 23:30 UTC through 2026-11-11 23:00 UTC.
  - SHA-256: a21f6fb1e90c4dbabf19bae0df1a891e9549c7ce9eb89528dd3ba1fca2de348a
- Both input series passed strict interval checks: no missing 1-hour OI intervals and no missing 15-minute traded-price intervals.
- Valid feature rows after warm-up/alignment: 17,446; first available 2024-11-15 02:00 UTC; last 2026-11-11 23:00 UTC.
- Chronological split boundaries: training through 2026-04-07 21:30 UTC; validation through 2026-07-25 22:15 UTC; OOS follows.
- Reproducible engine: research/oi_contraction_traded_backtest.py. CLI takes --oi-csv, --price-15m-csv, and --output-dir; --quality-filter runs the explicitly non-primary sensitivity.
- Six deterministic execution-order self-tests passed. Python compilation passed. The raw and filtered full matrices were executed locally against the exact archived CSVs.

## Primary result — raw data, 12bp assumed round-trip cost

**48 configurations; 1 training-eligible; 0 validation passes; OOS not evaluated.**

The only training-eligible configuration was:
- OI z-score ≤ -2.5; price impulse ≥ prior q90.
- Reversal direction.
- 1.5 ATR stop; 1.5R target.
- Training: 128 trades, 51.56% win rate, PF 1.047, +3.49R, average +0.027R, max drawdown -15.36R, maximum losing streak 7; 47.1% of active months positive.
- Matching validation: 36 trades, 50.00% win rate, PF 0.823, -3.75R, average -0.104R, max drawdown -7.26R, maximum losing streak 2; 25.0% of active months positive.

Cost sensitivity for this training-eligible configuration:

| Assumed round-trip cost | Training net R / PF | Validation net R / PF |
|---:|---:|---:|
| 6bp | +17.61R / 1.263 | +0.74R / 1.039 |
| 12bp | +3.49R / 1.047 | -3.75R / 0.823 |
| 20bp | -15.33R / 0.815 | -9.73R / 0.597 |

The result does not survive the primary 12bp cost assumption in validation. No OOS result is claimed for the raw primary run.

## Post-inspection data-quality sensitivity — not primary evidence

After observing extreme raw OI changes, a separate sensitivity excluded observations with absolute 1-hour OI percentage change above 20% or absolute 1-hour traded-price return above 5%. This filter was not preregistered and is not allowed to replace the raw primary result.

- At z≤-2.5/q95, the 8-hour cooldown event count fell from 156 raw events to 104 filtered events.
- The filtered matrix had 5 training-eligible configurations and 4 validation passes.
- All four validation-pass candidates failed OOS. At 12bp, their OOS results ranged from -14.61R to -16.53R, PF 0.338–0.396, 25–27 trades, max drawdown -16.92R to -24.40R, and maximum losing streak 7.

The best filtered validation row (z≤-2.5, q95, reversal, 1.5 ATR stop, 2R target) illustrates the instability:

| Metric | Training | Validation | OOS |
|---|---:|---:|---:|
| Trades | 53 | 26 | 25 |
| Win rate | 45.28% | 57.69% | 24.00% |
| Profit factor | 1.073 | 1.490 | 0.352 |
| Net R | +2.64R | +6.06R | -15.11R |
| Average R | +0.050R | +0.233R | -0.604R |
| Max drawdown | -8.91R | -2.38R | -18.84R |
| Losing streak | 7 | 2 | 7 |
| Positive active months | 46.2% | 75.0% | 25.0% |

Filtered candidate cost sensitivity:

| Cost | Validation net R / PF | OOS net R / PF |
|---:|---:|---:|
| 6bp | +9.25R / 1.829 | -12.09R / 0.429 |
| 12bp | +6.06R / 1.490 | -15.11R / 0.352 |
| 20bp | +1.82R / 1.128 | -19.13R / 0.270 |

OOS monthly net R for that filtered candidate: July +0.26R, August -3.61R, September -4.95R, October -6.81R. OOS regime breakdown was negative in every bucket: downtrend 7 trades/-6.57R; range 4/-0.34R; uptrend 14/-8.20R.

**Decision:** reject. Do not tune this inspected validation/OOS period.

## Data-quality and execution limitations

- Raw OI hourly percentage changes are extreme in places (BTC minimum approximately -57.8%, maximum +114.9%). The absolute OI units and exact sampling convention have not been independently reconciled. These jumps must not automatically be interpreted as liquidation events.
- Delta documents OI:<contract> as a supported historical candle symbol prefix, but the public candle reference does not establish the economic unit/contract aggregation semantics. See [Delta historical candle API documentation](https://docs.delta.exchange/).
- Funding is excluded: historical settlement timestamp/unit/sign mapping has not yet been cross-checked against event-level settlement records.
- 12bp is an assumed round-trip cost, not the user's account-specific fee tier. No separate spread model is used.
- Same-bar stop/target ambiguity resolves stop first; adverse stop gaps fill at the worse open; target gaps fill at the target; time exits use the final 15-minute close.
- The backtest uses traded BTCUSD 15-minute OHLC for signal and fills, not mark price. It remains a single-instrument research test and not a production strategy.

## Next research step

Pause parameter tuning. First reconcile the OI series against Delta's current ticker/open-interest fields and a second independent observation source, establish whether the extreme hourly jumps are genuine contract OI moves or data/aggregation artifacts, and document the unit. Only then preregister a new deleveraging study on a fresh period. Keep funding out of P&L until settlement attribution is verified.


## Fresh full-data GitHub Actions rerun — successful (2026-11-12 07:42 UTC)

- Workflow run: https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43177146399
- Reproducible inputs and outputs artifact: https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43177146399/artifacts/13924985913
- The workflow downloaded fresh two-year inputs, ran the raw primary matrix and post-inspection sensitivity, generated the summary, and successfully uploaded all 14 files. The initial attempt had an artifact-name escaping error; the workflow interpolation was corrected and this rerun passed.
- Fresh BTC OI 1h: 17,531 rows, 2024-11-11 20:00 UTC to 2026-11-12 06:00 UTC, SHA-256 c4f85f738b55bdc316e4c0745b0093e9f45a3a00658c3baab550836314659609.
- Fresh BTCUSD traded 15m: 70,127 rows, 2024-11-11 19:45 UTC to 2026-11-12 07:15 UTC, SHA-256 3934aadf4b36704cf26c21de9a887a674716e4d87fc28a4fa992ba526f3ff6ac.
- Valid feature rows: 17,458; first available 2024-11-14 22:00 UTC; last 2026-11-12 07:00 UTC. Train boundary 2026-04-08 01:54 UTC; validation boundary 2026-07-26 04:27 UTC.
- Results were unchanged: raw primary 1 training-eligible, 0 validation passes; raw candidate train 128 trades/+3.49R/PF1.047 and validation 36 trades/-3.75R/PF0.823. OOS was not evaluated for the raw primary.
- The post-inspection filter still yielded 5 training-eligible and 4 validation-pass candidates; all four failed OOS at 12bp, -14.61R to -16.53R with PF 0.338–0.396. No strategy promoted.
- Deterministic quant CI passed on the same corrected branch commit.
- Delta's official ticker schema distinguishes oi (number of outstanding contracts), oi_value (base-currency value), and oi_value_usd. The historical OI:BTCUSD candle series has not yet been mapped to one of these ticker measures. Next step is a timestamp-aligned live ticker vs last-closed historical OI candle reconciliation, not more parameter tuning.
