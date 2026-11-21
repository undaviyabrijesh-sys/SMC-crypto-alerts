# Salty Quant Supervisor Handoff — 2026-11-06 01:01 IST

## Live GitHub checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Current branch head at inspection: `fbf1b0679660870413848f83465faea1a03757b9` — "Save Salty Quant supervisor handoff for 2026-11-06".
- PR #1: open, draft, unmerged, mergeable; base `main`; head `ai-quant-rebuild`.
- Compare: 351 commits ahead, 0 behind. PR base SHA / current main SHA: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- Branch API reports branch protection disabled. Do not change branch protection as part of this supervision task.
- No code changes were required in this cycle: latest lifecycle regression tests already cover the previously identified expiry and missing-candle cases, and current CI is green.
- No merge, main edit, deployment, secret change, schedule enablement, live trading or exchange order was performed.

Re-fetch branch, PR, workflow runs and status checks before any later write. Do not assume this checkpoint remains current.

## CI and market-data evidence (2026-11-06 00:19–00:20 IST)

Exact-head checks for `fbf1b067`:
- Push CI: [42087889227](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42087889227) — success.
- PR CI: [42087900133](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42087900133) — success.
- PR check run includes compilation and the visual, agent, DNS, quant replay/supervisor, reports, feedback, secret-format, derivatives-history/archive, Quant Discovery and feed smoke suites.

Feed smoke at 2026-11-05 18:49:35 UTC:
- 18/18 BTCUSD, ETHUSD and XAUTUSD × 5m/15m/1h/4h/1d/1w closed-candle/freshness checks passed.
- 5m closes at that probe: BTC 76,172.0; ETH 2,251.9; XAUT 4,093.12. These are historical CI observations, not current quotes.
- Three-day derivatives probe: funding 67 BTC / 67 ETH / 71 XAUT hourly candles; mark 864 five-minute candles per contract; OI 72 hourly candles per contract.
- BTC 5m archive pilot: 1,050 candles, 100% coverage, zero gaps.
- The feed snapshot is not live at the time of this handoff. No chart-review artifacts were attached to the CI run; the visual PNG tests render fixtures but do not provide a current market chart for human/AI review.

## Critical runtime and visual-first architecture findings

1. Branch `worker.py` defaults to `WORKER_MODE=quant`. The deterministic quant lane is AI-free and is the default.
2. Branch `.github/workflows/alerts.yml` directly invokes `python quant_worker.py`; it does not route through the mode selector. Its schedule is gated by `vars.ENABLE_GITHUB_SCHEDULE == 'true'`, but scheduled workflows only run from the repository's default branch. Do not assume this branch workflow is running on a schedule.
3. Branch `ai_analyst.py` is genuinely image-based and reads the six timeframe panels, but its system prompt hard-requires demand/supply anchoring. It does not allow independent standalone trend/momentum/breakout/mean-reversion candidates away from DNS.
4. Branch `dns_worker.py` refreshes visual maps infrequently and then uses a local coded sweep/reclaim watcher. Optional Bull/Bear/Chief debate is opt-in and occurs only after a local DNS trigger. It is advisory; the mechanical DNS/risk checks remain authoritative.
5. Therefore, the requested independent visual candidate comparison is not the active decision path. No live chart images or chart-review artifacts were available in this CI cycle, so no current visual setup was assessed and no execution signal is justified.
6. Do not revive `zones.py` / `score.py` as a decision-maker. The next architecture should have the vision analyst compare suitable independent setup families from fresh multi-timeframe images, return one best candidate or `NO_TRADE`, and pass any candidate through mechanical risk gates. Preserve DNS as visual context, not a mandatory entry anchor.

## Important default-branch legacy workflow — owner decision required

GitHub evidence shows the default `main` branch still has `.github/workflows/alerts.yml` scheduled every 10 minutes and invoking `python main.py`. The workflow supplies `DISCORD_WEBHOOK`, `DISCORD_WATCH_WEBHOOK` and `DISCORD_TRIGGER_WEBHOOK` to that process. Main's `main.py` imports `zones.py` / `score.py` and contains the legacy WATCH-to-TRIGGER flow.

A scheduled run on main completed successfully at 2026-11-05 19:24:21–19:24:49 UTC:
- [Run 42093564382](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42093564382).
- Job log confirms the scheduled workflow executed `python main.py` with Discord webhook secrets injected. It does not expose a message payload or prove that a Discord alert was delivered.
- This is a material conflict with the requested visual-first / no-WATCH architecture. It has NOT been changed because main must remain untouched. Repository owner must decide whether to pause the legacy workflow or retain it until an approved cutover. Do not change main or disable this workflow without explicit authorization.

## Risk, lifecycle and Discord audit

- Quant supervisor: minimum quality 75/100; minimum 2R; stop distance 0.35–2.5 ATR; exact latest-close entry; stale-candle rejection; conflicting opposite-side candidates within 8 quality points produce NO_TRADE; `APPROVED_STRATEGIES` remains empty.
- Visual DNS path: confidence >=75; minimum 2R; directional DNS quality >=3; max entry deviation 0.35%; one open position per symbol; malformed/API/review failures fail closed.
- `trade_lifecycle.py` tracks closed 5m candles, resolves ambiguous same-bar stop/target stop-first, refuses to bridge missing candles, caps TP/SL checks at the 48h expiry and only issues TIME after the full eligible horizon is observed. Existing tests cover TP, missing-bar unresolved, post-expiry target ignored, and time exit at the last eligible candle.
- Discord execution messages include setup, entry, stop, target, R:R, timeframe context, rationale and invalidation. Outcome messages are separate TP/SL/TIME updates. The deterministic quant lane does not emit WATCH messages.
- Actual Discord webhook delivery remains unverified by CI. The legacy main workflow may still emit WATCH/trigger messages; its run log alone does not prove delivery.

## Quant Discovery status

- Existing archived screen remains research-only. Archive: 926,209 candles across 18 asset/timeframe datasets; BTC and ETH have multi-year history, while XAUT begins 2026-04-17 (~6.6 months).
- The six screened families were trend pullback, breakout, liquidity sweep, mean reversion, volatility expansion and momentum. The documented process used chronological train/validation/OOS partitions, five expanding walk-forward blocks, gap-aware replay, next-bar entries, stop-first ambiguous exits, fees, slippage and a spread proxy.
- No candidate passed the full OOS / walk-forward / stressed-cost promotion standard. The BTC 1h volatility-expansion cell had only 11 OOS trades and failed validation consistency; reject it as an edge.
- Historical spread/depth and market-impact data are unavailable. Funding history is retrievable, but settlement attribution/units are not yet verified and funding was excluded from the prior replay. No strategy is approved for execution.

Primary report: [SCREEN_2026-11-05.md](SCREEN_2026-11-05.md).

## Precise next steps

1. Re-check live branch, PR #1 and latest CI after this documentation commit.
2. Design a versioned visual analyst contract with multiple independent candidate setups and a single winner / `NO_TRADE` response. Remove the hard DNS-anchor requirement only as part of that tested contract.
3. Run vision on every new closed-candle cycle using fresh six-timeframe chart images; persist raw and reviewed chart images plus structured decisions as auditable artifacts.
4. Keep the local coded zone/sweep engine out of decision authority. Keep the existing 75/100, 2R, ATR, freshness, conflict and one-position risk gates.
5. Wire the new visual analyst to the actual paper worker only after offline contract tests and an opt-in integration test pass. Do not activate live/scheduled alerts as part of this change.
6. Verify OpenAI API quota/model availability without printing or changing secrets; the last recorded quota error is not currently re-verified.
7. Resolve the default-branch legacy workflow with the owner before cutover; main remains untouched until explicit approval.
8. Continue Quant Discovery only with reproducible, chronological, cost-aware OOS and walk-forward experiments. No research candidate may enter execution alerts without promotion review.

## Safety boundary

No secret values, webhook URLs or credentials are recorded here. No live exchange order, deployment, schedule enablement, PR merge or main modification has been performed.
