# Salty Quant Supervisor Handoff — 2026-11-06 14:50 IST

## Exact repository state

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Code fix: `f5de412420126614b035655ca4ef86092fc1bb9a` — bind visual audit cycle IDs to exact chart image hashes.
- Regression tests: `9ccee9b22a1d737f68d9b32297f5daf60b0f9c7f` — test image-sensitive cycle identity and mismatched evidence sets.
- Current branch head before this handoff document: `9ccee9b22a1d737f68d9b32297f5daf60b0f9c7f`.
- PR #1: open, draft, unmerged; 418 commits, 77 changed files; head `9ccee9b`, base `main`.
- Compare: 418 ahead / 0 behind. Main remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- No submitted PR reviews or review threads.
- Branch-protection endpoint returned HTTP 403 `Resource not accessible by integration`; protection state was not independently verified in this pass.

## Bug found and fixed

The visual chart renderer embeds the run timestamp in each image title. Before this fix, `cycle_id` was derived only from candle watermarks. A retry on unchanged candles could therefore create different PNG bytes under the same cycle ID and overwrite the earlier chart artifact, while the earlier decision/error log still referenced the previous image hash.

Fix:
- Added `_visual_cycle_id(chart_watermarks, chart_hashes)`.
- Cycle identity now hashes both the sorted closed-candle watermarks and the sorted SHA-256 image hashes.
- Mismatched/empty symbol sets fail closed.
- The visual worker uses this identity before persisting images or calling the analyst.
- Added tests proving a changed PNG hash on identical candle watermarks yields a different cycle ID, identical evidence is deterministic, and mismatched symbol sets are rejected.

This preserves each distinct rendered attempt's chart evidence instead of allowing retries to overwrite it.

## Exact-head CI

Both required code/test workflows passed on `9ccee9b22a1d737f68d9b32297f5daf60b0f9c7f`:

- Push CI [42194245334](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42194245334): success.
- PR CI [42194251933](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42194251933): success.

The PR job log explicitly passed:
- `test_visual_cycle_id_changes_when_chart_image_changes_on_same_candles`
- `test_visual_cycle_id_rejects_mismatched_chart_evidence_sets`
- the remaining `test_visual_first.py` checks and all CI test groups.
- live public Delta closed-candle/freshness checks and derivatives-history probes.

The PR CI artifact list was empty because CI does not invoke the visual worker. This is expected; it is not evidence of a visual cycle.

## Fresh feed evidence — PR CI at 2026-11-06 09:20:37 UTC (14:50:37 IST)

All 18/18 instrument/timeframe checks passed for BTCUSD, ETHUSD and XAUTUSD across 5m, 15m, 1h, 4h, 1d and 1w.

Latest 5m closed-price snapshots:
- BTC: 76,165.00
- ETH: 2,243.60
- XAUT: 4,071.67

Other available closed-candle snapshots:
- BTC 15m 76,092.50; 1h 75,640.00; 4h 75,569.50; 1d 76,050.50; 1w 78,313.50.
- ETH 15m 2,240.35; 1h 2,225.55; 4h 2,227.55; 1d 2,236.95; 1w 2,274.30.
- XAUT 15m 4,072.66; 1h 4,069.01; 4h 4,047.27; 1d 4,077.36; 1w 3,899.49.

Derivatives-history probe:
- Funding: BTC 66, ETH 66, XAUT 70 hourly candles.
- Mark price: 864 five-minute candles per instrument.
- Open interest: 72 hourly candles per instrument.
- Availability does not prove funding settlement attribution or executable costs; funding remains excluded from validated strategy P&L.

BTC 5m historical bootstrap pilot: 1,051 candles, 100.0% coverage, zero gaps. SHA-256 prefix `924d1ea981fd`.

XAUT weekly history remains only 29 candles; Gold long-horizon inference is weak.

These are CI-time snapshots, not current market quotes or trade recommendations.

## Visual-first pipeline and execution controls

- Raw six-panel chart input: 1w, 1d, 4h, 1h, 15m, 5m.
- Independent candidates: SMC/market structure, visual supply-demand, liquidity sweeps/reclaims, support/resistance, trend pullbacks, momentum, breakout/retest, volatility expansion, range rejection/mean reversion, and other evidence-supported behaviour.
- The model selects at most one immediately actionable candidate or `NO_TRADE`. No coded DNS/zone/market-structure engine selects, ranks or substitutes a trade.
- Mechanical gates remain unchanged: confidence >=75; quality >=75; R:R >=2.0; stop 0.35–2.5 trigger-timeframe ATR; entry-zone deviation <=0.35%; at least two distinct evidence timeframes including trigger; fresh candle watermarks; MARKET entry only; one open/pending paper position per symbol; similarly strong opposing candidates fail closed with the existing 8-point quality margin.
- Discord visual alerts remain execution-focused, include entry band, entry, stop, target, R:R, trigger, context, rationale, invalidation, evidence/conflicts and cancellation conditions; messages above 1,900 characters are refused rather than truncated.
- No WATCH/status messages are emitted by the visual lane.

## Real visual / AI / Discord status

- No `workflow_dispatch` run was found on `ai-quant-rebuild`.
- No fresh multi-timeframe chart bundle or visual artifact was available to inspect.
- No actual OpenAI vision response, selected live-paper setup, or Discord webhook delivery was verified.
- Last recorded real OpenAI blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested in this pass.
- Manual visual-paper dispatch requires `lane=visual` and `confirm_visual_paper=true`. Scheduled workflow is gated by `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; the scheduled path runs AI-free Quant Discovery, not visual analysis.
- Chart PNGs and their manifest are persisted under `visual_artifacts/<cycle_id>/` and uploaded with 14-day retention on an actual visual workflow run. No such run occurred here.

## Signal lifecycle and state

- Closed 5m candles only; same-candle TP/SL ambiguity resolves SL-first.
- Data gaps leave outcomes unresolved rather than fabricating the first exit.
- TIME exit requires the full contiguous eligible candle window.
- TP, SL and TIME are separate outcome messages; failed delivery is queued for retry.
- Reported lifecycle P&L is gross before fees, spread, slippage and funding.
- Local state writes are atomic, but cross-run GitHub Actions cache is evictable; there is no durable database guarantee.

## Quant Discovery — research only

- `quant_supervisor.APPROVED_STRATEGIES = frozenset()`; no candidate can reach deterministic execution alerts.
- EXP-001: all 30 baseline OOS cells negative at 10 bps round-trip plus the stated funding stress; all 270 stop/target variants negative. Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, seven consecutive losses.
- OI/volatility screen: BTC best row negative (-0.0313R, 45 trades); ETH best row +0.0493R over 67 trades but train/validation negative and 20 bps stress -0.0640R; XAUT +0.2863R over only 14 OOS trades but train/validation negative and 20 bps stress -0.0305R. All rejected.
- Historical spread/depth, executable market impact and funding settlement attribution remain incomplete. Do not promote candidates or describe them as edges.

## Legacy main workflow — still active

- Latest observed default-branch scheduled run: [42189082666](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42189082666), 2026-11-06 08:38:02 UTC (14:08 IST), success on main SHA `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- Its job steps confirm `python main.py`.
- Main `.github/workflows/alerts.yml` remains scheduled every 10 minutes and passes legacy WATCH/TRIGGER webhook configuration.
- A successful run does not prove Discord delivery. This is separate from the PR's visual-first paper workflow. Do not modify/disable main or cut over without explicit owner authorization.

## Next steps

1. Re-check the live branch and PR head after this handoff commit.
2. Confirm the handoff-only commit's CI status; code/test head `9ccee9b` already passed both Push and PR CI.
3. Restore usable OpenAI quota, then run exactly one explicitly confirmed visual-paper cycle.
4. Inspect the uploaded raw chart PNGs and manifest; verify image hashes, six timeframe watermarks, model candidate comparison, risk validation and actual Discord delivery.
5. Track any emitted paper signal through a confirmed TP/SL/TIME update.
6. Resolve legacy-main workflow cutover only with owner authorization.
7. Continue pre-registered chronological OOS/walk-forward research; do not promote any unvalidated candidate.

## Safety

No main changes, PR merge, deployment, secret changes, schedule activation, workflow dispatch, live trading, exchange orders or risk-threshold reductions were performed in this supervision pass.
