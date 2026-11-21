# BTC 1H volatility-compression release → 15M retest continuation — Preregistration (2026-11-17)

## Scope
A distinct BTC intraday hypothesis. It tests a volatility squeeze followed by a higher-timeframe range release and a 15m retest, not a generic Donchian breakout or the previous-week sweep setup. Research-only on `ai-quant-rebuild`; no main, production, approved-strategy, alert or exchange-order changes.

## Data and construction
- Delta BTCUSD perpetual traded-price 5m OHLCV, same frozen two-year archive where possible.
- Build only complete contiguous 15m and 1h bars from 3 and 12 consecutive 5m bars. No gap filling.
- Chronological 70/15/15 development/validation/OOS split. OOS remains sealed unless both earlier gates pass.
- All indicators use completed bars and prior-only thresholds.

## Frozen signal
1. Compute 1h Bollinger bandwidth using 20 completed 1h closes and 2 standard deviations: (upper-lower)/middle.
2. A compression is present only if the previous completed 1h bandwidth is at or below the 20th percentile of the preceding 100 completed bandwidth observations. Require at least 80 valid prior observations; do not include the current or future bandwidth in the quantile.
3. On the next completed 1h bar, require a close above the prior 20 completed 1h highs or below the prior 20 completed 1h lows by at least 0.05 prior 1h ATR(14). The 20-bar range and ATR are shifted; the breakout candle cannot define its own threshold.
4. Within the next eight completed 15m bars, require a retest within 0.15 prior 15m ATR(14) of the broken range level and a close back on the breakout side in the directional half of the candle.
5. Enter at the next 15m open. Cancel if that open has returned through the broken level. One attempt per direction per compression-release event; no repeated entries from the same hourly breakout.
6. Stop beyond the 15m retest extreme by 0.10 prior 15m ATR. Skip risk above 2.5 prior 15m ATR.
7. Fixed target diagnostics: 1.5R, 2R (primary) and 3R. Maximum hold four hours; exit earlier at the last completed 15m close before the next scheduled UTC funding boundary.
8. One open trade globally per target configuration. Full permitted holding horizon must remain inside the chronological sample.

## Execution and costs
- Same-bar stop/target: stop first.
- Stop gap: worse open; target gap: target.
- A missing 15m bar before first exit is unresolved and reserves the planned horizon.
- Round-trip cost sensitivities: 4/7/10/20 bps, with 10 bps primary public-base taker/taker assumption. Apply costs to entry plus exit notionals.
- Funding cashflows excluded until historical rate-to-settlement mapping is verified. Spread, slippage and market impact must be disclosed as unmodelled if no defensible data is available.

## Gates
- Development: at least 30 trades, positive net R at 10 bps, PF >=1.05, max DD no worse than -20R, and >=50% positive active months.
- Validation: at least 12 trades, positive net R at 10 bps, PF >=1.05, max DD no worse than -10R, and >=50% positive active months.
- 2R is the primary target; 1.5R and 3R are diagnostics, not post-hoc alternatives.
- Do not compute OOS outcomes unless the frozen 2R configuration passes both gates. No validation tuning or post-hoc side/regime selection.

## Deliverables
Source hash/coverage, deterministic tests for rolling quantile causality, compression lookback, shifted range/ATR, retest timing, no-lookahead perturbation, gap handling, same-bar ordering and split isolation; candidate/trade CSVs; cost, monthly, side and completed-4h-regime summaries; and a written ACCEPT/REJECT/INSUFFICIENT SAMPLE decision.

No test result is claimed until execution completes and artifacts are inspected.
