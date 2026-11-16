# BTC Previous-Week Range Sweep → 1H Reclaim → 15M MSS — Preregistration (2026-11-17)

## Status and scope
- New, price-only BTCUSD perpetual hypothesis. This is not a duplicate of the prior-day breakout/retest or 1H/15M internal-liquidity sweep studies: the external reference is a fully completed prior UTC week, the sweep/reclaim is confirmed on 1H, and entry requires a pre-existing 15M swing break.
- Research only on `ai-quant-rebuild`. Do not modify `main`, production rules, `APPROVED_STRATEGIES`, live alerts or exchange-order code.
- No parameter tuning on validation. Do not evaluate the final 15% unless one frozen target passes both chronological gates.

## Dataset and timeframe construction
- Source: archived Delta Exchange India BTCUSD perpetual traded-price 5m OHLCV.
- Use the exact archived source CSV and record its SHA-256, row count, UTC range, duplicates, malformed bars, zero-volume rows and gaps.
- Derive 15m and 1h candles only from exactly contiguous complete groups of 3 and 12 source 5m bars. Do not interpolate or carry features across gaps.
- Prior-week reference: Monday 00:00 UTC through the following Monday 00:00 UTC, requiring exactly 2,016 contiguous 5m bars. A current week without a fully observed preceding week is ineligible.
- Timeframes: weekly external range; 1h sweep/reclaim; 15m MSS and execution.

## Frozen signal rules
1. For each eligible UTC week, freeze the previous completed week's high and low. These levels never change during the current week.
2. Calculate Wilder ATR(14) on contiguous 1h bars; expose only the prior completed 1h ATR to a sweep candle.
3. Bullish sweep: a completed 1h candle trades below prior-week low by at least 0.10 × prior 1h ATR and closes back above the prior-week low. Bearish sweep is the exact mirror above prior-week high. If one 1h candle qualifies as both directions, reject it as ambiguous.
4. Allow at most one first qualifying sweep attempt per direction per UTC week. If that first sweep does not produce MSS within the allowed window, do not take a later same-direction sweep that week.
5. Before the sweep hour begins, identify the most recent confirmed 15m swing high (for bullish MSS) or swing low (for bearish MSS), using strict 2-left/2-right pivots. A pivot is usable only after both right-side bars have closed before the sweep hour starts. If none exists, the attempt fails.
6. After the 1h sweep candle closes, wait up to eight completed 15m bars. Bullish MSS requires a 15m close above the pre-sweep confirmed swing high; bearish MSS requires a close below the pre-sweep confirmed swing low. No wick-only breaks.
7. Enter at the next 15m candle open. Cancel if that open is back inside the prior-week range on the wrong side of the swept boundary.
8. Stop: beyond the 1h sweep extreme by 0.10 × prior 1h ATR. Skip if stop is on the wrong side or risk exceeds 2.5 × prior 1h ATR.
9. Fixed target diagnostics: 1.5R, 2R and 3R. Maximum holding time is eight hours, but exit earlier at the last completed 15m close before the next scheduled UTC funding boundary (00:00, 08:00 or 16:00 UTC). This avoids crossing a funding settlement while historical funding cashflow alignment remains unresolved.
10. One open trade globally at a time per target configuration; no overlapping positions. One attempt per direction per weekly level. A trade's full maximum holding window must remain within its chronological sample; otherwise it is excluded.

## Execution and costs
- Same 15m candle touching stop and target: stop first.
- Stop gap: fill at the worse opening price. Target gap: fill at target price.
- A missing 15m bar before first exit makes the path unresolved; exclude it and reserve the full maximum holding window before the next trade.
- Apply round-trip costs on entry plus exit notionals, expressed in R. Test 4/7/10/20 bps; primary public-base taker/taker assumption is 10 bps. These are public base-fee assumptions, not the user's authenticated tier.
- Funding cashflows are excluded. No separate spread, slippage or market-impact model is claimed; state this limitation prominently.

## Chronological design and gates
- Split source 5m rows chronologically 70% development / 15% validation / 15% untouched OOS. Do not compute OOS metrics or inspect OOS trade outcomes unless a frozen target passes both earlier gates.
- Primary target: 2R. 1.5R and 3R are predeclared diagnostics, not candidates for post-hoc selection.
- Development gate: at least 30 trades, positive net R at 10 bps, PF >= 1.05, max drawdown no worse than -20R, and at least 50% positive active months.
- Validation gate: at least 12 trades, positive net R at 10 bps, PF >= 1.05, max drawdown no worse than -10R, and at least 50% positive active months.
- OOS remains sealed if the primary 2R configuration fails either gate. Do not tune the failed validation period or promote side/regime subsets selected after seeing results.

## Required outputs
- Source manifest with exact SHA-256 and coverage diagnostics.
- Deterministic synthetic tests for week-boundary completeness, prior-week-level causality, pivot confirmation timing, no-lookahead under future-data perturbation, one-attempt-per-side-per-week, stop/target ordering, funding-boundary time exit, split isolation and gap handling.
- Candidate and trade ledgers; 1.5R/2R/3R summary at 4/7/10/20 bps; monthly, long/short and completed-4H-regime diagnostics; cost and data-quality report.
- Metrics: trade count, win rate, PF, gross/net R, max drawdown, longest losing streak, average/median R, positive active months, side/regime splits and holding time. Report R-based results; no unsupported annualized return.
- Final decision: ACCEPT FOR FURTHER OOS REVIEW, REJECT, or INSUFFICIENT SAMPLE. A passing development/validation result authorizes only a separately documented OOS review, not production promotion.

## Research discipline
- Preserve this preregistration and all prior findings.
- Do not claim a workflow or test completed unless it ran and its output artifact was inspected.
- No production, main-branch, live-alert or exchange-order changes.
