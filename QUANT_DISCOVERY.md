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

### Follow-up: entry-zone and Discord alert quality

- Added a strict selected_entry_zone object to the visual analyst output. For TRADE, the AI must identify one meaningful price band, source timeframe and evidence; for NO_TRADE it returns null.
- validate_trade now rejects missing/invalid zones and rejects a latest price more than the existing 0.35% tolerance away from the selected band. This is a validation gate only; the model still makes the visual setup decision.
- Discord execution alerts now show the selected entry band and optional Target 2 alongside entry, stop, Target 1, validated R:R, timeframe alignment, rationale and invalidation.
- Added tests for zone proximity rejection and Discord entry-band/TP2 formatting.
- Final code head 49d68876ff9b8aa6b5dcbe4aea0390f573f6aa46 passed both push CI [41904264877](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41904264877) and PR CI [41904271682](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41904271682), including compilation, offline visual-pipeline tests and live public Delta OHLCV smoke tests.
- Next: bootstrap durable historical OHLCV and implement the independent deterministic research runner. OpenAI live analysis, Discord webhook delivery, authenticated Delta check and persistent worker deployment remain unverified.


## Supervisor handoff — 2026-11-05 (latest code review)

- Rechecked private repository branch `ai-quant-rebuild`, draft PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1), current CI and PR feedback. PR #1 remains open, draft, unmerged, and targets `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. No review submissions or new inline review comments were present; the existing lifecycle review comment is addressed by the tests and code below.
- Fixed a data-gap edge case in paper trade expiry. The tracker now uses the last eligible candle close only when that candle closes exactly at the 48-hour expiry. If candles are missing near expiry, it uses the first observed post-expiry candle open; if no post-expiry price is available, it leaves the outcome unresolved rather than fabricating a stale exit price. It also handles the case where there are no eligible post-entry candles at all.
- Added regressions for: late TP after expiry remains TIME; first post-entry candle is included; no eligible candles then a post-expiry price closes TIME at that first open; pre-expiry data gaps do not close early; stale last eligible candles use the first post-expiry open; and expired positions remain unresolved when no post-expiry price is available.
- Commits on `ai-quant-rebuild`: `abc89da50de1fe187e6ee4cf0d5ab7a39a7f0001` (gap fallback), `03117391d4ced49f6063337e45f72986368bca2a` (initial regression tests), `9f929079b8b216d41b619be14a982d1d1066a3f9` (empty-window test fixture correction), `ec7db8f1cea79b647f7462e248851f67224d2921` (stale-candle-safe TIME exit), and `3bbf2ed6b55bfefb9eb1c183c1719c55ed16a9f9` (stale/missing-price regressions).
- Final code head `3bbf2ed6b55bfefb9eb1c183c1719c55ed16a9f9` passed push CI [41911224179](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41911224179) and PR CI [41911232009](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41911232009). The workflow completed dependency installation, Python compilation, the offline visual-pipeline suite (25 test functions), and the live public Delta OHLCV smoke test across all 18 symbol/timeframe combinations.
- Current architecture check: six native Delta timeframes per BTCUSD, ETHUSD and XAUTUSD feed six-panel chart images plus exact OHLCV context to the multimodal Responses API analyst. The prompt compares multiple setup families and can return NO_TRADE. The old coded zone/scoring engine remains outside the runtime decision path. Mechanical gates remain confidence >=75, minimum 2R, market-entry deviation <=0.35%, selected entry-zone validation, directionally valid levels and one open paper position per symbol. Discord remains execution-only with separate TP/SL/TIME outcomes.
- The schedule workflow remains gated by `ENABLE_GITHUB_SCHEDULE == 'true'`; manual dispatch is separate. No worker has been deployed and no live alert was sent. OpenAI API-key/model access, Discord webhook delivery and the authenticated Delta read-only check remain unverified. No order was placed and no strategy performance is claimed.
- Quant Discovery remains at protocol/design stage: no tracked historical dataset, no dedicated backtest runner, and no reproducible historical experiment yet. The live Delta smoke test proves current feed integrity only. Continuous history accumulation is not established until a persistent worker or a controlled data collection process is running. Historical spread/funding inputs remain unavailable and must not be silently set to zero.
- Exact stopping point: code head `3bbf2ed6b55bfefb9eb1c183c1719c55ed16a9f9`; PR #1 open/draft/unmerged; push and PR CI both green. Next safe work: implement bounded, rate-limited historical OHLCV bootstrap with hashes/coverage metadata, then a small event-driven cost-aware research runner and deterministic tests. Keep experiments separate from production alerts and retain the untouched chronological holdout.


## Supervisor verification — 2026-11-05 03:46 IST

- Rechecked branch and PR metadata through GitHub. Current PR #1 head is `41ddca230c6b69561e168a817bc6f073d02defec`; this commit changes only this handoff file (13 insertions, no code changes) relative to the previously tested code head `3bbf2ed6b55bfefb9eb1c183c1719c55ed16a9f9`.
- PR #1 remains open, draft, unmerged and mergeable; base is `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. No PR review submissions or inline review threads were returned.
- The latest PR-triggered GitHub Actions run on head `41ddca230c6b69561e168a817bc6f073d02defec`, run [41911359159](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41911359159), completed successfully. Job steps confirmed dependency installation, Python compilation, all offline visual-pipeline tests, and the public Delta OHLCV smoke test.
- The feed log checked all 18 instrument/timeframe combinations (BTCUSD, ETHUSD, XAUTUSD × 5m, 15m, 1h, 4h, 1d, 1w); closed-bar and freshness checks passed at the time of that CI run. This is a dated smoke test, not a live feed guarantee for later times.
- Current code review found no additional clear low-risk defect to change. Paper-trade expiry, state persistence, entry-zone validation, confidence/R:R/deviation gates, visual multi-setup prompt, and execution/outcome Discord formatting remain as previously tested. No code thresholds or live-trading controls were changed.
- Runtime limitation remains: no worker is deployed and the repository does not contain current chart-image artifacts for this cycle. Therefore no fresh AI visual analysis or market setup was evaluated, and no Discord alert was sent.
- Quant Discovery remains design-only: no tracked historical dataset, no dedicated experiment/backtest runner and no completed historical experiment. The next engineering task remains bounded historical OHLCV bootstrap with coverage/hash metadata, followed by a deterministic event-driven backtester with realistic costs and chronological/walk-forward validation.
- No deployment, secret change, merge, live order or performance claim was made.


## Supervisor verification — 2026-11-05 (symbol coverage guard)

- Rechecked the current private-repository branch and PR #1 through GitHub. Latest code head: `81659436a4b394027085014a7db2a9f9f3aefd6b` on `ai-quant-rebuild`. PR #1 remains open, draft, unmerged, and mergeable; base is `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. No review submissions or inline review threads were present.
- Found a response-validation edge case in `ai_analyst.py`: set comparison accepted duplicate model analyses if every expected symbol was also present (for example BTC, BTC, ETH for BTC/ETH). Added `_validate_symbol_coverage` to require exactly one well-formed analysis per requested symbol and reject duplicates, missing symbols, unexpected symbols, or malformed symbol entries.
- Added offline regression tests for exact one-per-symbol acceptance and duplicate-symbol rejection.
- Commits: `04890d0d8233512fb6059c114ee54a9e848da6cd` (guard), `81659436a4b394027085014a7db2a9f9f3aefd6b` (tests).
- Final code head CI run [41927585515](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41927585515) completed successfully: dependency installation, Python compilation, all offline visual-pipeline tests including both new symbol-coverage regressions, and live public Delta OHLCV checks for all 18 BTCUSD/ETHUSD/XAUTUSD × six-timeframe combinations passed.
- Visual-first architecture, multi-setup prompt, NO_TRADE option, selected-entry-zone gate, confidence >=75, minimum 2R, 0.35% market-entry deviation, one open paper position per symbol, and TP/SL/TIME lifecycle remain unchanged. No coded zone engine was reintroduced and no thresholds were weakened.
- Runtime remains undeployed: no persistent worker or fresh chart images were available for this cycle; actual OpenAI chart analysis and Discord delivery remain unverified. No alert or order was sent.
- Quant Discovery remains at protocol stage: no tracked historical OHLCV archive, dedicated backtest runner, or completed experiment. Current public-feed smoke checks prove current candle availability/integrity only. Historical spread/funding inputs remain unavailable and must not be silently set to zero.
- Exact next steps: bootstrap bounded, rate-limited historical Delta OHLCV with per-file hashes and coverage metadata; test data integrity and missing intervals; then implement the deterministic event-driven cost-aware research runner with chronological splits, purge/embargo and walk-forward folds. Keep research candidates out of production alerts until untouched out-of-sample and robustness checks pass.
- No deployment, secret change, merge, live order, or performance claim was made.

## Supervisor verification — 2026-11-05 (OHLCV integrity guard)

- Latest verified code head: `e68c05646f202fcf876dc48a98d650fa893d5ee2` on `ai-quant-rebuild`. Draft PR #1 remains open, draft, mergeable, and unmerged; base `main` remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- Code review found that `data.normalize()` previously converted values to numeric and dropped missing OHLC rows, but did not reject infinite/non-positive prices, inconsistent high/low ranges, or negative/non-finite volume. Missing volume values could also remain NaN in model context.
- Updated normalization to discard NaT timestamps, require finite positive OHLC values with internally consistent high/low, represent missing volume explicitly as zero, and reject non-finite or negative volume. Malformed feed/cache data now fails closed and can fall back only to a separately validated fresh cache.
- Commits: `60bd706435ddffa3e55bc01b4992e4fcb89913f5` (normalization guard) and `e68c05646f202fcf876dc48a98d650fa893d5ee2` (regression tests).
- Latest PR CI [41933836886](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41933836886) completed successfully: dependency install, Python compilation, 29 offline test functions, and public Delta smoke checks for all 18 BTCUSD/ETHUSD/XAUTUSD × six-timeframe combinations.
- The live feed smoke test at 2026-11-04 23:27 UTC confirmed closed-bar, timestamp, OHLC-integrity and freshness checks. It is a dated integration check, not a historical strategy backtest or a guarantee of later feed availability.
- No new chart images or worker runtime were available. No fresh visual AI analysis was performed and no Discord alert was sent. OpenAI API access, Discord webhook delivery, authenticated Delta access and deployment remain unverified.
- Quant Discovery remains at protocol stage: no tracked long-term OHLCV archive, dedicated backtest runner, or completed experiment. Do not infer strategy performance from feed checks.
- Next steps: bootstrap bounded historical Delta OHLCV with coverage/hash metadata; preserve contract/timeframe provenance; add deterministic gap and cost-model tests; then implement the event-driven backtester with explicit next-bar fills, fees/spread/slippage/funding flags, chronological splits, purge/embargo and walk-forward folds. Keep all candidates out of production alerts until untouched out-of-sample and robustness checks pass.
- No deployment, secret change, merge, live order, threshold change, or performance claim was made.

## Supervisor cycle — 2026-11-05 05:53 IST

- Branch: `ai-quant-rebuild`; draft PR #1 remains open, unmerged, and targets `main`.
- Latest code change: `053c730f96abfdb19b0ee91732b9d8091f9302ff` adds finite-number guards to required trade prices, current price, entry-zone bounds, and optional TP2 handling. This closes a validation edge case where NaN comparisons could bypass the entry-deviation check and an infinite zone bound could be accepted.
- Regression tests: `8a8caa54c1d16a0993b89630570f5375178a2d19` adds two offline tests covering non-finite required prices/zone bounds and ignoring a non-finite optional second target.
- Baseline CI on the preceding head `b34add5c44150590846f23a0d7ed139cfbdc85ac` passed in run [41933934867](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41933934867): compilation, 29 offline test functions, and live public Delta OHLCV checks for all 18 instrument/timeframe combinations. The new code/test commits triggered a fresh CI run; its result must be checked before treating these changes as verified.
- Current architecture remains visual-first; old coded zone/scoring modules are not the decision path. Confidence, minimum R:R, entry-deviation and single-open-position controls were not weakened.
- No running worker or production chart images were available in this cycle. OpenAI API access, Discord delivery, authenticated Delta access and deployment remain unverified; no alert/order was sent.
- Quant Discovery remains design-only: no tracked long-term historical archive, dedicated deterministic backtest runner, or completed experiment. Next step is bounded historical OHLCV bootstrap with coverage/hash metadata, followed by cost-aware event-driven backtesting and chronological walk-forward validation.
- Safety constraints unchanged: do not modify `main`, merge PR #1, deploy, change secrets, enable live trading, or place orders.

## Supervisor follow-up — 2026-11-05 05:57 IST

- Code safety fix: `053c730f96abfdb19b0ee91732b9d8091f9302ff` rejects NaN/Infinity in required entry, stop, target, current price and selected entry-zone bounds; non-finite optional TP2 is discarded.
- Regression coverage: `8a8caa54c1d16a0993b89630570f5375178a2d19` added two tests. A first CI inspection revealed the script's test-discovery block had been placed before those appended functions, so they were not executed by the script runner. `81b3ff65691a4948130187dd4a1ea1b45c2be3fc` moved the runner to the end; CI then executed 31 tests successfully.
- Security fix: `1f64a9dcb97ccea9a3ff5e3c61a16ba5426a80f9` prevents Discord request exceptions from printing raw exception text, which can contain a webhook URL. Regression test `9b37043f829d3aacd12a0d97821efa20567c5383` confirms the dummy webhook URL is absent from failure logs.
- Final verified code CI: [run 41941317350](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41941317350) completed successfully on code head `9b37043f829d3aacd12a0d97821efa20567c5383`. Compilation passed; all 32 offline tests passed, including both non-finite-price regressions and webhook-secret redaction; the public Delta feed smoke test passed all 18 BTC/ETH/XAUT × six-timeframe combinations.
- PR #1 was rechecked as open, draft, unmerged and mergeable; base `main` remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. No main-branch changes, merge, deployment, secret mutation, live trading or order placement.
- Visual-first pipeline, multiple setup-family comparison, NO_TRADE option, confidence >=75, minimum 2R, entry deviation <=0.35%, selected entry-zone requirement and one-open-position-per-symbol guard remain unchanged.
- No persistent worker or production chart images are available in this cycle; OpenAI API access, Discord delivery and authenticated Delta access remain unverified. No execution alert was sent.
- Quant Discovery remains research design only: no tracked long-term historical archive, dedicated backtest runner or completed experiment. Continue with historical OHLCV bootstrap, coverage/hash checks, then a deterministic cost-aware event-driven backtester with chronological and walk-forward validation.


## Quant Discovery implementation — historical archive bootstrap (2026-11-05)

### Implemented on ai-quant-rebuild

- Added `bootstrap_historical_data.py`, a standalone, credential-free historical traded-price OHLCV collector for Delta India contracts BTCUSD, ETHUSD and XAUTUSD across 5m, 15m, 1h, 4h, 1d and 1w.
- Uses `GET /v2/history/candles` in bounded adjacent time windows. Each request respects Delta's documented 2,000-candle cap. The collector runs sequentially with a conservative inter-request delay and bounded exponential backoff for HTTP 429, 5xx and transient request failures.
- Default collection window is three years, configurable through `--years` or explicit `--start` / `--end`. Symbol and timeframe subsets can be selected for a small pilot.
- Each symbol/timeframe is downloaded into temporary chunk files. A progress checkpoint is atomically updated after each successful chunk, so reruns resume after interruption. Completed files are skipped only when request bounds match and the stored SHA-256 verifies.
- Strict parsing rejects unsuccessful API responses, missing required candle fields, invalid timestamps, non-finite/non-positive prices, inconsistent OHLC, negative/non-finite volume, and responses larger than the configured cap. Missing volume is made explicit as zero and counted in the manifest; no missing price bars are synthesized.
- Final CSVs are atomically published under `historical_data/`. `manifest.json` records contract, venue, timeframe, requested and observed bounds, row count, duplicate removal count, empty request windows, volume defaults, request count and file SHA-256. `coverage.csv` reports requested-range coverage and observed-span missing bars/gaps, including the largest gap.
- Added an inclusive chunk-end regression test after review of boundary semantics, plus offline tests for chunk caps, response validation, 429 retry handling, checkpoint resume, SHA-256, and coverage reporting.
- `historical_data/` is Git-ignored intentionally. The raw dataset must live on durable local or mounted storage and be backed up; it is not committed to the source repository or treated as an ephemeral CI artifact.
- README now documents the exact collection commands and output format.

### GitHub commits

- `73e39202da9aaa00915ae33ffc3539a95a98e5de` — add resumable historical OHLCV bootstrap.
- `ebf7a5b78ef33958d7433a88742afd9025cdb253` — include inclusive candle request end boundaries.
- `af56ee69e8a8b3d0044cca74ede3a61aac452005` — test inclusive chunk-end candle handling.
- `09495fae0928d1d4c28d64043ed7eabe838502a8` — report both requested-range and observed-span coverage.
- `231d5a853455812317f82ee7406dc9755b388a53` — assert coverage metrics in offline archive test.
- `d71be2543d15a1fcffe98ce31a2ef31f258741f4` — Git-ignore local historical archives.
- `172d0f811b06ffb9b060ab4788758ef6d35700d1` — document archive workflow in README.

### Verification status and limits

- The collector has offline regression coverage but has **not yet run a full three-year collection**. No historical dataset, market coverage result, or strategy performance is being claimed at this point.
- CI will verify Python compilation and the new offline tests. The existing public-feed smoke test is a separate short-window availability/integrity check, not proof of long-range history completeness.
- This first version archives traded-price OHLCV only. It does not collect funding history, mark-price candles, order-book depth, spread or executable bid/ask history. Those cost inputs must not be set to zero in future backtests; extend the archive only after the corresponding public series is checked and validated.
- The three-year default is a configurable bootstrap starting point, not an assertion that every contract/timeframe has three years of available history. The coverage report must reveal actual history and gaps for each contract.
- No persistent worker was deployed. The archive should be run from the user's durable machine/storage after pulling this branch, beginning with the small pilot command in README, then the full three-year run. Keep the raw archive out of Git.
- Once the archive is produced, inspect all 18 datasets' first/last timestamps, requested coverage, observed gaps, duplicates and hashes. Resolve coverage anomalies before implementing backtests. The next code milestone is a deterministic event-driven replay harness with explicit next-bar fills, conservative same-bar SL-first handling, fee/slippage assumptions, explicit unavailable funding/spread flags, chronological splits, purge/embargo and walk-forward folds.


## Historical archive bootstrap — verification handoff (2026-11-05)

- Latest branch head at this handoff: `f47f4d5a84503924eb9279507448577deda53b65` on `ai-quant-rebuild`.
- PR #1 remains open, draft, unmerged and mergeable; base `main` is still `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. The `main` branch SHA was rechecked and is unchanged.
- Historical collector: `bootstrap_historical_data.py`. README documents the local pilot and full run commands. Raw output folder `historical_data/` is Git-ignored.
- The initial CI run exposed a missing argument in the new coverage-metric call; this was corrected. A follow-up test caught the coverage CSV index label and it was corrected so `dataset_key` remains a normal column. The duration-based requested-range coverage field is explicitly labelled as an estimate. Permanent HTTP 4xx errors now fail immediately rather than being retried; 429/5xx and transient network failures retain bounded retry/backoff.
- Current final CI passed on head `f47f4d5`: push run [41951014739](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41951014739) and PR run [41951021653](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41951021653). The PR workflow completed Python compilation, all 38 offline tests, the existing public-feed smoke test for all 18 instrument/timeframe combinations, and the new live historical-archive pilot.
- Live historical pilot: CI downloaded BTCUSD 5m candles for the configured 0.01-year window (approximately 3.65 days), wrote a CSV, manifest and coverage report in the runner's temporary directory, and reported 1,052 candles, 100.0% estimated requested coverage, zero observed gaps, and SHA-256 prefix `d2ac41e68c42`. This proves that the new downloader works end-to-end against the public historical endpoint for a small sample. The runner's temporary output was not retained as the research archive.
- This is not the full dataset. No three-year 18-series archive has yet been downloaded to durable storage, and no historical strategy experiment has been run.
- Delta's current API documentation states that the historical candle endpoint supports up to 2,000 candles per response and also describes funding, mark-price and open-interest series using `FUNDING:<symbol>`, `MARK:<symbol>` and `OI:<symbol>`. These series are not included in the first traded-price OHLCV collector and have not yet been independently validated. Extend after baseline OHLCV is secured. Historical bid/ask spread and order-book depth remain uncollected.
- Exact next user action after pulling the latest branch: first run the README pilot locally and inspect the CSV/manifest/coverage output; then run `python bootstrap_historical_data.py --years 3` on durable local or mounted storage. Do not commit raw CSVs. On completion, review all 18 datasets for first/last timestamps, estimated requested coverage, observed gap counts, missing bars, duplicate removal counts, volume defaults and SHA-256 before writing the backtester.
- Next engineering milestone after archive review: deterministic event-driven replay/backtesting with next-bar executable fills, same-bar SL-first ambiguity handling, fee and slippage assumptions, explicit funding availability, chronological train/validation/test boundaries, purge/embargo and walk-forward folds. No candidate may enter production alert logic before untouched OOS and robustness validation.


## Final session handoff — 2026-11-05

- Latest verified code/test commit: `dbae5323eca5645b66d0a511c42b30697b277ca7`.
- Latest push CI [41951280121](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41951280121) and PR CI [41951285956](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41951285956) both passed on that code/test head.
- The final PR workflow passed 40 offline test functions, Python compilation, the live Delta feed smoke test across 18 symbol/timeframe combinations, and the new historical-download pilot. The pilot returned 1,052 BTCUSD 5m candles for the 0.01-year window, 100.0% duration-estimated requested coverage, zero observed gaps, and SHA-256 prefix `99c8826490f2`. Its files were in the ephemeral runner temp folder and were not retained.
- The latest branch was `ai-quant-rebuild`; PR #1 remained open, draft, unmerged and mergeable. Base `main` remained at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- The collector is implemented and CI smoke-tested; the full three-year, 18-dataset archive has **not** been produced. No backtest or edge claim exists.
- Next user action: pull `ai-quant-rebuild`, run `python bootstrap_historical_data.py --years 0.1 --symbols BTC --timeframes 5m 1h` as a local pilot, inspect `historical_data/manifest.json` and `coverage.csv`, then run `python bootstrap_historical_data.py --years 3` on durable storage. Keep `historical_data/` out of Git.
- After collection, validate all 18 datasets and investigate any low estimated requested coverage or observed gaps. Funding/mark/open-interest candles are documented as queryable using prefixed symbols but are not part of this first collector; validate them in a separate extension. Spread/order-book depth is still missing. Then implement the event-driven backtester with realistic executable fills/costs, chronological splits and walk-forward tests.
