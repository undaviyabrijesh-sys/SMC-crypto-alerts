# Salty Quant Supervisor Handoff — 2026-11-06 04:25 IST

## Exact repository checkpoint

- Private repository: `undaviyabrijesh-sys/SMC-crypto-alerts`.
- Working branch: `ai-quant-rebuild`.
- Branch head immediately before this final handoff refresh: [`58f4c99`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/58f4c99fb9ad9707e1a963e3946978685cb7f2d1). Documentation-only commits since the last code/test head: visual analyst V2 spec [`ab8de2c`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/ab8de2cc811f57ca5ce03fabc8fa9a24eaf6a0ec), initial handoff `fde36d5`, and mergeability clarification `58f4c99`. This refresh becomes the next branch head; resolve its SHA from the live branch ref.
- PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1): open, draft, unmerged, base `main`; latest metadata recheck returned `mergeable=true`. Latest push/PR CI for pre-refresh head `58f4c99` was still in progress at the time of this handoff refresh; re-check exact-head runs.
- Compare at pre-refresh head `58f4c99`: 361 commits ahead / 0 behind; base/main SHA remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. This refresh adds one further branch-only commit.
- Branch API reports `protected=false` and no required status checks. Do not change branch settings in this task.
- No changes to `main`, no PR merge, deployment, secrets, live trading, exchange orders, or schedule activation.

## Work completed this cycle

- Re-read live branch ref, PR #1, compare metadata, exact-head CI, workflow files, job steps/logs, data ingestion, chart rendering, visual analyst, workers, validator, lifecycle, Discord formatting and research reports.
- No new failing test or sufficiently clear low-risk code defect was found. Existing Boolean-number validation fix remains present at `f9ef735`; the gross-P&L label correction remains present in history.
- Added a design-only document: [`VISUAL_FIRST_INDEPENDENT_ANALYST_V2_SPEC.md`](./VISUAL_FIRST_INDEPENDENT_ANALYST_V2_SPEC.md), commit [`ab8de2c`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/ab8de2cc811f57ca5ce03fabc8fa9a24eaf6a0ec). It specifies independent setup families, a versioned candidate-comparison contract, unchanged mechanical safety gates, runtime separation, fail-closed behaviour, and required offline/integration tests. It is not wired into runtime and does not enable alerts.
- Latest completed exact-head code/test CI: push [42112855948](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42112855948) and PR [42112865809](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42112865809), both success for `d25e8e55a6c7649e898ce850487cbedd9a5e83ab`. Documentation commits triggered new CI: push [42125416342](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42125416342) and PR [42125423897](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42125423897) were in progress on pre-refresh head `58f4c99`; this refresh triggers another pair. Re-check final exact-head CI.

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


## Fresh supervision checkpoint — 2026-11-06 06:45 IST

### GitHub / CI
- Live PR #1 is open, draft, unmerged, mergeable, base `main`; before this checkpoint's small test-clarity commit its head was `784eb0d6f84a477e5f98ddc9fc0d224e997b05ce`. Compare showed 362 commits ahead / 0 behind, with main at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- Exact-head push CI `42125482093` and PR CI `42125488717` both passed on `784eb0d6`. Both ran compile, visual, agents, DNS, replay, quant, lifecycle/reporting, derivatives, research, live public Delta OHLCV/history probes, and a BTC archive pilot.
- The PR run had no uploaded artifacts. CI success is not a live vision decision or Discord-delivery test.
- Repository metadata grants push/admin permission, but branch-protection read returned 403 (resource not accessible by integration); protection state is unverified.

### Small test-clarity fix
- Commit `347975b80aeed5152780204e4f6e0803e267f7e3` renames `test_visual_analyst_compares_multiple_setup_families` to `test_visual_analyst_is_dns_first_and_lists_confirmation_families` and adds a docstring clarifying that enum coverage is not independent setup comparison.
- This is deliberately a test-only clarity change; no production logic or thresholds changed. Verify the new exact-head push and PR CI before relying on it.

### Data-feed snapshot (historical CI observation, not current market prices)
- On the successful 2026-11-05 22:55 UTC CI probe, all 18 BTC/ETH/XAUT × six-timeframe OHLCV checks passed.
- Per asset: 1,151 closed 5m candles; 1,343 15m; 1,079 1h; 719 4h; 364 1d for BTC/ETH (XAUT 202); weekly 149 BTC, 143 ETH, 29 XAUT. These are API-returned rolling windows, not a multi-year research archive.
- Derivatives endpoint returned 71 hourly funding, 864 5m mark-price and 72 hourly OI candles per contract. Availability does not validate funding settlement attribution.
- BTC 5m historical pilot: 1,051 candles, 100% coverage in the requested pilot window, zero gaps.

### Visual pipeline / runtime finding
- Current `ai_analyst.py` still says “DEMAND AND SUPPLY FIRST”; every actionable trade must be DNS-anchored, and trend/momentum/breakout/mean-reversion are confirmations inside/at DNS, not independent candidate families.
- The renamed test makes this limitation explicit. The previous test name overstated what it proved.
- `worker.py` supports only `quant` (default, AI-free) and `dns`; there is no independent `visual` mode. DNS refreshes a visual map infrequently and then a coded local sweep/reclaim detector creates candidates; optional Bull/Bear/Chief review is after that trigger.
- Branch `.github/workflows/alerts.yml` gates its scheduled run on `vars.ENABLE_GITHUB_SCHEDULE == 'true'`, but the workflow's manual/opt-in job directly executes `python quant_worker.py`, not visual analysis. No chart-review artifact was produced.
- Keep V2 as design-only until the schema, prompt, validator, isolated visual paper worker, persistence, mocked end-to-end tests and fail-closed behaviour are implemented together. Never revive coded zones/structure as setup decision-maker.

### Legacy main workflow — unchanged, owner decision required
- Main `.github/workflows/alerts.yml` still schedules every 10 minutes and runs `python main.py` with masked WATCH/TRIGGER Discord webhook variables.
- Latest observed run: [42137828192](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42137828192), created 2026-11-06 00:34:37 UTC and completed successfully. Job logs confirm `python main.py` executed; they do not prove a Discord message was delivered.
- Main `main.py` imports legacy `zones.py` and `score.py` and retains WATCH/TRIGGER logic. Do not modify or disable it without owner authorization; no main change was made.

### Risk, lifecycle, Discord and research
- Existing risk controls remain unchanged. `quant_supervisor.APPROVED_STRATEGIES` remains empty. Branch quant lifecycle retains closed-5m evaluation, stop-first ambiguity, missing-bar protection, 48h TIME expiry and separate/retryable outcome notifications.
- Discord execution/outcome format tests passed; gross P&L is explicitly labeled before fees, spread, slippage and funding. Actual webhook delivery is unverified.
- Quant Discovery remains research-only: 926,209 OHLCV candles across 18 datasets; BTC/ETH have roughly 2.7 years, XAUT starts 2026-04-17 (~6.6 months). Prior six-family screen rejected all candidates; all 18 15m OOS cells were negative under stressed costs; only 8/180 folds had positive expectancy and PF >1, and only four also had >=30 trades. BTC 1h volatility expansion's 11-trade OOS result had negative validation. OI expansion did not survive cost/validation/sample checks. Funding excluded from P&L; measured spread/depth unavailable.
- Last documented OpenAI API blocker remains HTTP 429 insufficient quota; quota was not re-tested and no credentials/secrets were changed.

### Next actions
1. Verify exact-head CI for test-clarity commit `347975b` and the following handoff refresh commit.
2. Implement V2 independent setup comparison in a separate opt-in visual paper mode; update prompt, strict schema, validator and worker together.
3. Keep all existing mechanical gates and reject stale/missing images, watermarks, malformed output, conflicts and API failures as NO_TRADE.
4. Add mocked end-to-end chart-to-paper tests, then separately verify API quota and a paper-only vision smoke test.
5. Keep Quant Discovery separate; reproduce experiments from frozen runners/data, extend XAUT, and resolve funding/spread/depth before net-cost claims.
6. Obtain owner authorization before any legacy main-workflow cutover.

No deployment, main modification, PR merge, secret change, schedule activation, live trading or exchange order was performed.
