# Salty Quant Supervisor Handoff — 2026-11-07 02:26 IST

## Exact repository checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Code/test commit: `cb8f8b7a8cc6afd554343b9b69cdda75ecefe42d` — **Refuse oversized Discord messages instead of truncating**.
- Parent: `76d6f16055168474666b5dc9b8abba622625769d`.
- Base `main`: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- Compare at code/test head: **436 ahead, 0 behind**; merge base equals main.
- PR #1: open, draft, mergeable, unmerged; 436 commits, 86 changed files. No submitted reviews or inline review threads.
- Current branch-protection endpoint reports `protected=false`, `protection.enabled=false`, and required status-check enforcement `off` with no contexts/checks. This is a real governance gap; do not change settings without owner authorization. The repository rulesets endpoint is not available through the current GitHub connection, so no claim is made about other rulesets.

## Low-risk bug fixed

- In `discord.py`, generic `_post()` previously sent `content[:1900]`, silently truncating long legacy, quant, outcome and daily-report messages. Visual alerts already rejected oversized messages, but the shared boundary did not.
- It now refuses any message longer than 1,900 characters and sends the complete original content for messages within the budget.
- Added two regression tests to `test_visual_first.py`: oversized messages must not call the webhook; a 1,900-character message must be delivered unchanged.
- Commit: [`cb8f8b7`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/cb8f8b7a8cc6afd554343b9b69cdda75ecefe42d).

## Exact-head CI

Both workflows passed on code/test commit `cb8f8b7`:

- Push CI: [42292374923](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42292374923), job `test` ID `128148804459`, success.
- PR CI: [42292384088](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42292384088), job `test` ID `128148835281`, success.
- Both ran the full workflow: compile, visual pipeline and mocked paper cycle, manual workflow contract, agent contracts, DNS watcher tests, quant replay/supervisor, daily reports, feedback, secret-format checks, derivatives parser/archive, Quant Discovery tests, public Delta OHLCV, derivatives-history probes and BTC historical pilot.
- Push log explicitly passed `test_discord_post_refuses_oversized_messages_without_sending_truncated_content` and `test_discord_post_sends_the_complete_message_within_the_safe_budget`.
- CI artifact list was empty. These are code tests, not a real visual dispatch.

## Latest CI market-data snapshot (not live quotes)

Push CI log at **2026-11-06 20:55:48 UTC (2026-11-07 02:25:48 IST)**:

- All **18/18** BTCUSD / ETHUSD / XAUTUSD checks passed across 5m, 15m, 1h, 4h, 1d and 1w.
- Latest closed 5m values: BTC **75,822.00**, ETH **2,230.25**, XAUT **4,054.71**.
- Funding: 69 hourly candles for each instrument. Mark price: 864 five-minute candles each. Open interest: 72 hourly candles each.
- BTC 5m historical pilot: **1,051 candles**, 100% coverage, zero gaps; SHA-256 prefix `eda17c4532dd`.
- XAUT weekly history remains limited to 29 candles. These are CI-time observations, not current market quotes.

## Visual-first chart-to-AI lane

Inspected `visual_first_analyst.py`, `visual_worker.py`, `discord.py`, `main.py`, `state.py`, `trade_lifecycle.py`, `test_visual_first.py`, `test_visual_pipeline.py`, `alerts.yml`, `tools.yml` and `ci.yml`.

- The independent visual analyst receives raw six-timeframe charts (5m, 15m, 1h, 4h, 1d, 1w), compares SMC/structure, supply-demand, liquidity sweeps, support/resistance, trend pullback, momentum, breakout/retest, volatility expansion, mean reversion and other evidence-supported approaches. It selects at most one candidate or `NO_TRADE`.
- DNS maps are optional context for this analyst; coded DNS/zone/sweep logic does not select, rank or substitute a setup. The legacy `main.validate_trade()` still has DNS-specific checks, but the visual worker uses its independent `validate_analysis()` path. Do not route visual decisions through the legacy validator.
- Visual validation requires current chart watermarks, candidate identity, immediately actionable market entry, valid entry/stop/target geometry, actual R:R, ATR stop band, confidence/quality, two distinct evidence timeframes, no same-symbol open/pending position, and fail-closed opposing-candidate comparison. It never substitutes an alternative candidate.
- Unchanged gates: confidence >=75; quality >=75; R:R >=2.0; stop distance 0.35–2.5 trigger-timeframe ATR; entry-zone deviation <=0.35%; at least two distinct evidence timeframes including trigger; one open/pending paper position per symbol; an opposing actionable candidate must be at least eight quality points weaker or the model decision fails closed.
- Manual visual workflow requires `task=visual-desk-run` and `confirm_visual_paper=true`. Scheduled workflow is opt-in through `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; scheduled runs route to the AI-free quant worker, not visual AI. No workflow was dispatched and no schedule was enabled.
- Raw chart PNGs, hashes and six-timeframe watermarks are persisted with a manifest when a real cycle runs. Latest CI artifact list is empty.
- No real chart bundle, OpenAI vision response, selected real paper signal or Discord webhook delivery was verified. Last recorded OpenAI blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested.

## Discord and lifecycle

- Visual alert includes setup family, entry band/price, stop, target, R:R, trigger, context, rationale, target rationale, invalidation, supporting/conflicting evidence and cancellation conditions. Visual formatter and now the shared `_post()` boundary both fail closed above 1,900 characters.
- Lifecycle confirms outcomes only on closed 5m candles, resolves same-candle TP/SL conservatively as SL-first, does not infer outcomes across missing bars, and sends separate TP/SL/TIME messages. Failed outcome delivery is queued for retry.
- A position with a data gap before a confirmed exit can remain unresolved/open and block another same-symbol signal; do not invent an outcome. Persistent cross-run state relies on evictable GitHub Actions cache, so durable position persistence is not guaranteed.
- Outcome P&L is gross paper P&L before fees, spread, slippage and funding, not broker P&L.

## Quant Discovery

- `quant_supervisor.APPROVED_STRATEGIES` remains empty. No research candidate is approved or promoted.
- EXP-001: all 30 baseline OOS combinations and 270 stop/target variants negative at documented baseline cost assumptions. Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, seven consecutive losses, 25.76 trades/month.
- OI expansion: BTC 45 OOS trades, -0.0313R; ETH 67 trades, +0.0493R at 10 bps but negative in train/validation and at 20 bps; XAUT 14 trades, +0.2863R at 10 bps but weak sample and negative at 20 bps. Reject all.
- OHLCV archive: 926,209 candles across 18 datasets. Derivatives archive: 758,119 candles across nine BTC/ETH/XAUT series. XAUT history begins 2026-04-17 (~6.6 months), not three years.
- Derivatives artifact ID `13383865992`, source run [41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516), expires **2026-11-19 02:37:57 UTC**. Preserve it before expiry.
- Funding candle units and settlement-event semantics remain unresolved; raw funding closes are not realized cashflow. Historical executable spread/depth/market-impact data are unavailable. Do not silently set unknown costs to zero or claim funding-adjusted performance.
- The DNS visual evaluation and SMC subset-updater documents describe a separate DNS-anchored experimental watcher. They are not the independent visual-first analyst and must not become its decision-maker.

## Legacy workflow and governance

- `main` remains at `e93ee289`. Its legacy scheduled `main.py` / WATCH-TRIGGER path remains a separate owner-authorized migration item.
- Branch protection is disabled at the classic branch endpoint; required CI enforcement is off. Ruleset enforcement could not be read through the current connection.
- PR #1 remains draft and unmerged. Do not merge, deploy, alter secrets, enable schedules, activate live trading or place orders.

## Exact next steps

1. Keep PR #1 draft/unmerged and main untouched.
2. Restore/confirm OpenAI project quota through owner account controls; do not change secrets during supervision.
3. When explicitly confirmed, run one paper-only visual cycle; inspect raw BTC/ETH/XAUT six-timeframe images, manifest hashes/watermarks, model candidate comparison, validator decisions and actual Discord delivery.
4. Preserve derivatives artifact `13383865992` before expiry; verify manifest and hashes after download.
5. Confirm funding interval, units, sign and event-time attribution against contract metadata and a realized funding event before implementing funding P&L; then add unit/sign/negative-rate/missing-event/boundary tests and rerun chronological train/validation/OOS and walk-forward research.
6. Improve durable position storage beyond evictable Actions cache; define a safe unresolved-gap reconciliation path without fabricating TP/SL/TIME.
7. Obtain owner decision on legacy-main workflow migration and branch-protection/required CI settings.

## Safety

Only `ai-quant-rebuild` was changed. No main changes, PR merge, deployment, secret modification, workflow dispatch, schedule activation, live trading, exchange orders or risk-threshold reductions were performed.
