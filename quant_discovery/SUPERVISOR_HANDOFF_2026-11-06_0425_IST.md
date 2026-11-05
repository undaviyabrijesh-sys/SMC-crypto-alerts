# Salty Quant Supervisor Handoff — 2026-11-06 04:25 IST

## Exact repository checkpoint

- Private repository: `undaviyabrijesh-sys/SMC-crypto-alerts`.
- Working branch: `ai-quant-rebuild`.
- Branch head immediately before this handoff: [`ab8de2c`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/ab8de2cc811f57ca5ce03fabc8fa9a24eaf6a0ec), documentation-only visual architecture spec.
- PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1): open, draft, unmerged, base `main`. After the documentation commit, GitHub temporarily reported `mergeable=false` while the new push/PR CI checks were still in progress; re-check mergeability after checks complete.
- Compare at prior code head: 358 commits ahead / 0 behind; base/main SHA remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. Adding this handoff will add one further branch-only commit.
- Branch API reports `protected=false` and no required status checks. Do not change branch settings in this task.
- No changes to `main`, no PR merge, deployment, secrets, live trading, exchange orders, or schedule activation.

## Work completed this cycle

- Re-read live branch ref, PR #1, compare metadata, exact-head CI, workflow files, job steps/logs, data ingestion, chart rendering, visual analyst, workers, validator, lifecycle, Discord formatting and research reports.
- No new failing test or sufficiently clear low-risk code defect was found. Existing Boolean-number validation fix remains present at `f9ef735`; the gross-P&L label correction remains present in history.
- Added a design-only document: [`VISUAL_FIRST_INDEPENDENT_ANALYST_V2_SPEC.md`](./VISUAL_FIRST_INDEPENDENT_ANALYST_V2_SPEC.md), commit [`ab8de2c`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/ab8de2cc811f57ca5ce03fabc8fa9a24eaf6a0ec). It specifies independent setup families, a versioned candidate-comparison contract, unchanged mechanical safety gates, runtime separation, fail-closed behaviour, and required offline/integration tests. It is not wired into runtime and does not enable alerts.
- Latest code/test CI before the two new documentation commits was exact-head success: push [42112855948](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42112855948) and PR [42112865809](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42112865809), both for `d25e8e55a6c7649e898ce850487cbedd9a5e83ab`. New docs commits trigger fresh CI; re-check after handoff commit.

## Current CI and data-feed evidence

The successful push and PR CI jobs each completed all listed steps: compile, visual pipeline, Bull/Bear/Chief contracts, DNS tests, replay, quant engine, daily reports, feedback, OpenAI secret-format tests, derivatives parser/archive tests, Quant Discovery tests, public Delta feed probe, funding/mark/OI probe and a small historical archive pilot.

At 2026-11-05 21:28:18 UTC the feed probe passed all 18 symbol/timeframe checks:
- BTCUSD, ETHUSD, XAUTUSD × 5m, 15m, 1h, 4h, 1d, 1w.
- These are CI-time observations, not current quotes. 1d/1w candles naturally have older close ages but remain within configured freshness limits.
- Three-day derivatives probe: 70 hourly funding observations per contract, 864 five-minute mark candles per contract, and 72 hourly OI candles per contract.
- BTC 5m archive pilot: 1,051 candles, 100% coverage, zero gaps for the requested pilot window.
- Historical spread/depth/impact remain unavailable. Funding history availability does not prove event-time/units/settlement attribution.

## Visual chart-to-AI architecture — main blocker

Confirmed from live branch source:
- `worker.py` defaults to `WORKER_MODE=quant` and calls AI-free `quant_worker.py`.
- `WORKER_MODE=dns` calls `dns_worker.py`, where the visual DNS map refreshes infrequently and a coded local sweep/reclaim detector generates candidates; optional Bull/Bear/Chief review runs only after that trigger and is disabled by default.
- `ai_analyst.py` sends six-panel chart images to the Responses API, but its system prompt requires a primary directional demand/supply zone. Other families are only DNS confirmations/refinements. `test_visual_pipeline.py` has DNS-first assertions.
- Branch `.github/workflows/alerts.yml` directly executes `python quant_worker.py`; it bypasses `worker.py` mode selection. Its schedule is gated by `ENABLE_GITHUB_SCHEDULE`, and manual dispatch runs the same deterministic quant worker.
- Therefore no active branch workflow currently performs independent visual candidate comparison every new closed 5m cycle. Latest CI had no workflow artifacts, no chart-review images, no live model decision, and no Discord delivery evidence.
- Last documented live API failure is HTTP 429 insufficient quota. This cycle did not test quota or touch credentials. The model string in config was not changed.
- Do not revive coded `zones.py`/`score.py` as decision-maker. Do not patch only the prompt. Implement the new schema, prompt, validator, worker, persistence and tests together using the V2 design spec.

## Main-branch legacy workflow — owner attention required

- Live `main` workflow `.github/workflows/alerts.yml` still schedules `*/10 * * * *` and runs `python main.py` with masked `DISCORD_WEBHOOK`, `DISCORD_WATCH_WEBHOOK`, and `DISCORD_TRIGGER_WEBHOOK` environment variables.
- Latest observed main scheduled run: [42121787128](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42121787128), created 2026-11-05 22:28:29 UTC, completed successfully. Job steps/logs confirm legacy `python main.py` executed; logs do not prove a Discord message was delivered.
- Main code imports the coded `zones.py` / `score.py` path and retains WATCH/TRIGGER messages. This is not the requested visual-first execution architecture and may continue producing legacy notifications.
- Do not modify/disable the workflow or `main` from this task. Owner authorization is required before pausing or replacing it during cutover.

## Risk, lifecycle and Discord state

- Quant supervisor: quality >=75/100, minimum 2R, stop distance 0.35–2.5 ATR, entry exactly the latest closed 5m price, stale signal-candle rejection, opposing directions within 8 quality points => NO_TRADE, one open paper position per symbol.
- `APPROVED_STRATEGIES` remains empty. No deterministic research candidate can reach quant execution alerts.
- DNS lane: confidence >=75, minimum 2R, visual zone quality >=3/5, entry deviation <=0.35%, one open position per symbol; malformed output/API errors fail closed.
- Quant `trade_lifecycle.py`: closed 5m bars, stop-first same-bar ambiguity, missing-bar protection, 48h TIME horizon, separate outcome notification and retry queue. Parallel legacy lifecycle remains in `main.py`; parity audit remains open.
- Discord formatter includes setup and execution levels; outcome messages distinguish gross paper P&L before fees/spread/slippage/funding. Branch quant lane does not send WATCH. Actual webhook delivery is unverified.

## Quant Discovery decision

- Existing archive: 926,209 OHLCV candles across 18 datasets. BTC starts 2023-12-29, ETH 2024-02-05, XAUT 2026-04-17 (~6.6 months only).
- Six independent setup families screened with chronological splits, purge/embargo, walk-forward and explicit fee/slippage/spread assumptions. No strategy passed promotion.
- Initial screen: all 18 15m asset/hypothesis OOS cells negative under stressed costs; only 8/180 folds positive with PF >1, only four also >=30 trades. BTC 1h volatility expansion had 11 OOS trades and negative validation; reject.
- OI/volatility screen rejected: apparent ETH/XAUT positives did not survive 20 bps cost stress and/or adequate sample/validation.
- Funding excluded from prior P&L because event-time/units attribution unresolved. Historical spread/depth/impact unavailable. Do not claim an edge or populate the approval allowlist.

## Precise next steps

1. Verify the CI runs triggered by `ab8de2c` and this handoff commit; ensure exact-head push and PR checks pass.
2. Implement the V2 visual response schema and prompt, including independent setup families and selected candidate or `NO_TRADE`.
3. Update validation and tests together: validate only the model-selected plan; never let coded zones or scores select a market setup; retain all existing mechanical gates.
4. Add an isolated opt-in visual paper worker that analyses fresh unannotated six-timeframe images on each new closed 5m cycle, records image hashes/watermarks and raw decisions, and emits execution-only paper alerts only after validation.
5. Add mocked end-to-end tests; then resolve API quota and perform a separate paper-only live vision smoke test. Do not change credentials or repeatedly retry quota failures.
6. Audit lifecycle parity, persistence and retry-safe outcome delivery.
7. Obtain owner authorization before changing the legacy scheduled workflow on `main`.
8. Continue Quant Discovery separately; no candidate promotion without adequate OOS, walk-forward, parameter-neighbourhood and stressed-cost evidence.

No secrets or credentials are stored in this handoff.
