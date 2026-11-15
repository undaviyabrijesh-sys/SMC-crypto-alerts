# BTC/ETH intraday relative-momentum study — 2026-11-16

## Decision

**REJECT this short-horizon BTC/ETH relative-momentum family as tested.** None of the 36 configurations passed the training gate; none passed validation. The untouched final 15% was not evaluated. This is a two-asset study, not evidence about a broad crypto universe.

## Reproducibility

- Repository: undaviyabrijesh-sys/SMC-crypto-alerts
- Branch: ai-quant-rebuild
- Script: research/btc_eth_intraday_relative_momentum_backtest.py
- Workflow: .github/workflows/btc-eth-intraday-relative-momentum.yml
- Source archive: Delta BTC/ETH 15m traded-price data retained in workflow artifact 14111766678 from run 43589236769: https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43589236769/artifacts/14111766678
- BTC SHA-256: d2f47c4d053cd2e159977fbd2bf2c71c8fe354235b6b1eff42fae67d1861a8ca
- ETH SHA-256: b4420194cfcc6f44b3897381f63b30f9373c5290ac1234d5a4ac47c6816ae221
- Data: 70,127 aligned 15m bars per asset; 2024-11-13 23:30 UTC to 2026-11-14 11:00 UTC (last bar open); no missing or irregular aligned intervals; exact common timestamps.
- Local execution: Python backtest completed on the archived raw CSVs; 5 synthetic alignment/funding/no-lookahead/full-4h-bar tests passed. No market-performance claim is based on a GitHub Actions run for this new script.

## Frozen rules

- Decisions occur at each UTC hour, using the just-completed 15m candle.
- Lookbacks: 1h, 4h, 8h.
- Relative spread: BTC trailing return minus ETH trailing return.
- Trigger thresholds: absolute spread at least 0.25 or 0.50 percentage points.
- If spread is positive, BTC is stronger; if negative, ETH is stronger.
- Modes: (a) equal-dollar 1x long stronger / short weaker pair; (b) 1x long stronger asset only.
- Entry: next 15m open.
- Fixed holding periods: 1h, 2h, 4h; exit at the close of the final 15m bar.
- One open position per configuration; skip overlapping decisions.
- Trades crossing UTC 00:00, 08:00 or 16:00 funding boundaries are excluded. No funding cashflow is applied.
- Completed 4h EMA50/EMA200 is used for regime attribution only; it is not a signal filter.
- No stop or target is defined; R is therefore not applicable. PF is calculated from net fixed-horizon trade returns.

## Evaluation and costs

- 36 configurations: 3 lookbacks × 2 thresholds × 3 holding periods × 2 position modes.
- Chronological row split: 70% development, 15% validation, 15% untouched final holdout.
- Development ends after row 49,087 (last bar open 2026-04-09 07:15 UTC); validation ends after row 59,606 (last bar open 2026-07-27 21:00 UTC). Entire trade horizons must remain inside their sample.
- Primary assumed round-trip cost: 12 bps per traded leg; sensitivity: 6 and 20 bps. For the equal-dollar pair, the same bps is charged against total gross pair notional. Actual fee tier, separate spread/market impact and historical funding cashflows are not verified.
- Gates: development >=100 trades, PF >=1.05, positive compounded net return and >=50% positive active months; validation >=50 trades with the same PF/net/month conditions. No OOS unless both gates pass.

## Results at 12 bps

The least-bad development diagnostic was 4h lookback, 0.50pp threshold, 4h hold, equal-dollar long/short pair:

| Metric | Development | Validation |
|---|---:|---:|
| Trades | 1,121 | 156 |
| Win rate | 35.86% | 28.21% |
| Profit factor | 0.636 | 0.384 |
| Compounded net return | -61.58% | -15.10% |
| Maximum drawdown | -62.52% | -15.34% |
| Longest losing streak | 15 | 9 |
| Positive active months | 3/18 | 0/4 |

Cost sensitivity for that same configuration:

| Round-trip cost | Development net / PF | Validation net / PF |
|---|---:|---:|
| 6 bps | -24.70% / 0.877 | -6.77% / 0.655 |
| 12 bps | -61.58% / 0.636 | -15.10% / 0.384 |
| 20 bps | -84.35% / 0.425 | -25.08% / 0.200 |

The least-bad validation-only diagnostic was 1h lookback, 0.50pp threshold, 4h hold, long stronger asset only:

- Development: 692 trades, 45.52% win, PF 0.767, compounded net -61.87%, max DD -67.84%, 8-loss streak, 5/18 positive months.
- Validation: 54 trades, 31.48% win, PF 0.915, compounded net -2.67%, max DD -8.19%, 6-loss streak, 2/4 positive months.
- At 6 bps, validation was +0.53% / PF 1.042, but development was -42.21% / PF 0.867. At 20 bps, validation was -6.79% / PF 0.775. It is not eligible for selection.

Across the full matrix, 0/36 configurations had positive net return or PF > 1 in development at 12 bps; 0/36 did so in validation. At 6 bps, only one validation configuration had positive net return, but its corresponding development result failed badly. No candidate passed either gate.

For the least-bad development pair, 4h EMA regime attribution was negative in all groups: bear 579 trades / -67.35%; bull 455 / -19.93%; neutral 87 / -6.77%. Its validation bear and bull groups were also negative.

## Interpretation and limitations

- Short-horizon relative momentum between BTC and ETH did not show a robust edge under these rules. This is consistent with the previously rejected 72h/4h relative-momentum test, but the present study is a separate 1h/4h/8h lookback and 1h/2h/4h holding grid.
- Cost drag is material at hourly-to-4h horizons. Even 6 bps did not produce a development winner.
- The two-asset universe is narrow; it does not support a broad cross-sectional survivorship conclusion.
- The validation interval spans only four active calendar months; nevertheless, all 36 validation configurations failed the primary-cost profitability test.
- Funding-boundary trades were excluded rather than assigned an unverified cashflow. Spread/market impact beyond the assumed round-trip cost are not separately modelled.
- The final 15% remains untouched. It was not used for diagnostics, tuning or selection.
- No live, production, approved-strategy, main-branch, alert or exchange-order logic was changed.

## Next research step

Move to a distinct BTC-only exhaustion-to-mean-reversion hypothesis. Treat it as an EMT-inspired mechanical proxy, not a claim to reproduce any discretionary/canonical EMT definition: use prior-only volume-climax and true-range expansion, require a rejection close after a directional extension, then test a next-bar reversal entry against matched non-event controls before testing stop/target variants. Use BTC 5m traded-price data, 15m/1h completed context, chronological splits, and the same 6/12/20 bps stress grid. Do not tune the rejected relative-momentum family or inspect the untouched holdout.
