# Quant Discovery — Research Protocol and Handoff

Status: research design recorded; no historical experiment has been run and no candidate is approved for production.

## Purpose

Build an independent research stream beside the visual AI analyst. Discover repeatable BTC, ETH and Delta XAUTUSD behaviours from raw market data, including candidates outside SMC. The visual analyst remains the chart-reading decision-maker for live paper alerts; this workstream must not replace it with a coded zone/structure engine.

## Current repository evidence (2026-11-04)

- `data.py` fetches Delta Exchange India OHLCV for BTCUSD, ETHUSD and XAUTUSD at 5m, 15m, 1h, 4h, 1d and 1w.
- Current per-fetch lookbacks are 4d, 14d, 45d, 120d, 365d and 1825d respectively. Rolling CSV retention is capped by timeframe in `MAX_ROWS`.
- The runtime stores rolling candles and visual decisions under ignored runtime paths (`market_data/`, `research/`); the GitHub Actions fallback relies on cache. The persistent worker has not been deployed, so continuous history accumulation is not established.
- The repository currently has no dedicated Quant Discovery backtest/experiment runner and no tracked historical OHLCV dataset. CI's live-feed smoke test validates current data availability and candle handling; it is not a historical backtest.
- The current OHLCV feed does not contain order-book depth or a complete historical funding/spread series. Candle-derived sweep/liquidity features are proxies, not proof of resting liquidity. Any missing cost/funding input must be explicitly marked, never silently treated as zero.

## First hypothesis families (unproven)

1. Volatility compression followed by range expansion and breakout/retest.
2. Trend continuation after a pullback, normalized by ATR/realized volatility.
3. Failed breakout or liquidity sweep followed by reclaim; OHLCV wick/close proxy only.
4. Range rejection / mean reversion, gated by an objectively defined balanced regime.
5. Momentum continuation after displacement and consolidation.

These are research hypotheses, not live signal rules. Test each independently; do not blend incompatible entries into one strategy.

## Required experiment record

Every run must persist:
- Experiment ID, code/version hash, instrument/venue/contract, timeframe, hypothesis, parameter grid and exact date range.
- Raw-data file hashes, candle count, missing/duplicate-bar checks, timezone, and any excluded intervals.
- Entry timestamp and executable fill assumption; stop/target logic; maximum holding time; same-bar ambiguity policy.
- Fee tier, spread assumption, slippage model, funding inputs or an explicit unavailable-data flag.
- Chronological train/validation/untouched test boundaries and walk-forward fold definitions.
- Trades, equity curve, gross/net P&L, win rate, expectancy in R, profit factor, maximum drawdown, longest win/loss streak, frequency, exposure, and regime breakdown.
- Reproducible parameter/config file and machine-readable results (JSON/CSV).

## Validation protocol

1. Validate raw data first: UTC, monotonic timestamps, unique bars, OHLC integrity, gaps, and contract continuity.
2. Define each hypothesis and parameter search before inspecting the final holdout. Never use future bars to create features or confirm an entry.
3. Make decisions only after a candle has closed; simulate fills at the next executable bar/price, not at information unavailable at decision time.
4. Use chronological train / validation / untouched out-of-sample segments. Add a purge/embargo at split boundaries at least as long as the maximum look-ahead/holding window where trades overlap.
5. Use rolling walk-forward folds. Keep the final holdout sealed until the candidate and its parameter ranges are frozen.
6. Include fees, realistic spread and slippage on every fill; include funding for perpetual positions when a reliable historical series is available. Re-run at stressed costs (at least 1.5x and 2x base assumptions).
7. Test parameter neighbourhoods, alternate timeframes, long/short symmetry where relevant, and trending/ranging/high-volatility regimes. Report all tried variants to expose selection bias.
8. Use block/bootstrap confidence intervals for expectancy and drawdown; report sample size and trade clustering. A positive headline win rate alone is not evidence of an edge.
9. Reject candidates whose profitability depends on one fold, one regime, a narrow parameter point, missing costs, or a small sample. No candidate reaches production alerts until it survives untouched out-of-sample and robustness checks and is compared with visual-AI paper setups.

Initial screening floor (not proof of an edge): aim for at least 100 completed trades overall and 30 in each evaluated out-of-sample fold, across at least three walk-forward folds. If the market history cannot supply that sample, report the limitation rather than relaxing the standard.

## First implementation sequence

1. Bootstrap a sufficiently long, versioned OHLCV history for all three Delta contracts and six native timeframes using bounded, rate-limited historical requests. Record data coverage before any test.
2. Add deterministic data-quality and cost-model tests.
3. Implement a small event-driven research runner with no dependency on the visual AI. Make fill timing, same-bar SL-first handling, and fees explicit and unit-tested.
4. Implement one hypothesis family at a time; store every experiment and rejected variant.
5. Run chronological/walk-forward validation; compare surviving candidates with visual AI signals using the same instruments, time windows and net-cost assumptions.
6. Keep all research output separate from production signal generation until explicitly validated and reviewed.

## Handoff at 2026-11-04

- Branch: `ai-quant-rebuild`
- Draft PR: [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1) (open, not merged).
- Latest code commit when this note was authored: `c71bd2602a1f4847d29575bbdf272de22cda80c0`.
- Recent safety change: `state.py` now refuses to silently replace unreadable/corrupt state with an empty dictionary and writes state via an atomic temporary-file replacement. Regression tests were added to `test_visual_pipeline.py`.
- Follow-up verification: CI run [41886874010](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41886874010) completed successfully on 2026-11-04. Python compilation, the offline visual-pipeline suite (including the new state-persistence regressions), and the live public Delta OHLCV smoke test all passed.
- Repository head at this follow-up: `94e4df878a0930eaa9f9aca5c958c3e82cb64e46` on `ai-quant-rebuild`; PR #1 remains open, draft and unmerged.
- Next step: build the historical-data bootstrap and deterministic Quant Discovery harness. No historical experiment or strategy edge is claimed. Do not deploy, merge or enable live trading.

## Supervisor cycle — 2026-11-05

- Rechecked branch `ai-quant-rebuild` and draft PR #1. PR remains open, draft, mergeable, based on `main`, and unmerged.
- Fixed a paper-lifecycle timestamp mismatch: signal entry is assumed at the close of the latest closed 5m candle, but the tracker previously stored that candle's open timestamp. This made the 48-hour TIME exit five minutes early and excluded the first post-entry candle. `main.py` now stores the candle-close timestamp and includes the next candle whose open equals that entry time.
- Added regression coverage for the first post-entry candle. The existing late-TP-after-expiry regression remains in place to prevent post-expiry bars from changing a TIME exit.
- Commits: `d9f214d214a5b5c670c6a9d5fe8990fc9cdc82bd` (lifecycle fix), `68d3f7f24ee6e98df0651ec13a265c9fbb6129bc` (regression test).
- CI run [41903777179](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41903777179) completed successfully on code head `68d3f7f24ee6e98df0651ec13a265c9fbb6129bc`: dependency installation, Python compilation, the full offline visual-pipeline suite (including the new first-post-entry-candle regression), and live public Delta OHLCV smoke test all passed. The paired PR run [41903783790](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41903783790) also passed. The subsequent handoff-only commit `d5397e8fb49e4a197896f945801d637812464d9b` is now the branch head; its fresh CI run was in progress at this note update.
- Current architecture review: six Delta candle timeframes feed six-panel chart images and exact OHLCV context to the visual Responses API analyst. Multiple setup families remain in the prompt; old coded zone/scoring modules remain unused by `main.py`. Mechanical gates remain confidence >=75, R:R >=2, entry deviation <=0.35%, valid direction/levels, and one open paper position per symbol. Discord posts execution alerts only and separate TP/SL/TIME outcomes.
- Still unverified: real OpenAI API call/model access, Discord webhook delivery, authenticated Delta key check, persistent worker deployment. No live alert or order has been sent; no strategy performance claim is made.
- Next steps: verify CI for the new lifecycle regression; then build the bounded historical-data bootstrap and deterministic cost-aware Quant Discovery runner with chronological/walk-forward validation. Preserve missing historical spread/funding as explicit unavailable inputs; do not silently set them to zero.
