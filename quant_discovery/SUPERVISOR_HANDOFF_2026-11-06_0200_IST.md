# Salty Quant Supervisor Handoff — 2026-11-06 02:00 IST

## Exact GitHub checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Code/test head immediately before this handoff: [`a0a0671`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/a0a0671e005ad8771457626d0fbcf59ad21fc0f7).
- PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1): open, draft, unmerged; base `main`; mergeable at last full PR fetch.
- Compare before this handoff: 355 commits ahead, 0 behind. Base/main SHA: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- This documentation commit is the next commit after `a0a0671`; re-fetch branch and PR before any later write.
- No main modification, PR merge, deployment, secret change, live trading, order or schedule activation was performed.

## Changes and exact-head CI

- [`417b7df`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/417b7df27a278e681bb26f1cbeba804d0fff93d7) changes the Discord outcome label from ambiguous “Paper P&L” to “Gross paper P&L (before fees, spread, slippage and funding)”. The stored outcome fields are `gross_pnl_pct` and `gross_R`; costs are not deducted from these values.
- [`a0a0671`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/a0a0671e005ad8771457626d0fbcf59ad21fc0f7) places the regression test before the test runner's `__main__` guard, so `python test_visual_pipeline.py` actually executes it.
- Exact-head push CI [42103734197](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42103734197) — success.
- Exact-head PR CI [42103746261](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42103746261) — success.
- The PR job log explicitly contains `PASS test_discord_outcome_alert_labels_gross_pnl_before_costs`.
- The derivatives-history archive workflow was skipped by its commit-message/manual-dispatch guard; this was not a failure.

## Latest data-feed evidence

Push CI run [42103734197](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42103734197) completed at 2026-11-05 20:29 UTC and ran live public Delta smoke checks:

- 18/18 closed-candle/freshness checks passed for BTCUSD, ETHUSD and XAUTUSD across 5m, 15m, 1h, 4h, 1d and 1w.
- Snapshot 5m closes at that probe (historical observations, not current quotes): BTC 76,127.0; ETH 2,250.1; XAUT 4,098.09.
- Three-day derivatives probe: 69 hourly funding observations per contract; 864 five-minute mark-price candles per contract; 72 hourly open-interest candles per contract. Availability does not establish correct funding settlement attribution or units.
- BTC 5m historical archive pilot: 1,051 candles, 100% coverage, zero gaps in that pilot window only.
- CI artifact listing for the PR run was empty. No raw/annotated market chart or actual model decision was available to inspect.

## Visual chart-to-AI architecture — still not compliant with requested design

- `worker.py` defaults to `WORKER_MODE=quant`; this path calls the AI-free `quant_worker.py`.
- The branch `.github/workflows/alerts.yml` directly invokes `quant_worker.py` and gates its scheduled job on `ENABLE_GITHUB_SCHEDULE`. This branch workflow is not the active default-branch schedule.
- `WORKER_MODE=dns` calls `dns_worker.py`: it refreshes AI-authored maps infrequently, then the coded local sweep/reclaim detector creates candidates. Optional Bull/Bear/Chief review is disabled by default and only runs after that coded trigger.
- `ai_analyst.py` reads six-timeframe chart images, but its prompt forces demand/supply as the primary framework. Every actionable trade must overlap a directional quality >=3 DNS band; trend, momentum, breakout, volatility and mean-reversion are only confirmations/refinements at DNS. The test `test_visual_analyst_compares_multiple_setup_families` explicitly asserts “demand and supply first”.
- Therefore, neither the default quant worker nor the DNS lane satisfies the requested visual-first independent candidate comparison on every new closed-candle cycle. Do not patch only the prompt: the response schema, validators, risk gate and worker orchestration currently assume DNS fields and need a versioned coordinated redesign.
- Do not restore `zones.py` / `score.py` as decision-makers. The vision model should compare independent evidence-supported candidates from fresh multi-timeframe images, select one candidate or `NO_TRADE`, and then pass the chosen plan through unchanged mechanical safety gates.
- Last documented real Responses API attempt returned HTTP 429 `insufficient_quota / credit_balance_exhausted`. This run did not test or change API credentials/quota.

## Legacy default-branch workflow — owner decision remains unresolved

- `main` remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- Main's `.github/workflows/alerts.yml` is still configured for `*/10 * * * *` and runs `python main.py`; main's `main.py` retains the legacy WATCH-to-TRIGGER flow.
- Latest observed scheduled main run: [42101399621](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42101399621), 2026-11-05 20:13:41 UTC, success. Job steps confirm `python main.py` ran with masked Discord webhook environment variables present. Logs do not prove that a Discord message was delivered.
- No newer scheduled main run was present in the latest Actions query. GitHub may delay or skip scheduled events; do not infer a fixed execution cadence from the cron expression.
- Do not edit or disable this workflow while the explicit “do not modify main” constraint remains. Owner must approve a pause/retention decision before legacy-to-new cutover.

## Risk controls, lifecycle and Discord

- Deterministic quant supervisor: quality >=75/100; minimum 2R; stop distance 0.35–2.5 ATR; entry must equal latest closed 5m price; stale-candle rejection; opposing long/short candidates within 8 quality points produce `NO_TRADE`; `APPROVED_STRATEGIES` remains empty.
- Visual DNS mechanical gates: confidence >=75; minimum 2R; directional zone quality >=3/5; entry deviation <=0.35%; one open paper position per symbol; malformed/API/review errors fail closed.
- Main DNS lifecycle and the quant `trade_lifecycle.py` path both track closed 5m candles, resolve ambiguous same-bar exits stop-first, refuse to bridge missing bars, and require the full 48-hour eligible horizon before TIME. There are two similar lifecycle implementations; audit parity before consolidating.
- Execution Discord format includes setup, entry, stop, targets, R:R, context, rationale and invalidation. TP/SL/TIME updates are separate. The gross-P&L wording is now explicit. Actual webhook delivery remains unverified.
- The deterministic quant lane does not emit WATCH messages. The legacy main workflow can still run the older WATCH-to-TRIGGER path.

## Quant Discovery decision

- Primary archive: 926,209 candles across 18 asset/timeframe datasets; BTC/ETH multi-year, XAUT starts 2026-04-17 (~6.6 months), not three years.
- Six families screened with chronological train/validation/OOS, purge/embargo and five expanding walk-forward blocks. Under stressed costs, all 18 15m asset/hypothesis OOS cells were negative. Only 8/180 walk-forward folds had both positive expectancy and PF >1; only four also had >=30 trades. BTC 1h volatility expansion had 11 OOS trades and negative validation; reject it.
- OI/volatility expansion screen: all BTC/ETH/XAUT candidates were rejected. ETH's best 67-trade OOS result was +0.0493R at 10 bps but -0.0640R at 20 bps; XAUT's 14-trade result was +0.2863R at 10 bps but -0.0305R at 20 bps. These are not robust edges.
- Historical spread/depth and market impact are unavailable. Funding observations are retrievable, but event-time/units attribution is unresolved and funding is excluded from the prior replay. Cost figures are explicit assumptions, not measured execution costs.
- Keep every strategy research-only. Do not populate `APPROVED_STRATEGIES` until a candidate survives adequate OOS sample, walk-forward, parameter-neighbourhood and stressed-cost review.

## Precise next steps

1. Re-check live branch head, PR #1, compare and CI after this handoff commit.
2. Design a versioned visual analyst contract for independent candidate families, explicit comparison/rationale and one winner or `NO_TRADE`; remove mandatory DNS anchoring from the contract and schema together.
3. Update mechanical validation to validate general structural invalidation/entry/stop/target without generating zones; preserve all current confidence, R:R, freshness, stop-distance and one-position controls.
4. Connect the visual analyst to the actual paper worker only after offline tests and an opt-in integration test. Require fresh six-timeframe images each closed-candle cycle and persist raw/review images plus structured decisions.
5. Resolve OpenAI quota before a real chart-to-AI paper-only test. Do not retry repeatedly or alter secrets.
6. Reconcile duplicate lifecycle paths and keep outcome delivery retry-safe.
7. Obtain owner authorization before any change to the active legacy workflow on `main`.
8. Continue independent, reproducible Quant Discovery. No unvalidated research candidate reaches execution alerts.

## Safety boundary

No secret values or credentials are stored here. No main changes, PR merge, deployment, schedule enablement, live trading or exchange orders were performed.
