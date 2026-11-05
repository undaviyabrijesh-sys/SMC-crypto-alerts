# Salty Quant Supervisor Handoff — 2026-11-05 23:27 IST

## Live repository checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts`
- Branch: `ai-quant-rebuild`
- PR: [#1 — Draft: AI-free deterministic multi-strategy quant paper desk](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1)
- PR state at checkpoint: open, draft, unmerged, mergeable; base is `main`.
- PR head at checkpoint: `e8a6ec4b8e333f56a9ac4e3acd39b6091d9e5d5b` — “Include the Chief Trader decision rationale in paper alerts”.
- Base/main SHA: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- GitHub compare: branch is 348 commits ahead, 0 behind; merge base is main SHA above.
- No review submissions or inline review threads were present.
- No branch/main merge, deployment, secret mutation, schedule enablement, live trading, or exchange order was performed.

Re-check the PR head and CI before every subsequent write. Do not assume this checkpoint remains current.

## CI and feed evidence

At PR head `e8a6ec4`, GitHub Actions PR workflow run [42072584817](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42072584817) completed successfully. Its single `test` job passed compilation, visual pipeline, Bull/Bear/Chief contract, DNS map/watcher, backtest, quant supervisor, daily report, feedback, secret-format, derivatives parser/archive and Quant Discovery tests.

The same run reported:
- Public Delta traded-price OHLCV passed closed-bar/freshness checks for all 18 BTCUSD, ETHUSD and XAUTUSD × 5m/15m/1h/4h/1d/1w combinations.
- At the probe timestamp, the latest 5m candles were about 4.7 minutes past close; 15m about 14.7 minutes; 1h about 14.7 minutes; 4h about 74.7 minutes; daily about 1,034.7 minutes; weekly about 5,354.7 minutes. These are CI-time observations, not current quotes.
- Three-day public derivatives-history pilot returned funding, mark-price and open-interest series for all three contracts (funding 1h, mark 5m, OI 1h).
- One small BTC 5m historical OHLCV archive pilot completed with 1,050 candles, 100% coverage and zero gaps.
- The run produced no artifacts. In particular, it did not provide live chart-review PNGs, a vision-model decision, or proof of Discord webhook delivery.
- Combined commit-status endpoint returned no separate statuses; the successful Actions run above is the relevant check evidence.

No failing CI test or clear low-risk code defect was found in this review cycle, so no runtime code change was made. The only new commit in this cycle is this documentation handoff.

## Runtime architecture audit — critical outstanding mismatch

The repository currently contains three different paths; do not conflate them:

1. `worker.py` defaults to `WORKER_MODE=quant`. That path calls `quant_worker.run()`, an AI-free deterministic OHLCV research engine. It does not inspect chart images.
2. `WORKER_MODE=dns` calls `dns_worker.run()`. It fetches six timeframes and creates six-panel chart images only when an AI-authored DNS map needs refresh (first map, scheduled refresh, or zone invalidation). The map is refreshed infrequently; the local `dns_engine.detect_local_setup()` sweep/reclaim detector decides candidate events every cycle. The optional Bull/Bear/Chief review is disabled by default and receives a JSON map plus recent OHLCV bars, not chart images. It runs only after the coded DNS event. This is not the requested visual-first multi-setup decision process.
3. `main.run()` contains a full image-to-vision analysis path (`data.fetch_bundle → render_symbol_chart → ai_analyst.analyse → validate_trade → Discord`). However, its current system prompt forces every actionable trade to be anchored to a DNS zone and only permits other setups as confirmations/refinements. Its validator also requires a nearby quality DNS zone. It therefore does not yet implement independent comparison of DNS, S/R, trend/pullback, momentum, breakout/retest, volatility and mean-reversion candidates. Also, `main.py`'s direct script entrypoint calls `dns_worker.run()`, not `main.run()`.

Additional operational fact: `.github/workflows/alerts.yml` currently invokes `python quant_worker.py` directly. It does not route through `worker.py` or `main.run()`. Its scheduled job remains gated by `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; manual dispatch runs one paper-only quant cycle. No workflow dispatch or schedule enablement was performed.

**Conclusion:** the visual chart pipeline exists and its offline tests pass, but the active default worker and GitHub paper workflow are quant-only; the optional DNS lane still lets a coded sweep/reclaim detector decide candidate events. This does not meet the visual-first instruction. Do not present the current runtime as visual-first or claim that a live chart review occurred.

## Signal, risk, lifecycle and Discord audit

- Quant promotion allowlist: `quant_supervisor.APPROVED_STRATEGIES = frozenset()`; keep it empty.
- Quant supervisor gates include finite/positive levels, exact latest closed 5m entry, stale-candle rejection, direction ordering, minimum 2R, stop distance 0.35–2.5 ATR, integer quality score >=75, strategy identity/rationale, open-position guard, and opposing-side conflict handling.
- DNS lane has AI-authored zone map validation, zone quality floor 3, 0.35% proximity, 2R and one open position per symbol. It is narrower and does not compare all independent setups. Do not broaden it as a shortcut.
- Paper outcome lifecycle uses contiguous closed 5m bars, stop-first ambiguity, explicit gap handling, and separate TP/SL/TIME notifications. A data gap can leave a trade unresolved rather than fabricate an exit.
- Discord formatter includes setup, entry zone, entry, stop, targets, R:R, timeframe agreement, rationale and invalidation; optional Chief Trader rationale is now included. Webhook delivery is not verified by CI.
- No execution alert should be emitted by the quant lane while the allowlist remains empty. The optional DNS lane must not be treated as the approved future visual-first runtime.

## Quant Discovery decision

The committed screens remain research-only:
- The initial fixed-rule screen rejected all 30 asset × timeframe × strategy OOS cells at its stated 10 bps round-trip plus adverse carry stress.
- The later chronological screen reports 926,209 candles across 18 datasets, but XAUT history begins 2026-04-17 (about 6.6 months); BTC/ETH also have observed-history gaps.
- The later screen's best-looking BTC 1h volatility-expansion OOS cell has only 11 trades and negative validation; it is rejected.
- The later screen reports 180 walk-forward folds, with only 8 positive-expectancy/PF>1 folds and only 4 of those at 30+ trades. No stable promoted candidate was established.
- Cost limitations remain: historical spread/depth unavailable; funding event-time/sign/units not yet independently attributed; no exchange contract/margin/liquidation emulator. The three-day funding/mark/OI API probe proves series availability only, not correct funding-cost modelling.
- Historical XAUT sample is insufficient for long-horizon edge claims. No candidate should reach Discord until independent OOS, walk-forward, parameter-neighbourhood and stressed-cost checks survive.

Relevant prior research:
- `quant_discovery/EXP001_INITIAL_SCREEN.md`
- `quant_discovery/HISTORICAL_REPLAY_2026-11-05.md`
- `quant_discovery/SCREEN_2026-11-05.md`
- `quant_discovery/DERIVATIVES_ARCHIVE.md`

## Precise next steps

1. Re-read PR #1, branch head and CI. Do not rely on the hashes above if the branch has advanced.
2. Design the visual-first decision contract before changing runtime: every new closed 5m analysis cycle should generate synchronized six-timeframe charts and ask the vision model to compare all suitable independent candidate families. The image remains primary evidence; OHLCV pins exact levels. Return one best candidate or NO_TRADE with explicit candidate comparisons and evidence. Do not require a DNS anchor for non-DNS setups.
3. Revise `ai_analyst.SYSTEM_PROMPT`, structured output schema and `main.validate_trade` together so the validator checks evidence, timeframe, level geometry, invalidation, stop-distance, 2R, confidence/quality and conflict filters without recreating a coded zone/structure decision-maker.
4. Wire the intended visual path behind an explicit runtime mode and update the GitHub workflow so it cannot silently bypass that mode by directly invoking `quant_worker.py`. Keep all alert routes paper-only and fail closed when the OpenAI key/quota or chart input is unavailable. Do not enable the schedule or change secrets as part of this work.
5. Keep Quant Discovery independent. Commit exact frozen runners/configuration and machine-readable result tables; add parameter-neighbourhood and regime robustness. Align verified funding events only after units/sign/timestamps are established. Expand XAUT history before long-horizon claims.
6. Add focused tests for candidate-family comparison, no-trade on conflict/weak evidence, no DNS-anchor requirement for independent setups, stale/incomplete charts, risk boundaries, no noisy WATCH messages, and separate confirmed outcome delivery.
7. Keep `APPROVED_STRATEGIES` empty and do not promote a research candidate based on these screens.

## Resume rule

A fresh chat should start by re-reading this handoff, fetching the current PR #1 and `ai-quant-rebuild` head, comparing against `main`, and checking the latest CI. Continue from the exact architecture mismatch above; do not repeat the completed historical screens or assume the old tool state persists.
