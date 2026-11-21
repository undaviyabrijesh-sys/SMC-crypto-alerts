# BTCUSDT USD-M premium/index-basis dislocation event study — preregistration 2026-11-21

## Research question

Does an extreme, prior-only standardized dislocation in BTCUSDT perpetual contract price versus the USD-M index price mean-revert more over the following 15 minutes, 1 hour and 4 hours than a matched non-event control?

This is a descriptive event study. It is not an executable strategy, trade simulation or PnL backtest.

## Prior-art and data decision

- The 2026-11-21 two-month availability audit verified contract, indexPrice, markPrice and premiumIndex archives with checksums and four-series alignment.
- Prior-art search found no historical premium/index-basis event study in the research tree. Existing funding-sentiment work uses funding-rate observations and is distinct.
- The corrected Delta OI event study is closed without an established predictive edge. No OI thresholds are reused.
- This study uses Binance USD-M public monthly archives only. Prior REST calls returned HTTP 451; no REST parity claim is made.

## Frozen dataset

- Symbol: BTCUSDT USD-M perpetual; interval 5m.
- Warmup: 2025-10-01 through 2025-10-31.
- Analysis: 2025-11-01 inclusive through 2026-11-01 exclusive (12 complete UTC months).
- Monthly archives: 2025-10 through 2026-10 inclusive.
- Four series: contract klines, indexPriceKlines, markPriceKlines and premiumIndexKlines.
- Expected rows per monthly archive: calendar days × 288.
- Verify sibling SHA-256 checksum, ZIP CRC, 12-column schema, UTC 5m grid, row count, no duplicates/gaps, monthly boundary continuity and exact four-series timestamp intersection.
- No missing bars are interpolated. A monthly archive may be repaired only when its missing timestamps form one or more complete UTC day(s); each corresponding daily archive must independently pass sibling SHA-256, ZIP CRC, exact 288-row count, exact day boundaries, no gaps/duplicates and no overlap with monthly rows. Partial-day gaps, extra timestamps, checksum/schema failures or unavailable daily patches fail the run. All monthly and daily-patch hashes are retained.

## Feature definitions

Primary dislocation:

perp_index_basis_bps = 10000 × (contract_close / index_close − 1)

Secondary corroboration, not substituted for the primary:

mark_index_premium_bps = 10000 × (mark_close / index_close − 1)

premium_index_close is retained in native units. It is not assumed to equal either price ratio.

For each 5m observation t, compute the basis z-score using only the immediately preceding 8,640 observations (30 complete days), excluding the current observation:

z_t = (basis_t − mean(basis[t−8640:t])) / std_pop(basis[t−8640:t])

Population standard deviation is used. A zero/near-zero standard deviation yields no event observation.

## Frozen event definition

- Positive-basis event: z_t >= +2.5 (perpetual rich relative to index).
- Negative-basis event: z_t <= −2.5 (perpetual cheap relative to index).
- Event is timestamped when the 5m bar closes and the value becomes observable.
- One event maximum per 4h05 (49 bars), regardless of direction. This prevents event-event overlap at the 4h horizon.
- Event must have the full 4h outcome inside its own chronological split.

No threshold, lookback, cooldown or horizon grid is permitted.

## Outcome definitions

For event side s = +1 for positive basis and s = −1 for negative basis:

signed_basis_reversion_h = −s × (basis[t+h] − basis[t])

Positive values mean the basis moved toward zero.

- Primary horizon: 1h (12 bars).
- Secondary descriptive horizons: 15m (3 bars) and 4h (48 bars).
- Secondary mark/index corroboration uses the same sign convention.
- Premium-index native-unit changes are reported separately and are not called basis PnL.

## Chronological splits

Use the 105,120 analysis bars in exact timestamp order:
- Development: first 60% (63,072 bars).
- Validation: next 20% (21,024 bars).
- OOS: final 20% (21,024 bars).

Every event and matched-control outcome must remain entirely inside its own split. No threshold, matching cutpoint or event rule is chosen using validation/OOS.

## Matched controls

For each event, select at most one non-event control from the same split and within ±24h, using the nearest eligible timestamp. A control must:
- Have the same positive/negative basis side.
- Have the same prior-24h index-return decile, with decile cutpoints computed from development only.
- Have the same prior-24h realized-volatility quartile, with quartile cutpoints computed from development only.
- Have the same fixed prior-24h regime: bear <= −0.50%, neutral between −0.50% and +0.50%, bull >= +0.50%.
- Have the complete 4h outcome inside the same split.
- Be at least 4h05 from every main event and every other selected control.
- Never be reused.

Events without an eligible control remain in the event ledger but are excluded from paired-lift calculations. Matching rules are not relaxed to increase sample size.

## Inference and decision rule

- Primary comparison: mean paired 1h signed-basis-reversion lift (event minus matched control).
- Report event mean, control mean, paired mean/median lift, event-beats-control fraction and UTC event-day cluster bootstrap 95% descriptive interval.
- Bootstrap 5,000 replicates, fixed seed namespace, resampling UTC event-day cluster means. These intervals are descriptive, not p-values and not proof of causality.
- 15m and 4h are secondary descriptive horizons; no threshold or horizon selection after viewing OOS.
- A candidate may proceed to a separately preregistered execution study only if: at least 30 matched pairs in each split at the primary horizon; positive mean paired lift in development, validation and OOS; and the OOS primary cluster-bootstrap lower bound is above zero.
- Otherwise close this exact event definition as no stable predictive edge established. Do not tune against OOS.

## Costs, funding and trading metrics

No positions, entries, stops, targets or execution are simulated. Fees, spread, slippage and funding are not applicable to this event study. Win rate, profit factor, net R, trading drawdown and losing streak are not applicable. A later executable strategy requires a separate preregistration with actual funding cashflows, fees/slippage and conservative intrabar handling.

## Reproducibility

- Implementation: research/btcusdt_premium_basis_event_study.py
- Archive parser reused from: research/binance_btcusdt_premium_basis_availability_audit.py
- Workflow: .github/workflows/btcusdt-premium-basis-event-study.yml
- Outputs: report, manifest, summary, monthly, regime, matched-pair and event CSVs under quant_discovery; full aligned feature sample and all 52 archive hashes retained in the workflow artifact.
- Branch: ai-quant-rebuild only.

No main-branch, production, alert, paper-state, exchange-order or deployment changes.


## 2026-11-21 data-integrity addendum — deterministic full-day archive repair

The first 12-month execution found the Binance USD-M indexPriceKlines monthly archive for 2026-06 contained 8,352 rows instead of 8,640, with one internal gap. The deterministic self-tests had passed, but the archive-integrity gate correctly stopped the run before any event calculations. No market-performance result was produced.

To avoid interpolating or silently dropping a day, the preregistration now permits one narrowly defined source repair: if and only if all missing timestamps for a monthly series form complete UTC day(s), download the exact corresponding daily archive(s) for that same series. Each daily patch must pass its own SHA-256 checksum, ZIP CRC, exact 288 rows, exact first/last 5m timestamps, no gaps/duplicates, and zero overlap with the monthly archive. After patching, the full month must have exactly the expected rows and a continuous 5m grid. Any partial-day gap or failed daily archive still stops the run.

This changes only deterministic data reconstruction; event threshold, lookback, cooldown, outcomes, matching, splits, bootstrap and decision gates remain frozen. The missing 2026-06 date is not inferred or manually filled; it is discovered from the archive timestamps at runtime and sourced only from the matching public daily archive.
