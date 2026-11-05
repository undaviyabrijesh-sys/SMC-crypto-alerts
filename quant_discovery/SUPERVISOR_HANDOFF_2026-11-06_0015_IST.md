# Salty Quant Supervisor Handoff — 2026-11-06 00:15 IST

## Live checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts`
- Working branch: `ai-quant-rebuild`
- PR: [#1 — Draft: AI-free deterministic multi-strategy quant paper desk](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1)
- Pre-handoff code/test head: `2788f92308b9be52b88e38be11f2fdae5846b702`.
- PR #1: open, draft, unmerged, mergeable; base `main`; 350 commits ahead / 0 behind.
- `main` base SHA remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- The branch is not protected in GitHub. Do not change protection as part of this task.
- No merge, main edit, deployment, secret change, schedule enablement, live trading, or exchange order was performed.

Re-fetch branch, PR and CI before every later write; do not assume this checkpoint remains current.

## Changes and CI

Added two focused lifecycle regressions to `test_quant_engine.py` in commit [2788f92](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/2788f92308b9be52b88e38be11f2fdae5846b702):

1. A TP touch on the first candle opening at/after the 48-hour expiry must not overwrite the time exit. TIME is priced at the final eligible in-horizon candle close.
2. A missing 5m candle inside the eligible 48-hour window leaves the position unresolved; do not fabricate a TIME/TP/SL result.

Both exact-head checks passed:
- Push CI [42087648035](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42087648035): success.
- PR CI [42087662049](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42087662049): success.
- PR CI executed compilation, visual pipeline, Bull/Bear/Chief contract, DNS worker, replay, quant supervisor, daily report, feedback, secret format, derivatives parser/archive, Quant Discovery, live OHLCV, derivatives-history probe and archive pilot. The new quant engine suite reported 18 tests; DNS suite 19; Quant Discovery suite 10. All workflow steps passed.

Latest CI feed snapshot (2026-11-05 18:48:19 UTC; historical CI evidence, not a current quote):
- 18/18 BTCUSD, ETHUSD, XAUTUSD × 5m/15m/1h/4h/1d/1w closed-candle/freshness checks passed.
- 5m closes at probe: BTC 76,172.0; ETH 2,251.9; XAUT 4,093.12. Do not present these as current prices.
- Three-day derivatives probe: funding 67 BTC / 67 ETH / 71 XAUT hourly candles; mark 864 five-minute candles per contract; OI 72 hourly candles per contract. Availability is not proof of correct funding settlement attribution.
- BTC 5m historical pilot: 1,051 candles, 100% pilot coverage, zero gaps. This is a small smoke-test window, not a full-history quality claim.
- No CI artifacts were uploaded, including no raw/annotated chart images or chart-review evidence. The CI run does not prove a live vision-model decision or Discord webhook delivery.

## Critical architecture mismatch — unresolved

Do not describe the active system as visual-first.

1. `worker.py` defaults to `WORKER_MODE=quant` and calls `quant_worker.run()`. The branch alert workflow `.github/workflows/alerts.yml` directly invokes `python quant_worker.py`. Neither path inspects chart images.
2. `WORKER_MODE=dns` calls `dns_worker.run()`. It renders six-timeframe charts only when a DNS map refresh is due. A local coded sweep/reclaim detector decides candidate events on each cycle. The optional Bull/Bear/Chief review is off by default and runs only after that coded event; it receives candidate/map/recent OHLCV, not the chart images. This is not independent visual setup competition.
3. `main.run()` contains a six-timeframe image-to-`ai_analyst.analyse()` path, but `main.py`'s script entrypoint imports and runs `dns_worker.run()`, not `main.run()`. The branch paper workflow also bypasses `main.run()`.
4. `ai_analyst.SYSTEM_PROMPT` requires DNS-first setups; non-DNS setups cannot bypass the zone anchor. `main.validate_trade()` independently requires a nearby quality demand/supply zone overlapping the selected entry band.

The requested architecture is still outstanding: on every new closed 5m analysis cycle, render synchronized six-timeframe charts, have vision compare suitable independent candidate families (SMC/structure, supply-demand, liquidity, S/R, trend/pullback, momentum, breakout/retest, volatility/mean reversion and others supported by the image), return the single best actionable candidate or NO_TRADE, then apply mechanical risk validation. The image is primary evidence; OHLCV pins exact prices. Do not substitute a coded market-structure/zone engine as decision-maker and do not force a DNS anchor for unrelated setups.

## Risk, lifecycle and Discord

- `quant_supervisor.APPROVED_STRATEGIES = frozenset()`; keep it empty. No current research candidate is approved.
- Quant candidate gates include finite/positive ordered levels, exact latest closed 5m entry, stale-candle rejection, minimum 2R, stop distance 0.35–2.5 ATR, integer quality score >=75, strategy/rationale checks, opposing-side conflict handling and one open paper position per symbol.
- DNS path remains a narrower sweep/reclaim-at-map-zone workflow with quality/proximity/R:R/one-position checks; it is not the approved future visual decision architecture.
- Paper outcome tracking uses contiguous closed 5m candles and stop-first intrabar ambiguity. Missing bars leave outcomes unresolved. The new expiry regressions passed.
- Discord formatters are covered by tests and are execution-focused; TP/SL/TIME outcome messages are separate. Actual webhook delivery is not verified by CI.
- The CI log contains a simulated `[dns-agent-veto] ... ERROR quota` from a mocked test path; it is not evidence of a live API request. The last documented real OpenAI failure remains HTTP 429 `insufficient_quota`; no fresh quota test or secret change was performed.

## Quant Discovery — unchanged, no promotion

- Existing archive report: 926,209 candles across 18 datasets. BTC/ETH/XAUT coverage has known gaps; do not fill missing candles or overstate continuity.
- XAUT history starts 2026-04-17 (about 6.6 months), not a multi-year gold sample.
- The first chronological screen rejected all 18 15m OOS asset/hypothesis combinations under stated stressed costs.
- Only 8/180 walk-forward folds had both positive expectancy and PF > 1; only 4 also had at least 30 trades. No stable full-OOS candidate emerged.
- BTC 1h volatility-expansion's apparent positive OOS result had only 11 trades and negative validation; reject it.
- Historical spread/depth are unavailable; funding event-time/sign/units are not independently attributed. Three-day endpoint availability is not a calibrated funding-cost model.
- Keep all hypotheses research-only. Do not promote or alert from these results.

## Exact next steps

1. Re-read this handoff, then fetch current PR #1, `ai-quant-rebuild` head, compare against `main`, and inspect exact-head push + PR CI.
2. Design the independent visual candidate-comparison prompt/schema/validator as one contract. Explicitly allow non-DNS setups and return one winner or NO_TRADE; keep images primary.
3. Add tests for independent candidate competition, no-DNS-anchor eligibility, conflicting candidates, incomplete/stale chart inputs, invalidation/stop/target geometry and fail-closed API/chart errors.
4. Wire the visual path into an explicit worker mode and the branch paper workflow without silently falling back to quant/DNS decision-making. Keep paper-only, do not enable schedules or alter secrets.
5. Verify a real visual request only after quota is restored, using a manually initiated paper-only test with chart artifacts and model metadata retained.
6. Verify actual Discord execution and confirmed TP/SL/TIME delivery separately; do not infer delivery from formatter tests.
7. Continue Quant Discovery independently; commit exact frozen runners/configuration/result tables, expand Gold history, and resolve cost/funding attribution before any promotion.

## Resume rule

A fresh chat should start by re-checking live GitHub state and CI, then continue from the architecture mismatch above. Do not repeat completed historical screens, assume old tool state persists, or claim an autonomous new chat was created.
