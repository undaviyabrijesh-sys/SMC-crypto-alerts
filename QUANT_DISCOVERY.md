# Quant Discovery — Research Protocol and Handoff

Status: EXP-001 completed and rejected as an edge; the end-of-data replay boundary was corrected and the full screen re-run on 2026-11-05. No candidate is approved for production.

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


## Supervisor update — 2026-11-05 07:46 IST

- Latest reviewed production branch at start of this run was ai-quant-rebuild head c9b5368c405d74db49bc2bc9853497f665176970; PR #1 remained open, draft, unmerged and mergeable. It was 144 commits ahead of main, 0 behind. Base main remained e93ee289b36d47ca774e9a285fc76a2f4cbb5795.
- Latest CI on the reviewed head completed successfully (run 41953198199). Python compilation, all existing visual-pipeline tests, all 18 public Delta OHLCV symbol/timeframe feed checks and the historical-download pilot passed.
- The historical archive now exists in the ChatGPT Library as salty_quant_historical_ohlcv_3y_verified.zip; it was not present in the earlier repo-only handoffs. It contains 18 validated traded-price OHLCV datasets and 926,209 candles. Actual history is BTC from 2023-12-29, ETH from 2024-02-06, and XAUTUSD from 2026-04-17 only. The latter is about 6.6 months, not three years. BTC/ETH have notable historical gaps; no candles were filled. The archive SHA-256 is 07db78359920ceec6331a8f96642406543516cb12a78a1ca90099f90eb6bb9d5.
- Added an independent quant_discovery/ workstream. initial_screen.py validates all 18 manifest hashes and row counts, runs five fixed candidate families on 15m/1h BTC/ETH/XAU, and writes OOS, cost, regime, parameter-robustness and walk-forward CSVs. It never imports or changes production alert logic.
- EXP001_INITIAL_SCREEN.md records the experiment protocol and results. At 10 bps round-trip fee/spread/slippage scenario plus 1 bp/8h adverse funding stress, all 30 asset/timeframe/strategy OOS cells were negative. The least-negative result was BTC 1h mean reversion at -0.0149R, PF 0.978, 176 trades. The 270 stop/target sensitivity combinations were also negative at this cost assumption. A post-hoc ETH 15m volatility-expansion/downtrend slice was positive in validation and OOS, but is not pre-registered, flips negative at 20 bps, and remains an unvalidated hypothesis. No research candidate is promoted to production.
- The archive lacks historical funding, mark/index, spread, order-book depth and executable fills. Backtests therefore use explicitly labelled cost/funding stress scenarios, not claims of exact historical execution. Gold coverage is too short for long-horizon conclusions.
- Added four offline Quant Discovery tests for higher-timeframe close alignment, next-bar entry, same-bar SL-first handling, split-boundary censoring and cost sensitivity (four test functions). CI was extended to run them alongside the existing suite.
- New research commits: 472b138771868006b2f562e7ce027575b56aef70 (screen), 89afe0b6db0d177e193d827023e3eccfc865ec9a (tests), 1fb57e4de10dfbe786f11b9b41dec6c52cc6cfcf (experiment report). CI verification follow-up: run 41955307668 on head 94075af13e543b562a3bdcbac97ef448d8bd2b6d completed successfully; compile, visual-pipeline tests, quant-backtest tests, Quant Discovery tests, all 18 live feed checks and the historical archive pilot passed. The immediately preceding run 41955221023 exposed an uncounted final-bar signal; commit 94075af fixed the skipped-entry counter and the rerun passed.
- Current next steps: cross-check EXP-001 against quant_backtest.py. That generic engine models per-side fees/slippage but explicitly excludes funding, spread/depth, contract multipliers, margin/liquidation and has no explicit time-stop; reconcile fill and cost semantics before treating the two engines as equivalent. Obtain historical funding/mark and defensible spread/slippage proxies; pre-register and retest the ETH 15m volatility-expansion/downtrend hypothesis on additional untouched windows and instruments; compare any validated candidates against visual-AI outcomes. Keep the chart-first multi-setup analyst and all production thresholds unchanged.
- No production worker, real chart cycle, OpenAI analysis, Discord delivery, authenticated account, order or deployment was exercised. No order was placed. Main was not modified and PR #1 was not merged.



## Supervisor handoff — 2026-11-05 08:04 IST

### Repository and verification

- Branch: `ai-quant-rebuild`; current code/test head before this handoff: `7f544c5744ffb421ad770d0aff8e9f00d458fea2`.
- PR #1 remains open, draft, unmerged and mergeable. It targets `main`; main remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. The branch is 173 commits ahead and 0 behind.
- Latest push CI [41955994996](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955994996) and PR CI [41956002630](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41956002630) passed on head `7f544c5`.
- The workflow compiled all Python modules; passed visual-pipeline tests, 17 generic replay tests, 7 derivative-probe tests, 7 derivatives-archive tests and 4 Quant Discovery tests; checked all 18 BTC/ETH/XAUT OHLCV symbol/timeframe combinations; checked the derivative series; and completed the small historical OHLCV pilot.
- No recent production visual-desk/alerts workflow run was found. No live worker, chart-to-AI call, Discord delivery, authenticated Delta account check or exchange order was exercised. The scheduled alerts workflow remains opt-in through `ENABLE_GITHUB_SCHEDULE=true`; do not enable it as part of research.

### Historical funding / mark / open-interest discovery

- The public Delta India historical candle endpoint returned usable three-day samples for all nine expected series:
  - Funding, `FUNDING:<contract>`, 1h: BTC 67, ETH 67, XAUT 71 candles.
  - Mark price, `MARK:<contract>`, 5m: 864 candles per contract.
  - Open interest, `OI:<contract>`, 1h: 72 candles per contract.
- The probe parser preserves negative funding values and raw API units. These counts establish short-window endpoint availability only; they do not establish multi-year history, funding-rate scaling/sign conventions, or executable spread.
- Added `bootstrap_derivatives_history.py` for resumable, bounded, chunked downloads of nine series, with CSVs, a manifest, SHA-256 hashes and coverage/gap metrics. Added `test_bootstrap_derivatives_history.py` and the one-time `.github/workflows/derivatives-archive.yml`.
- The one-time workflow is guarded: it runs only by manual workflow dispatch or a commit whose message begins `RUN_DERIVATIVES_ARCHIVE:`. It has **not** been dispatched. It retains a verified or partial archive as a 14-day Actions artifact and does not commit raw data.
- Safety/quality fixes on this branch: the three-day probe now requires every symbol/series pair to be present and non-empty; resume checkpoints must align to the series candle boundary; the archive workflow rejects empty datasets even if all nine filenames and hashes exist. Regression tests cover complete probe coverage and checkpoint alignment.
- Relevant commits: `16b21fab6599152cac06541c32b3026ae42b595f`, `7b654320ff8b3c241beed788739e3bc0a463f793`, `942b39e154f12de823ae6bd68d4f231258da266e`, `01a1923a8b17e426c82f6506031a1e9bd145393a`, and `7f544c5744ffb421ad770d0aff8e9f00d458fea2`.

### Research interpretation and exact next steps

- The existing EXP-001 conclusions remain unchanged: all 30 baseline OOS combinations were negative at the stated 10 bps combined round-trip cost scenario plus 1 bp per 8 hours funding stress. No candidate is an edge and none is routed to production.
- Do not apply funding to a backtest until raw series units, sign convention, actual funding-event timestamps and contract-specific payment semantics are independently confirmed. Keep missing spread/depth explicit; do not set them to zero.
- The generic `quant_backtest.py` engine and EXP-001 `initial_screen.py` are not yet equivalent: the generic engine has per-side fee/slippage inputs but no explicit time-stop or funding-event accounting; EXP-001 uses a 24-hour time stop and combined cost/funding stress. Reconcile next-bar fills, target/stop gap handling, fees, funding, end-of-data treatment and drawdown definitions before cross-validating or comparing their reported metrics.
- Next operator action: manually run GitHub Actions workflow **Derivatives history archive (one-time)** on `ai-quant-rebuild`, or run `python bootstrap_derivatives_history.py --years 3 --output-dir derivatives_history` on durable storage. Then inspect all nine series' actual first/last timestamps, empty chunks, gaps, cadence, row counts and hashes; do not assume three years are available.
- After the derivative archive is verified, implement event-time funding attribution and mark-price valuation in the research replay, add defensible spread/slippage scenarios, and run chronological/walk-forward validation. Pre-register the ETH 15m volatility-expansion/downtrend hypothesis before further testing; do not reuse its already-observed OOS slice as fresh holdout data.
- Keep the visual-first multi-setup AI analyst and all production thresholds unchanged. No deployment, secret mutation, merge, live trading or order placement was performed.



## Supervisor update — 2026-11-05 08:12 IST

### Three-year derivatives archive completed

- The guarded one-time GitHub Actions workflow completed successfully: [run 41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516).
- It verified nine non-empty series and their manifest SHA-256 values, with **758,119 candles total**. The compressed artifact is 16,854,903 bytes, artifact ID `13383865992`, ZIP digest `sha256:f16d0bc18eddcce7637c9643d9176590c8bb55fe9de6be1da9c717bdf7949a27`; retention expires **2026-11-19 02:37:57 UTC**. Download it from the run's Artifacts section and move it to durable storage before expiry.
- Dataset results (requested-range coverage is a duration estimate; observed-span coverage is measured only between the first and last observed candle):

| Series | Rows | Requested coverage | Observed-span coverage | Gaps | Largest gap |
|---|---:|---:|---:|---:|---:|
| BTC funding 1h | 25,170 | 95.7107% | 99.6398% | 13 | 8h |
| BTC mark 5m | 303,136 | 96.0580% | 100.0000% | 0 | 0 |
| BTC open interest 1h | 24,961 | 94.9160% | 99.8560% | 1 | 37h |
| ETH funding 1h | 24,002 | 91.2693% | 99.6512% | 12 | 8h |
| ETH mark 5m | 289,038 | 91.5906% | 100.0000% | 0 | 0 |
| ETH open interest 1h | 24,066 | 91.5127% | 100.0000% | 0 | 0 |
| XAUT funding 1h | 4,829 | 18.3626% | 99.8140% | 3 | 4h |
| XAUT mark 5m | 58,077 | 18.4035% | 100.0000% | 0 | 0 |
| XAUT open interest 1h | 4,840 | 18.4044% | 100.0000% | 0 | 0 |

- Actual first-candle timestamps confirm different listing histories: BTC starts 2023-12-18 (OI 2023-12-29); ETH starts 2024-02-05/06; XAUT starts 2026-04-17. All series end at 2026-11-05 UTC in the archive. XAUT's roughly 6.6-month history remains insufficient for three-year conclusions.
- The artifact came from the first collector workflow run on commit `b85a522`, before the later resume-alignment and empty-dataset validation hardening. All nine resulting datasets were non-empty and the workflow's SHA checks passed. The current branch has the additional checkpoint-alignment regression test and rejects empty archive datasets on future runs.
- The three-day API probe and the full archive establish endpoint availability and file integrity, not the meaning/sign of funding payments, funding settlement timing, or executable bid/ask spread. Keep those semantic checks open; do not feed funding into PnL until they are verified.

### Runtime validation and alert policy

- The first one-cycle push validation [run 41956553584](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41956553584) failed before AI analysis because the OpenAI secret contained outer whitespace in its HTTP header. The client now trims outer whitespace and rejects embedded whitespace/non-ASCII without logging the value; credential-format regression tests were added.
- A later one-cycle run [41956757056](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41956757056) passed header preparation and reached the OpenAI API, which returned HTTP 429 `insufficient_quota / credit_balance_exhausted`. No AI analysis or new execution alert was produced. **User action:** add OpenAI API credits or configure a key with available API quota at https://platform.openai.com/settings/organization/billing/; the ChatGPT subscription is separate from API billing.
- Daily P&L summaries conflict with the execution-only Discord preference. They are now opt-in in code and explicitly disabled in `.env.example`, `compose.yaml` and GitHub Actions (`ENABLE_DAILY_PNL_REPORT=false`). The helper remains dormant unless explicitly enabled. The README now documents execution alerts plus confirmed TP/SL/TIME updates as the default.
- The accidental push trigger on `.github/workflows/alerts.yml` / `ai_analyst.py` was removed. The visual-desk workflow now runs only by manual dispatch or when the opt-in repository variable `ENABLE_GITHUB_SCHEDULE=true` is set. Do not set that variable while the persistent Docker worker is running.
- During the two push validation attempts, daily reporting was still enabled in the workflow configuration. Because it executes before the AI call, a daily summary may have been posted; the workflow logs do not expose webhook delivery success, so delivery cannot be confirmed. Future runs have the setting disabled.
- No broker/exchange order was placed, no live trading was enabled, no secrets were changed, and no infrastructure was deployed.

### Current handoff and next actions

- Latest branch head at this handoff: `55cabb049fb13c9b5c2f6ad3537d28fc996f10bc` on `ai-quant-rebuild`; PR #1 remains open, draft, unmerged and mergeable, based on unchanged `main` `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. Latest CI for this head is still running at handoff; re-check its push and PR runs before further code changes.
- First user action: download artifact `salty-quant-derivatives-3y-41955898516` from the linked Actions run before its 14-day expiry and store it durably.
- Second user action: add OpenAI API credits / a valid quota-bearing key. Then manually dispatch the visual-desk workflow for one paper-only validation cycle; do not enable the scheduled variable by default.
- After the artifact is available in the research runtime, validate all nine raw CSVs and their hashes again, inspect funding units/sign/settlement timestamps, then implement event-time funding attribution and mark-price valuation. Keep spread/depth as explicit missing/stress scenarios until defensible proxies exist.
- Reconcile `quant_backtest.py` with EXP-001 before comparing results: align next-bar fills, gap and same-bar stop/target handling, 24-hour time exit, fee/slippage accounting, funding events and drawdown definitions. No new strategy performance claim is made from this archive.
- The EXP-001 rejection still stands. Live setup feedback is observational tie-breaker context only; no unvalidated research candidate enters production. Keep the visual-first multi-setup analyst and all risk thresholds unchanged.



## Final verification handoff — 2026-11-05 08:17 IST

- Latest code/test head: `e1a333e58eed83a5ae3ae9a25eb34fa1c72f586f`; final documentation-only handoff commit: `287a516c892dfb59c926a17d258dfea09a34eaca`.
- Latest push CI [41957057304](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41957057304) and PR CI [41957064310](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41957064310) both completed successfully on the final handoff commit.
- The verified CI steps include compilation; visual pipeline; generic replay; daily-report opt-in; setup-feedback; OpenAI secret-format; derivatives parser/archive; Quant Discovery tests; 18 public Delta OHLCV checks; nine-series funding/mark/OI probe; and the short historical OHLCV pilot.
- PR #1 is still open, draft, unmerged and mergeable; base `main` remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. The branch is 203 commits ahead and 0 behind. No changes were made to `main`.
- The alerts workflow push trigger has been removed. Since that change, no new `salty-quant-visual-desk` push run has been started. The workflow is manual-dispatch only unless the repository's explicit schedule variable is enabled.
- Daily P&L reporting is disabled in both supplied runtime configurations and the example environment. Keep it disabled unless the user explicitly changes the execution-only Discord preference.
- The OpenAI API quota blocker remains: the latest real request returned HTTP 429 `insufficient_quota / credit_balance_exhausted`. The API key header-format issue is handled and regression-tested; no secret was changed. Do not keep retrying until API credits are restored.
- The three-year derivatives archive artifact is available from [run 41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516), artifact ID `13383865992`, expiring 2026-11-19 02:37:57 UTC. It contains 758,119 candles across nine datasets and passed the archive workflow's hash checks. Download it before expiry and retain it durably.
- Next work is research-only: extract and independently revalidate that artifact, confirm funding units/sign/payment timestamps, then reconcile funding-aware replay and execution costs with EXP-001. The fixed-rule OOS rejection remains in force; no setup is promoted.

## DNS-first visual AI workstream — 2026-11-05

- User direction: make demand and supply the primary visual setup framework; evaluate SMC/liquidity, trend pullback, FVG, RBS/SBR, breakout/retest, momentum, range and mean-reversion only as subordinate confirmations/refinements at a valid DNS zone.
- Branch implementation: `ai_analyst.py` now prompts the vision model to visually map demand/supply bands from the raw six-timeframe chart images and to return timeframe, bounds, evidence and 1–5 quality. Mid-range standalone setups are not eligible. All trade candidates must be anchored to relevant demand (LONG) or supply (SHORT).
- `main.py` has a mechanical DNS gate: selected entry band must overlap the correct-side AI zone, minimum quality 3/5, and remain inside the pre-existing current-price tolerance. Confidence >=75, first target >=2R, market-entry freshness, SL/TP order, and one open paper position remain unchanged.
- `visual_chart.py` can render post-response AI annotations onto the matching timeframe panel: demand green, supply red, selected entry band yellow dashed. It preserves the price scale and does not infer zones algorithmically.
- Paired evidence is atomically saved for each successful cycle: `<SYMBOL>_raw.png` (exact image sent to AI) and `<SYMBOL>_latest.png` (AI DNS overlay). The JSONL log records both paths and SHA-256/byte metadata. Docker data volume retains these images; the GitHub Alerts workflow uploads them as a seven-day artifact when available.
- Discord execution messages now include the primary DNS side, timeframe, band and quality alongside the selected entry band, sub-setup, entry/SL/targets, RR, rationale and invalidation. No WATCH/status spam is added.
- Tests were added for overlay rendering on matching panels, atomic paired image saving and hashes, directional demand/supply requirements, quality floor, selected-band overlap, and Discord DNS formatting.
- CI passed on head `a90d3b965a769293ced5f051053fccdd056d581c`: [run 41957860056](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41957860056). All offline visual tests, replay/report/feedback/secret tests, derivatives/archive and Quant Discovery tests, 18 live OHLCV checks, funding/mark/OI probe and historical download pilot passed.
- PR #1 remains open, draft, unmerged and mergeable. At the above verified head it was 218 commits ahead and 0 behind; base `main` remained `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. No main changes, merge, deployment, secret changes, live trading or orders.
- Critical verification blocker: latest actual OpenAI Responses call returned HTTP 429 `insufficient_quota / credit_balance_exhausted`. Thus the code path and synthetic annotation tests pass, but there is no new live visual-AI DNS drawing to judge for mapping accuracy. Restore OpenAI API quota first; then manually dispatch one paper-only visual-desk cycle, download paired chart artifacts, manually inspect the zones, and track subsequent paper outcomes. Do not enable the recurring schedule, lower thresholds, or claim an edge until real charts and sufficient outcomes are audited.


## Supervisor handoff — 2026-11-05 09:00 IST

### Repository and CI

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts`; working branch: `ai-quant-rebuild`.
- Code/test commit: `2a3d3dae189c673bc446743cb3a5de6cea1a22f7` — fixes the Quant Discovery end-of-data boundary, adds its regression test, documents the DNS timeframe-specific refresh rule, and tests that a 1h close cannot invalidate a 4h zone.
- PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1) is still open, draft, unmerged and mergeable. It targets unchanged `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`; the branch is 243 commits ahead and 0 behind. No main-branch changes.
- Push CI for the code/test commit is running: [run 41963789721](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41963789721). The prior head `3c196a6` passed both push CI [41959335546](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41959335546) and PR CI [41959341346](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41959341346), including offline visual/DNS/replay/report/feedback/derivatives/Quant Discovery tests, all 18 live public Delta OHLCV checks, the funding/mark/OI probe, and the small historical OHLCV pilot. Re-check the new push and PR runs before the next code change.
- The latest `salty-quant-visual-desk` workflow has no recent run. Its schedule remains gated by the explicit `ENABLE_GITHUB_SCHEDULE=true` repository variable; do not enable it while no deployment/runtime coordination has been established.

### Visual pipeline, alerting and risk review

- The active container path is `Dockerfile → worker.py → dns_worker.py`. The active worker uses `ai_analyst.map_dns()` to create visual maps only, then `dns_engine.detect_local_setup()` emits only `DNS_LIQUIDITY_SWEEP_RECLAIM` candidates. The broad multi-setup `ai_analyst.analyse()` path in `main.py` is not called by this active worker. The map-only prompt also does not return a comparison of candidate setup families. **Therefore the requested multi-setup visual candidate comparison is not yet active in the production-shaped worker; do not claim it is.**
- This map-only/local-watcher split is credit-efficient and preserves AI-authored zones, but the current watcher is still a single fixed sweep/reclaim detector. Next design work should make the visual model compare suitable candidates on its scheduled map-analysis cycle and return explicit candidate/trigger metadata; local code should only monitor those AI-authored conditions and enforce mechanical safety, not invent zones or decide market structure. Preserve the no-noisy-WATCH policy and do not promote extra coded setup detectors.
- The active DNS watcher enforces fresh six-timeframe data, mapped-zone quality at least 3/5, a two-candle sweep/reclaim confirmation, a quality opposing target with at least 2R room, one open paper position per symbol, and a stop beyond the sweep extreme. Note that `main.validate_trade()` is part of the legacy `main.run()` path; the active `dns_worker` does not call it. Its confidence value is hard-coded to 80 and the legacy 0.35% market-entry deviation gate is therefore not the active path's independent validation. Add a shared, explicit risk validator before any production deployment; do not weaken existing thresholds.
- Discord execution formatting includes the primary DNS band, selected entry band, entry, SL, TP1/optional TP2, R:R, rationale and invalidation. TP/SL/TIME outcomes are sent separately by the closed-5m paper tracker. No WATCH/status messages are added. Actual webhook delivery and real paper outcomes remain unverified.
- The latest actual OpenAI request previously reached the API but returned HTTP 429 `insufficient_quota / credit_balance_exhausted`. No fresh visual-AI maps or execution alerts can be verified until API quota is restored. Do not repeatedly retry or change secrets. User action required for live visual validation: restore OpenAI API credits / use a quota-bearing API key, then manually run one paper-only cycle and inspect the raw and annotated chart artifacts.
- No worker was deployed, no scheduled alerts were enabled, no secrets were changed, no live trading was enabled and no exchange orders were placed.

### Historical data and Quant Discovery

- The Library OHLCV archive `salty_quant_historical_ohlcv_3y_verified.zip` was independently rechecked in this session: SHA-256 `07db78359920ceec6331a8f96642406543516cb12a78a1ca90099f90eb6bb9d5`; all 18 CSV hashes and row counts match the manifest; 926,209 candles total. BTC history begins 2023-12-29, ETH 2024-02-06 and XAUT 2026-04-17 (only about 6.6 months). Coverage gaps remain visible: BTC 5m has a 911,100-second largest gap, BTC 15m 311,400 seconds, BTC 1h 136,800 seconds, ETH 5m 164,400 seconds, and XAUT 5m 600 seconds. Do not fill these gaps silently or treat XAUT as a three-year sample.
- The one-time derivatives artifact from [run 41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516) was downloaded and independently revalidated: 758,119 candles across nine funding/mark/OI series; ZIP SHA-256 `f16d0bc18eddcce7637c9643d9176590c8bb55fe9de6be1da9c717bdf7949a27`; all nine CSV hashes and row counts match the manifest. BTC and ETH cover roughly 91–96% of the requested date range; XAUT covers about 18.4% because its contract history starts in April 2026.
- Funding values remain raw API units, with no scaling or payment attribution. Delta's current India perpetual guide describes funding snapshots every eight hours at 05:30, 13:30 and 21:30 IST, with payment based on position value × funding rate; some contracts may use shorter intervals. See [Delta Exchange India perpetual-contract guide](https://guides.delta.exchange/delta-exchange-india-user-guide/derivatives-guide/docs). The archived hourly `FUNDING:` candles are not yet mapped to contract-specific settlement snapshots. Do not apply them to backtest PnL until raw units, sign, candle timestamp meaning, product interval and payment-event mapping are independently verified. Historical bid/ask spread and order-book depth are still unavailable.
- EXP-001 was re-run on the verified OHLCV archive after fixing the final-bar off-by-one. All 30 OOS asset × timeframe × strategy cells remain negative at 10 bps round-trip cost plus a 1 bp/8h adverse carry stress. Only XAU 15m mean-reversion changed (116 → 117 trades; expectancy -1.3875R → -1.3611R). The least-negative cell is BTC 1h mean-reversion: 176 trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown and 7 consecutive losses. The worst is XAU 15m trend-pullback: 168 trades, 20.83% win rate, -1.6886R expectancy, PF 0.137, -284.499R max drawdown and 27 consecutive losses. All candidates remain rejected; no research rule reaches Discord.
- The 1 bp/8h term is an adverse stress assumption, not actual funding accounting. Next research step is to confirm event-time funding semantics and then add discrete funding snapshots, mark-price valuation and defensible spread/slippage scenarios to a reconciled replay engine. Keep the final OOS untouched and do not reuse the already inspected ETH downtrend subgroup as fresh holdout data.

### Exact next steps

1. Verify push and PR CI for `2a3d3dae189c673bc446743cb3a5de6cea1a22f7`.
2. Reconcile the active visual multi-setup requirement with the credit-saving map/local-trigger architecture; keep the AI visually responsible for candidate selection and the local engine limited to mechanical monitoring and risk gates.
3. Restore OpenAI API quota, then manually validate one paper-only multi-timeframe chart cycle and inspect paired raw/annotated images. Do not enable the recurring schedule.
4. Confirm funding raw units, contract-specific interval and settlement timestamp alignment before event-time attribution. Keep spread/depth limitations explicit.
5. Continue tracking visual paper alerts and confirmed TP/SL/TIME outcomes; compare them with research only after clean, adequate samples. No candidate is currently approved as an edge.


## Supervisor update — 2026-11-05 10:16 IST

### Default-branch scheduled runner and current visual pipeline

- Latest observed scheduled run: [advance-alerts run 41967539944](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41967539944), created 2026-11-05 04:23:47 UTC, ran on default branch `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`, and completed successfully. Its job log confirms it executed `python main.py`; the runner environment had `DISCORD_WEBHOOK`, `DISCORD_WATCH_WEBHOOK` and `DISCORD_TRIGGER_WEBHOOK` configured (values were redacted by GitHub).
- The default-branch `.github/workflows/alerts.yml` still schedules every 10 minutes without the visual-branch schedule guard. Default-branch `main.py` still imports and calls the coded `zones.find_zones` / `score_setup` path and can emit legacy `WATCH`, `CANCEL` and `TRIGGER` Discord messages. The run log does not establish whether any message was actually delivered. This is not the new visual-first pipeline. **No changes were made to `main`**, per scope.
- The `ai-quant-rebuild` workflow has its own five-minute schedule, but its job is gated by `ENABLE_GITHUB_SCHEDULE=true` (or manual `workflow_dispatch`). GitHub scheduled workflows run from the default branch; while PR #1 remains draft/unmerged, this branch's scheduled visual worker is not the default scheduled runner. CI runs are tests, not live chart-analysis cycles.
- No current raw/annotated chart images were attached to the latest PR CI or default-branch scheduled run; both workflow artifact lists were empty. Therefore no current multi-timeframe visual market assessment or execution signal is claimed in this supervisor cycle.
- The active branch container path remains `Dockerfile → worker.py → dns_worker.py`. It refreshes visual DNS maps with `ai_analyst.map_dns()`, then uses only `dns_engine.detect_local_setup()` for the local sweep/reclaim candidate. The broader multi-setup `ai_analyst.analyse()` path is not active in that worker. The prior HTTP 429 `insufficient_quota / credit_balance_exhausted` remains the last known live-analysis blocker; no new live OpenAI call was made.
- The lifecycle boundary finding in PR comment #6636833531 is already fixed on this branch: `manage_positions()` caps eligible 5m bars at expiry minus five minutes, only marks TIME after expiry, and has regressions for a post-expiry TP touch and missing candles. No duplicate fix was needed.
- This cycle found and fixed misleading metadata: the DNS watcher had hard-coded `confidence: 80` even though the local detector does not calculate a confidence score. The watcher no longer supplies that value, and Discord now omits confidence unless a valid measured value is present. A regression test was added. Visual-AI analyses still retain their actual model-returned qualitative confidence field; it is not a probability or proven win rate.
- User action before cutover: decide whether to pause the legacy default-branch `advance-alerts` schedule or knowingly tolerate its legacy WATCH/TRIGGER path. This supervisor did not disable it or modify `main`. Restore OpenAI API quota before manually validating the new branch's visual chart-to-AI cycle. Do not enable the branch's recurring schedule or deploy until the multi-setup visual analysis and shared risk-validation design are completed and reviewed.

### Exact next steps

1. Review the latest default-branch scheduled run and decide how to handle the legacy alerts workflow; no GitHub setting or main-branch file was changed.
2. Continue the visual-first integration design: the model must compare suitable setup families and return one selected candidate or NO_TRADE; local code should only enforce mechanical risk and track confirmed outcomes.
3. Add a shared mechanical validator to the active DNS worker before any deployment; remove hard-coded confidence or other unmeasured alert metadata.
4. Restore API quota and manually inspect raw/annotated multi-timeframe chart artifacts before judging visual mapping quality.
5. Confirm funding-event semantics and realistic execution costs before extending Quant Discovery beyond the rejected EXP-001 baseline.


## Quant Discovery funding-semantics update — 2026-11-05 10:22 IST

### Fresh CI data-feed verification

- Commit `b700a60a9ac86bd1850b571f51ea7be0250b79ce` passed push CI [41970160655](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41970160655) and PR CI [41970165574](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41970165574).
- Both CI runs passed the new Discord regression, the offline visual/DNS/Quant Discovery suite, and live public Delta checks for all 18 BTC/ETH/XAUT timeframes. The feed smoke observed closed 5m/15m/1h/4h/1d/1w candles with no freshness failures.
- The derivatives smoke returned 69 one-hour funding candles, 864 five-minute mark candles and 72 one-hour OI candles for each of BTCUSD, ETHUSD and XAUTUSD. The historical OHLCV pilot downloaded 1,051 BTC 5m candles with 100% coverage and zero gaps. These are availability/ingestion checks, not strategy or execution validation.

### Funding-event interpretation

- Delta's [historical candles API documentation](https://docs.delta.exchange/) explicitly supports `FUNDING:<symbol>`, `MARK:<symbol>` and `OI:<symbol>` as candle symbols, with up to 2,000 candles per response. It describes OHLC candles, but does not establish that every hourly FUNDING candle is a realised settlement event or specify the exact event timestamp semantics. Keep the hourly series as a sampled-rate research feature until this is resolved.
- Delta's public WebSocket `funding_rate` example includes `fi` (funding interval in seconds), `fr` (funding rate), `nfr` (next funding realisation timestamp) and `ts` (update timestamp). The example has `fi=28800`; the contract's live `fi` / product `rate_exchange_interval` must be read rather than assuming every contract is 8-hourly.
- Delta India's [perpetual-contract guide](https://guides.delta.exchange/delta-exchange-india-user-guide/derivatives-guide/docs) says standard 8-hour funding snapshots occur at 05:30, 13:30 and 21:30 IST, while some contracts can use shorter intervals. The position must be present in the funding snapshot; holding time between snapshots is not prorated. Payment is current position value × funding rate. Positive funding means longs pay shorts; negative funding means shorts pay longs. Backtests must therefore apply discrete contract-specific funding events only when a position is open at the event, not a continuous hourly carry approximation.
- Unit hypothesis only: the API example's numeric `fr=0.01`, together with the guide's 0.01% standard interest-rate example and 0.05% clamp, suggests rates may be expressed in percentage-point units (0.01 meaning 0.01%), not decimal fractions (0.01 meaning 1%). This is not yet verified for the archived hourly candles or every contract. Preserve raw values and do not convert or book funding into PnL until a live product specification and a known funding event/payment reconcile the units, sign and timestamp.
- Next funding research step: capture a timestamped read-only product specification and public funding-rate WebSocket sample for each contract, record `fi`, `fr`, `nfr`, `ts`, and reconcile one event against an independently observed funding transaction or authoritative event record. Until then, no historical funding PnL claim.

### Supervisor state after this update

- Branch: `ai-quant-rebuild`; code commit under review: `b700a60a9ac86bd1850b571f51ea7be0250b79ce`. The PR remains open, draft and unmerged. `main` remains unchanged.
- The fake DNS confidence value was removed; Discord only prints confidence when a valid value is actually supplied. The new regression passed in both CI runs.
- The default-branch legacy `advance-alerts` schedule finding and required user decision are recorded in the prior supervisor update above. No main-branch change or workflow setting change was made.


## Supervisor handoff — 2026-11-05 (local DNS entry-proximity gate)

### Latest verified repository state
- Branch: `ai-quant-rebuild`; code head before this handoff note: `2744b0f3e481f920ef2c73d7beadfa49913b273c`.
- PR #1 remains open, draft, unmerged, targeting `main`. No changes were made to `main`.
- Risk-gate fix commits: `6bfee07aace19ce63636f4f437d2d892026c1575` (local DNS entry proximity) and `2744b0f3e481f920ef2c73d7beadfa49913b273c` (regression tests).
- Push CI [41976396776](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41976396776) and PR CI [41976399657](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41976399657) both completed successfully, including DNS map/local watcher tests, Quant Discovery tests, public Delta OHLCV checks, derivatives probes and historical-download pilot.

### Risk-control defect fixed
- The active `dns_worker.py → dns_engine.detect_local_setup()` path generated a market entry at the confirming 5m close and enforced zone quality, sweep/reclaim, invalidation and minimum 2R, but it did not enforce the configured `MAX_MARKET_ENTRY_DEVIATION_PCT` between that entry and the AI-authored DNS band.
- A strong confirming candle could therefore chase price too far away from the visual zone. `dns_engine.py` now rejects local candidates when distance from the entry to the nearest edge of the mapped zone exceeds the existing configured 0.35% threshold. This is an additional mechanical gate only; it does not create zones or change setup identification.
- `test_dns_engine.py` now verifies a valid near-zone demand sweep remains eligible and a confirmation more than 0.35% away is rejected. Both CI workflows passed.

### Remaining operational / architecture blockers
- The latest observed default-branch scheduled run remains legacy `advance-alerts` [41973906858](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41973906858), on `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. Its workflow still executes `python main.py` every 10 minutes with legacy Discord webhook secrets present. The log confirms execution of the script and secret presence (values redacted), but does not prove a message was delivered. The old path can still emit WATCH/CANCEL/TRIGGER messages. No change was made to `main` or the workflow settings.
- The branch workflow `.github/workflows/alerts.yml` is schedule-gated by `ENABLE_GITHUB_SCHEDULE=true`; GitHub scheduled workflows execute from the default branch. PR #1 is unmerged, so this branch is not the default scheduled runner. Manual dispatch remains the only safe validation path.
- Active branch path remains `worker.py → dns_worker.py`: it fetches six closed Delta timeframes, refreshes an AI visual DNS map only when missing/aged/broken, then uses the narrow local DNS liquidity-sweep/reclaim detector. The broader `ai_analyst.analyse()` multi-setup trade-selection function is not called by the active worker. The prompt enumerates multiple DNS-anchored sub-setups, but this does not yet satisfy a full active multi-family AI comparison each cycle.
- No current chart-review artifact or fresh live AI cycle was available. The last known Responses API attempt returned HTTP 429 `insufficient_quota / credit_balance_exhausted`; no repeated API calls were made. Restore quota before one manual paper-only visual validation.
- Discord formatting on the branch includes setup, optional measured confidence, primary DNS band, selected entry band, entry, stop, targets, validated R:R, rationale, invalidation and paper-only disclaimer. TP/SL/TIME outcomes are separate updates. Actual Discord delivery remains unverified.

### Exact next steps
1. Keep the legacy main workflow unchanged until the owner explicitly decides how to handle the old scheduled alerts; do not silently disable or replace it.
2. Restore OpenAI quota and manually dispatch one paper-only branch cycle; inspect raw and annotated multi-timeframe images, model result, local signal gate and Discord delivery.
3. Design and test the active worker's visual multi-setup comparison path (including independent trend/momentum/breakout/mean-reversion candidates where chart evidence supports them), with the model selecting one candidate or NO_TRADE and local code enforcing mechanical risk only. Do not deploy or enable recurring schedule until audited.
4. Keep the new 0.35% local DNS proximity gate and add symmetric short-side coverage if the detector is expanded.
5. Continue discrete funding-event reconciliation; raw hourly funding candles remain unscaled and are not applied to P&L. EXP-001 remains rejected: all 30 OOS baseline cells negative under the documented cost/stress assumptions.

No live trading, broker orders, infrastructure deployment, secret changes, PR merge or main-branch edits were performed.


## Quant Discovery update — funding-series alignment and OI cross-check (2026-11-05)

### Historical funding-series structure
The verified derivatives archive (758,119 candles; ZIP SHA-256 `f16d0bc18eddcce7637c9643d9176590c8bb55fe9de6be1da9c717bdf7949a27`) was inspected at row level, not only by manifest hash.

- The `FUNDING:<symbol>` datasets are stored as 1h OHLC candles, but the close value is stepwise and typically changes only at funding-boundary timestamps rather than each hour.
- BTC: 1,387 observed rate changes after the initial value; all 1,387 timestamps aligned to UTC 00:00, 08:00 or 16:00 (the standard 05:30, 13:30, 21:30 IST schedule).
- ETH: 1,114 changes; 1,113 aligned to the same 8h boundaries (99.91%). One change occurred at 2024-11-29 09:00 UTC and needs investigation rather than silent normalization.
- XAUT: only two rate changes after its initial value; both happened on 4h-aligned UTC timestamps. The rate was otherwise almost constant at 0.005, so this sample alone is insufficient to establish its contract interval.
- BTC and ETH median raw funding close is 0.01; XAUT median is 0.005. Delta's current public WebSocket sample exposes `fi` (interval seconds), `fr` (funding rate), `nfr` (next funding realisation timestamp) and `ts` (update timestamp). The BTC sample uses `fi=28800` and `fr=0.01`. The India guide describes a 0.01% per 8h interest-rate baseline and percentage-based funding formula; this strongly suggests 0.01 is 0.01%, not 1%, for that live sample. The historical-candle endpoint documents `FUNDING:<symbol>` but does not explicitly state candle-value units. Preserve raw units until a live value, product specification and known settlement reconcile.
- The product API exposes `product_specs.rate_exchange_interval` in seconds; the live BTCUSD product response returned 28,800 seconds. Delta's India guide says standard funding is exchanged at 05:30, 13:30 and 21:30 IST, while some contracts use shorter intervals. A position is included only if present in the funding snapshot; payment is position value × funding rate.

Official references: [Delta API historical funding symbols and WebSocket funding_rate fields](https://docs.delta.exchange/); [BTCUSD product specifications](https://api.india.delta.exchange/v2/products/BTCUSD); [Delta India perpetual funding calculation and settlement guide](https://guides.delta.exchange/delta-exchange-india-user-guide/derivatives-guide/docs).

**Important unresolved timestamp question:** the hourly historical funding candle at a boundary may represent the rate just realised at that timestamp or the newly published rate for the next `nfr` event. The change-point alignment is strong evidence of event-boundary sampling, but does not prove whether the correct event attribution is same-boundary or one-interval-lagged. Do not book funding into trade P&L until this is reconciled against a timestamped live `fr/nfr/ts` sample and an independently known funding event. Do not prorate hourly values.

### Exploratory funding / OI association screen — descriptive only
A first alignment check sampled mark-price closes and open-interest closes on the candidate funding grid (BTC/ETH 8h; XAUT 4h), then compared the funding value and prior-interval OI percentage change with the subsequent mark-price return. This is a descriptive correlation screen, not a strategy backtest; nominal p-values ignore serial dependence, no fills/costs were simulated, and event-time funding attribution remains unresolved.

| Contract | Aligned intervals | Funding vs next mark return (Pearson r) | Prior OI change vs next mark return (r) |
|---|---:|---:|---:|
| BTCUSD | 3,117 | -0.0132 | -0.0082 |
| ETHUSD | 3,007 | +0.0166 | -0.0043 |
| XAUTUSD | 1,208 | -0.0138 | +0.0008 |

These near-zero linear associations do not support a simple standalone funding-contrarian or prior-OI-change signal. They do not rule out nonlinear, tail, volatility-regime or joint price/OI/funding effects. No candidate is promoted and no execution alert is affected.

### Next research steps
1. Capture read-only live product specifications and a timestamped `funding_rate` WebSocket sample for BTCUSD, ETHUSD and XAUTUSD, recording `fi/fr/nfr/ts` and contract interval.
2. Reconcile one funding event per contract against a known payment/event record to establish historical candle unit, sign and same-boundary versus lagged attribution.
3. Add reproducible funding-boundary and OI/mark feature experiments with chronological splits, block-aware uncertainty, costs and exact event attribution. Keep XAUT's short history and ETH's single non-aligned change explicit.
4. Until that is complete, keep funding as a raw descriptive feature only; EXP-001 remains rejected and no research candidate enters production alerts.


## Supervisor handoff — 2026-11-05 12:52 IST

### Exact repository state rechecked
- Branch `ai-quant-rebuild` head before this handoff-only update: `b7e0c9e74506dd36e82bbfcb9df96c3504b537c8` (commit message: "Document funding boundary and OI exploratory findings", 2026-11-05 05:53:09 UTC).
- Draft PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1) remains open, draft, mergeable and unmerged; base `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`; 250 commits / 45 changed files at this check.
- Exact-head push CI [41976807017](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41976807017) and PR CI [41976811826](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41976811826) both completed successfully. The PR-triggered run for this SHA is the same successful PR CI run.
- No review submissions or inline review threads were returned. No new code defect was found that justified a low-risk code change in this cycle; no code thresholds or runtime behaviour were changed.

### Fresh operational evidence
- Default-branch legacy scheduled run [41980193244](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41980193244) completed successfully on `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795` on 2026-11-05 06:24 UTC. Its job executed `python main.py`; the runner log showed the legacy Discord webhook environment variables present (values redacted). This proves the old scheduled code path ran, not that a Discord message was delivered.
- `main/.github/workflows/alerts.yml` still schedules `advance-alerts` every 10 minutes and executes `python main.py`. The branch `.github/workflows/alerts.yml` defines `salty-quant-visual-desk` every five minutes but gates scheduled analysis on repository variable `ENABLE_GITHUB_SCHEDULE == 'true'`; it also supports manual dispatch. Because PR #1 is unmerged and scheduled workflows run from the default branch, the branch visual workflow is not the current default scheduled runner. No change was made to `main`, workflow settings or secrets.
- The latest CI run checked all 18 BTCUSD/ETHUSD/XAUTUSD × six-timeframe public OHLCV combinations and the public funding/mark/OI probes. Last verified 5m closes at 2026-11-05 05:53 UTC were BTC 80407.0, ETH 2419.45 and XAUT 4098.27. This is a dated feed smoke test, not a quote for 12:52 IST.
- The latest push CI and PR CI runs have no uploaded artifacts. The latest legacy scheduled run also has no uploaded artifacts. No current raw or AI-annotated chart images are available in GitHub artifacts for visual inspection during this cycle.
- The active branch runtime remains `worker.py → dns_worker.py`. It builds six-timeframe chart images, but calls `ai_analyst.map_dns()` only when the map is missing/aged/broken, then lets the narrow local DNS sweep/reclaim detector generate paper candidates. The broader `ai_analyst.analyse()` path is not called by the active worker.
- The analyst prompt still makes demand/supply mandatory for every trade and restricts trend, momentum, breakout/retest and mean-reversion candidates to DNS-anchored sub-setups. This is narrower than the supervisor requirement to compare independently suitable evidence-supported approaches rather than force DNS as the universal location framework. Do not describe multi-family analysis as active until the prompt, schema, mechanical validator and active worker are updated and tested together.
- No fresh Responses API call was made because there was no manual visual-workflow run or current chart artifact to inspect. The last known OpenAI API blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`. Actual Discord delivery remains unverified.

### Current safety / research status
- Existing branch gates remain: AI confidence >=75, minimum 2R, selected-entry-zone proximity <=0.35%, quality >=3 for the DNS detector, directionally valid SL/TP, one open paper position per symbol, and closed-5m TP/SL/TIME tracking. Discord execution and separate outcome formatting are implemented; delivery is not verified.
- EXP-001 remains rejected: all 30 OOS asset/timeframe/strategy cells had negative expectancy under the documented base cost/adverse-carry assumptions. Funding/OI findings remain descriptive; raw funding candle units and same-boundary versus lagged settlement attribution are not reconciled. No candidate is approved as an edge.
- No deployment, secret change, live trading, broker order, PR merge, or `main` edit occurred.

### Exact next steps
1. Keep the legacy default-branch workflow unchanged until the owner makes an explicit decision; do not silently disable it.
2. Restore OpenAI API quota, then manually dispatch one paper-only visual workflow cycle and inspect all raw/annotated BTC/ETH/XAUT multi-timeframe chart images, model outputs, validator decisions and any Discord delivery result.
3. Redesign the visual analyst so it compares independent candidate families (SMC/structure, DNS, liquidity, S/R, trend pullback, momentum, breakout/retest and volatility/mean-reversion) where the chart evidence supports them; permit `NO_TRADE`. Remove the mandatory DNS anchor for non-DNS families without weakening numeric risk gates.
4. Wire that analyst into the active worker only after schema and mechanical-validator tests cover every family; local code must validate prices/risk and track outcomes, not invent zones or decide market structure.
5. Continue contract-specific funding event reconciliation; do not convert historical funding candles or book them into P&L until units, sign and event timing are independently verified.


## Supervisor verification — 2026-11-05 13:52 IST

### Exact branch / PR / CI state
- Branch `ai-quant-rebuild` head at the start of this verification: `e68bf74f8f23c52168fa88d308420c3daf520373` (handoff-only commit).
- Draft PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1) remains open, draft, mergeable and unmerged; base `main`; 251 commits / 45 changed files. Default branch is still `main`.
- Push CI [41987082118](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41987082118) and PR CI [41987089690](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41987089690) both completed successfully on the exact `e68bf74` head. All listed steps passed: compile, visual/DNS tests, paper replay, reporting, feedback, OpenAI-secret validation, derivatives parsing/archive, Quant Discovery tests, 18 public OHLCV checks, derivatives probes and historical download pilot.
- Neither CI run uploaded chart-review artifacts. No raw or AI-annotated multi-timeframe chart image was available for visual inspection. The successful offline tests/feed probes do not establish a live visual-AI decision or Discord delivery.

### Fresh feed evidence (CI timestamp 2026-11-05 07:25 UTC)
- All 18 symbol/timeframe checks passed for BTCUSD, ETHUSD and XAUTUSD across 5m, 15m, 1h, 4h, 1d and 1w. Closed-bar and freshness checks passed.
- Latest 5m closes in that run: BTCUSD 80,590.00; ETHUSD 2,424.25; XAUTUSD 4,106.95. These are historical CI snapshot values, not current quotes at 13:52 IST.
- Funding 1h, mark 5m and OI 1h series were available for all three contracts (72 funding candles, 864 mark candles and 72 OI candles per contract). The BTC 5m historical pilot returned 1,051 candles, 100% observed coverage, zero gaps.
- No newer live feed request was made in this verification.

### Architecture / operational blockers confirmed from current branch files
- `dns_worker.py` calls `ai_analyst.map_dns()` only when the DNS map is missing, aged or invalidated; each subsequent five-minute cycle uses `dns_engine.detect_local_setup()` for the narrow local DNS sweep/reclaim detector. The active worker does not call `ai_analyst.analyse()`.
- `ai_analyst.py` explicitly requires every actionable setup to be anchored to a directional DNS zone. Trend pullback, momentum, breakout/retest and mean-reversion are restricted to DNS-anchored confirmations. `main.validate_trade()` also requires a nearby selected entry zone overlapping a quality directional DNS zone. Thus the current prompt/schema/validator/worker combination does not yet satisfy independent comparison of all suitable setup families; a test that checks the setup-type enum alone is insufficient.
- Active `dns_worker.py` path: the local DNS detector enforces AI-map zone quality >=3, sweep/reclaim plus confirming close, invalidation on the zone's own timeframe, minimum 2R to an opposing mapped zone, and entry-to-zone deviation <=0.35%; the worker allows only one open paper position per symbol. This path does **not** apply the separate `main.validate_trade()` confidence >=75 gate because it does not call that validator and its DNS-map response has no trade-confidence score. The separate `main.validate_trade()` path enforces confidence >=75, minimum 2R, <=0.35% entry/zone proximity and selected-band overlap with a quality >=3 directional DNS zone, but it is not called by the active DNS worker. This distinction is a known integration gap, not evidence that all gates run on every active candidate. TP/SL/TIME tracking and execution/outcome Discord formatting are implemented; no delivery confirmation is available.
- The default-branch `main/.github/workflows/alerts.yml` still schedules `advance-alerts` every 10 minutes and executes `python main.py` with legacy Discord webhook secrets. The last specifically verified legacy scheduled run remains [41980193244](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41980193244) at 06:24 UTC; this check verified the workflow definition but did not retrieve a newer scheduled run. The branch visual workflow remains schedule-gated by `ENABLE_GITHUB_SCHEDULE == 'true'`; PR #1 is unmerged, so it is not the default scheduled workflow.
- Last known OpenAI Responses API blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not retried. Actual Discord delivery is not verified.

### Quant Discovery decision
- EXP-001 remains rejected: 30/30 baseline OOS cells had negative expectancy under the documented 10 bps round-trip cost plus adverse-carry stress. The post-hoc ETH 15m volatility-expansion/downtrend subgroup remains an unvalidated hypothesis and is not eligible for alerts.
- Funding/OI work remains descriptive. Historical funding candle unit, sign and same-boundary versus lagged event attribution are not reconciled; do not book historical funding P&L. Historical spread/depth remain unavailable.

### Supervisor decision / next steps
- No new low-risk code defect was identified. No runtime code, thresholds, secrets, infrastructure or `main` files were changed in this verification.
- Next: restore OpenAI quota; manually run one paper-only visual cycle and inspect chart artifacts/model output/validator/Discord result; redesign prompt/schema/validator/active worker together so independent evidence-supported setup families can be selected or return `NO_TRADE`; retain mechanical risk gates and local outcome tracking. Resolve the legacy default-branch workflow only after owner decision.
- No PR merge, deployment, live trading or exchange order.


## Supervisor update — 2026-11-05 15:43 IST (stale-map fail-closed fix)

### Safety defect found and fixed
- The DNS worker previously continued running local setup detection against the last saved map when a refresh was due but throttled by the 30-minute retry window, when the AI refresh raised an error (including quota failure), or when the batch response omitted a symbol. That was fail-open behaviour: a stale map could still produce a new paper entry.
- The worker now blocks new setup detection for each symbol whose map requires refresh. The block is removed only after that symbol's refreshed map is successfully validated and saved. Existing paper positions continue to be managed for TP/SL/TIME while new entries are blocked.
- Missing symbols in a batch response are handled explicitly and remain blocked; unknown/malformed response rows are ignored rather than being treated as a refreshed map.
- Changes are on `ai-quant-rebuild` only: `8d89dcd` (fail-closed worker), `6bd99cc` (worker regression coverage and test runner), `6177b6a` (fixture correction).

### Test-coverage defect found and fixed
- CI invokes `python test_dns_engine.py`, but the file previously defined test functions without a `__main__` runner; direct script execution therefore defined the tests without executing them. Added a deterministic runner so this CI step actually executes the DNS tests.
- Added four worker-level regressions: refresh throttled, AI refresh failure, refresh response omits symbol, and successful refresh resumes scanning.
- The earlier PR CI [41994333863](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41994333863) passed before the stale-map fixes. The subsequent PR CI [42009355459](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42009355459) passed on head `2490a1f`; the latest PR CI [42009630441](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42009630441) passed on head `122c26a` after adding the refresh-check exception regression.

### Current limitations and next steps
- The PR CI run above had one test job and no uploaded chart artifacts. It does not establish a live visual-AI decision or Discord delivery.
- The active worker remains DNS-only; the independent multi-family visual analyst is not yet wired into the worker. The system prompt and validator still require a directional DNS anchor for every trade.
- The legacy `main` branch workflow `.github/workflows/alerts.yml` remains scheduled every 10 minutes and executes `python main.py`. It has not been changed; owner decision is required before pausing/cutting over.
- Last known OpenAI quota blocker is HTTP 429 `insufficient_quota / credit_balance_exhausted`; not retried in this cycle.
- EXP-001 remains rejected (30/30 baseline OOS cells negative under stated assumptions). Funding event unit/sign/timing reconciliation remains open; no candidate is promoted.
- Next: verify both CI workflows on the new branch head; after API quota is restored, manually dispatch a paper-only visual cycle and inspect raw/annotated six-timeframe charts, model output, validator decisions and Discord delivery evidence. Do not enable scheduled visual runs or production cutover as part of this work.
- No main-branch change, merge, deployment, secret change, live trading or exchange order.


## Final supervisor verification — 2026-11-05 15:49 IST

- Latest code/test head verified by PR CI: `122c26a633dbc703e74dd01f2f1bd013decd39dc`. PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1) remains open, draft, unmerged and mergeable; `ai-quant-rebuild` is 259 commits ahead of `main`, 0 behind, with 45 changed files.
- PR CI [42009630441](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42009630441) completed successfully on that exact head. The job log explicitly shows 11 DNS tests executed and passed, including refresh throttled, AI refresh failure, response omitting a symbol, refresh-check exception, and successful refresh resuming detection. This also confirms the previously missing `test_dns_engine.py` script runner now executes the tests under CI.
- The same run passed compilation, visual pipeline, Quant replay, daily report, feedback, OpenAI-secret-format, derivatives parser/archive, Quant Discovery, all 18 BTC/ETH/XAUT timeframe freshness checks, public funding/mark/OI probes, and the BTC historical pilot.
- Feed snapshot at 2026-11-05 10:19:16 UTC: BTCUSD 5m 80,374.00; ETHUSD 5m 2,417.80; XAUTUSD 5m 4,110.39. All 18 symbol/timeframe checks passed. Derivatives availability: funding 67 BTC / 67 ETH / 71 XAUT hourly candles; mark 864 five-minute candles per contract; OI 72 hourly candles per contract. BTC 5m pilot: 1,051 candles, 100% observed coverage, zero gaps.
- No workflow artifacts were uploaded by this PR CI run. It is a validation workflow, not a live visual-desk run; no raw/annotated chart review or actual Discord delivery was verified.
- The active worker now fails closed whenever a DNS map refresh is due but throttled, fails, omits the symbol, or the refresh/freshness check itself raises. Existing paper positions continue to be managed; new entries for the affected symbol are blocked until a valid map is saved.
- Remaining architecture gap: active worker is still DNS sweep/reclaim only; the visual analyst/schema/validator require a DNS anchor for every candidate. Independent trend, breakout, momentum and mean-reversion setup families are not yet independently selectable in the active worker.
- The legacy default-branch `main/.github/workflows/alerts.yml` remains scheduled every 10 minutes and runs `python main.py`; no changes were made to it. The branch visual schedule remains gated by `ENABLE_GITHUB_SCHEDULE`.
- Last known OpenAI API quota blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; no live visual cycle or Discord execution delivery is verified. Restore quota before manually dispatching one paper-only visual validation.
- EXP-001 remains rejected; no new strategy edge is established. Funding candle units/sign/event timing remain unresolved; no historical funding P&L conversion is approved.
- No `main` modification, PR merge, deployment, secret change, live trading or exchange order.


## Supervisor handoff — 2026-11-05 16:08 IST

### Repository and CI
- Code/research head immediately before this handoff: `b56c3dcb3ebf33c2b54f9c00e210ecffe47fc514`. PR #1 remains open, draft, unmerged and mergeable; branch was 268 commits ahead of `main`, 0 behind, with 48 changed files.
- PR CI [42012178809](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42012178809) passed on that exact head. It passed compilation, visual pipeline, DNS watcher, replay/lifecycle, report, feedback, secret-format, derivatives parser/archive and Quant Discovery tests, plus live Delta feed checks and the historical download pilot.
- The first CI attempt for the new OI screen exposed a pandas 3 timestamp-resolution issue: `DatetimeIndex.asi8` may be microseconds while `Timedelta.value` is nanoseconds. Replaced the integer comparison with direct timedelta comparisons and changed simulation tests to microsecond-resolution indexes. The final PR CI passed.

### Delayed Discord alert safety fix
- Found that `dns_worker.py` retried pending Discord execution alerts before fetching current market data. A webhook failure followed by a delayed retry could therefore publish a stale entry even if price had moved through TP/SL or the required R:R had deteriorated.
- Pending alerts are now retried only after fresh closed-bar data and DNS-map refresh checks. The retry re-prices at the latest closed 5m close, recalculates R:R, rechecks the existing 0.35% entry/zone deviation limits, requires correct SL/TP ordering and minimum 2R, and requires the selected band to overlap a current quality directional AI zone. If no longer actionable, the pending alert is discarded; if the symbol's refresh is blocked or data is stale, it is not sent. Successful retry tracking starts at the new close time.
- Added long/short, price-drift, R:R erosion, current-map overlap and worker-delivery regressions. `test_dns_engine.py` now reports 17 passing tests in CI.

### Quant Discovery — OI + volatility expansion screen
- Added `quant_discovery/oi_expansion_screen.py`, `quant_discovery/test_oi_expansion_screen.py`, and `quant_discovery/OI_EXPANSION_SCREEN.md`.
- Hypothesis: after a large 1h move, positive OI expansion may identify continuation. Entry is next 1h open; signal thresholds use prior 720 hours only (minimum 168); ATR14 stops 1.0/1.5x; targets 2R/3R; max hold 8h; stop-first same-bar handling; no overlapping positions.
- Used complete 1h bars resampled from 5m traded-price OHLCV, aligned OI candle closes at timestamp +1h (explicit assumption still needing endpoint-semantic confirmation), and chronological 60/20/20 splits. No gap filling. Tested 10 bps all-in round-trip friction and 20 bps stress. Funding excluded pending settlement-event/unit reconciliation.
- BTC best OOS grid row: 45 trades, 42.22% win rate, -0.0313R expectancy, 0.9337 PF, -7.8709R max DD, 6-loss streak; at 20 bps expectancy -0.1365R. All eight BTC OOS rows were negative at 10 bps.
- ETH best OOS row: 67 trades, 43.28% win rate, +0.0493R, 1.0896 PF, -10.8919R max DD, 5-loss streak; 20 bps expectancy -0.0640R. Train and validation for this row were negative.
- XAUT best OOS row: 14 trades, 71.43% win rate, +0.2863R, 1.7499 PF, -3.7874R max DD, 2-loss streak; 20 bps expectancy -0.0305R. OOS is only ~40 days; train/validation were negative. This is a weak sample, not an edge.
- All candidates rejected; no walk-forward promotion stage is warranted until a candidate first survives chronological OOS and cost robustness with adequate sample size. No research output is connected to production alerts.
- The new Quant Discovery test module reports five passing tests, including incomplete-hour exclusion, OI close alignment, lagged thresholds, stop-first ambiguity and higher-cost sensitivity.

### Latest feed evidence
- CI snapshot at 2026-11-05 10:37:38 UTC: BTCUSD 5m 80,382.50; ETHUSD 5m 2,418.80; XAUTUSD 5m 4,108.09. All 18 symbol/timeframe freshness checks passed.
- Derivatives probe: funding 67 BTC / 67 ETH / 71 XAUT hourly candles; mark 864 five-minute candles per contract; OI 72 hourly candles per contract. BTC historical pilot: 1,051 candles, 100% observed coverage, zero gaps.
- The PR CI run uploaded no chart-review artifacts. It does not establish a fresh visual-AI decision or actual Discord delivery.

### Architecture and blockers
- The active workflow still runs `python dns_worker.py`. It refreshes AI-authored DNS maps and the local watcher only detects DNS sweep/reclaim. The separate `ai_analyst.analyse()` multi-family candidate function is not wired into this worker, and the validator still requires a DNS anchor. Independent trend, momentum, breakout and mean-reversion candidates therefore cannot yet compete on equal terms.
- The default `main` branch workflow `.github/workflows/alerts.yml` remains scheduled every 10 minutes and runs legacy `python main.py` with legacy Discord webhook secrets. No changes were made to `main`. The branch visual schedule is gated by `ENABLE_GITHUB_SCHEDULE`; manual dispatch is separate.
- Last known OpenAI API blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`. No new chart-review images were available in CI and no live visual cycle was run.
- EXP-001 remains rejected (30/30 baseline OOS combinations negative). OI screen candidates are also rejected. Historical funding event timing/units and actual spread/depth remain unresolved.
- Next: restore API quota; redesign the visual analyst/schema/validator so multiple independent setup families can be compared without forcing a DNS anchor; connect that selection to the active worker; retain mechanical risk validation; then manually validate one paper-only six-timeframe chart cycle and confirm Discord delivery/outcome tracking. Resolve the legacy default-branch workflow before any cutover.
- No `main` modification, PR merge, deployment, secret change, live trading or exchange order.


### Final report refinement — 2026-11-05 16:12 IST
- Expanded `quant_discovery/OI_EXPANSION_SCREEN.md` to include full OOS ranges across all eight parameter combinations per asset for trade count, win rate, expectancy, profit factor, max drawdown, losing streak, trade frequency and 20 bps stress. This prevents the best-row summary from obscuring the broader grid.
- The code/test head `b56c3dcb` passed PR CI [42012178809](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42012178809). This report refinement is documentation-only; its CI run is checked separately.

## Supervisor verification — 2026-11-05 17:20 IST (strict validation and gap-safe outcomes)

### Repository and CI
- Branch head: `c1892cc8b5582c7a9a495f5e5ad9efbbaf329ffa`.
- Draft PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1) remains open, draft, unmerged and mergeable; 277 commits / 48 changed files. Default branch remains `main`; no `main` edits were made.
- Push CI [42022081161](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42022081161) and PR CI [42022085639](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42022085639) both passed on the exact final head. The full job passed compile, visual, DNS, paper lifecycle, Quant Discovery, derivatives and live Delta feed checks.
- The prior code/test head `9083d36081d43777985ea6f0de883076c8472810` also passed PR CI [42022051699](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42022051699); the final head adds only a docstring clarification and a tightened test assertion after that run.

### Safety fixes on `ai-quant-rebuild`
- `main.validate_trade()` previously converted model confidence with bare `int(...)`. Malformed values such as `None`, strings, NaN/Infinity, booleans, fractional values, huge integers or out-of-range scores could raise or be silently truncated/accepted. It now requires a numeric, finite, integral score from 0–100 before applying the unchanged configured minimum confidence threshold. Regression tests cover invalid inputs and the 75/100 boundary. Commits: `8e8e457` and `f2f37cbe`.
- Paper outcome tracking previously inferred TIME from sparse candles and could accept a later TP/SL after an unobserved 5m gap, despite not knowing whether the first exit happened inside the gap. `manage_positions()` now walks a contiguous 5m sequence from the actual entry timestamp. It stops at the first gap; later TP/SL cannot be called the first exit across missing data. TIME is emitted only when every expected 5m candle through expiry is present. Missing/incomplete coverage leaves the position unresolved rather than fabricating a confirmed exit. Commits: `296805c` and `9083d360`; follow-up clarity/test cleanup: `7a1d2e9` and `c1892cc`.
- Tests explicitly cover a complete 48-hour window with a post-expiry TP (TIME remains correct), no in-window candles, a gap before a later TP, and a missing expiry window. CI passed all tests.

### Fresh feed evidence (PR CI at 2026-11-05 11:50:18 UTC)
- All 18 BTCUSD / ETHUSD / XAUTUSD timeframe checks passed (5m, 15m, 1h, 4h, 1d, 1w).
- Latest closed 5m values: BTCUSD 80,365.50; ETHUSD 2,420.20; XAUTUSD 4,119.07. These are CI snapshots, not current quotes.
- Funding candles available: 68 BTC / 68 ETH / 72 XAUT hourly; mark: 864 five-minute candles per contract; OI: 72 hourly candles per contract.
- BTC historical pilot: 1,051 candles, 100% coverage, zero gaps.
- PR CI uploaded no chart artifacts. This is not a visual-desk run and does not verify an AI chart decision or Discord delivery.

### Active operational blockers
- The active branch worker remains DNS-map + local sweep/reclaim only. `ai_analyst.analyse()` and its multi-setup comparison are not wired into the active worker; prompt/schema/validator still require a DNS anchor. Independent trend, momentum, breakout/retest and mean-reversion candidates are not yet eligible to compete independently.
- The branch visual workflow `.github/workflows/alerts.yml` schedules every 5 minutes but the job is gated by `ENABLE_GITHUB_SCHEDULE == 'true'` for scheduled events. No branch visual workflow run or chart-review artifact was found. Manual dispatch remains the intended paper-only validation route; do not enable the schedule or cut over without approval.
- Last observed legacy default-branch run [42020401643](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42020401643) at 2026-11-05 11:36:58 UTC succeeded on `main` and ran legacy `python main.py`. `.github/workflows/alerts.yml` on `main` still schedules every 10 minutes and has Discord webhook secrets configured. Logs did not establish an actual message delivery. No changes were made to `main`; owner decision is required before pausing/cutting over.
- Last known OpenAI Responses request returned HTTP 429 `insufficient_quota / credit_balance_exhausted`; not retried. No fresh raw/annotated charts, AI decision or Discord execution delivery is verified.
- EXP-001 remains rejected (30/30 baseline OOS combinations negative). OI + volatility-expansion screen candidates remain rejected; XAUT OOS is weak sample and ETH fails 20 bps stress. Funding event attribution and historical spread/depth remain unresolved. No research candidate is eligible for alerts.

### Exact next steps
1. Restore OpenAI API quota, then manually dispatch one paper-only visual cycle and inspect raw/annotated BTC/ETH/XAUT six-timeframe images, model output, candidate comparison, validator decisions and Discord delivery result.
2. Redesign analyst prompt/schema/validator together so independent evidence-supported setup families can compete and return `NO_TRADE`; keep numeric safety gates and local outcome monitoring, but do not require a DNS anchor for non-DNS families.
3. Retain the new contiguous-bar outcome rule; if data gaps remain unresolved, leave the paper position open for manual review rather than sending an unconfirmed TP/SL/TIME update.
4. Resolve the legacy default-branch scheduled workflow only after owner decision. Do not change `main`, enable live trading, deploy or place orders.


## Supervisor verification — 2026-11-05 17:57 IST (automation cycle)

### Repository / PR / CI
- Rechecked live GitHub state. PR #1 remains open, draft, unmerged and mergeable. Head is `e6af043f03a3be9abaf8864dd6eabef7f6cce725`; PR reports 278 commits and 48 changed files. Compare `main...ai-quant-rebuild`: 278 ahead, 0 behind. No new code commits since the 17:20 IST handoff.
- Push CI [42022269265](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42022269265) and PR CI [42022278020](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42022278020) both completed successfully on the exact head. The PR job's 17 principal test/verification steps all passed. No review submissions or inline review threads were returned.
- PR CI artifacts list is empty. This confirms the CI job did not publish chart-review PNGs; it is not a live visual-desk run. No new code defect or failing test was identified, so no code change was warranted.

### Latest available data-feed evidence
- The exact-head PR CI feed probe ran at 2026-11-05 11:51:42 UTC. All 18 BTCUSD / ETHUSD / XAUTUSD timeframes (5m, 15m, 1h, 4h, 1d, 1w) passed closed-bar and freshness checks.
- At that probe: BTC 5m close 80,365.50; ETH 2,420.20; XAUT 4,119.07. Last 5m candle was reported closed 1.7 minutes before the probe. These are historical CI observations, not current quotes.
- Funding availability: 68 BTC / 68 ETH / 72 XAUT hourly candles; mark: 864 five-minute candles per contract; OI: 72 hourly candles per contract. BTC historical pilot: 1,051 candles, 100% coverage, zero gaps.
- No newer live feed check was run in this cycle; GitHub Actions dispatch is not exposed by the available GitHub connector actions.

### Visual pipeline / signal safety / Discord
- Branch `.github/workflows/alerts.yml` defines a 5-minute schedule but scheduled runs are gated by `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; `workflow_dispatch` is allowed. Latest branch run listing contains CI push/PR runs only; no visual-desk workflow run or chart artifact was found.
- The active worker remains `dns_worker.py`: AI-authored DNS map plus local sweep/reclaim watcher. It does not yet route independent trend-pullback, momentum, breakout/retest or mean-reversion candidates through a shared multi-setup selector. The analyst prompt still requires a demand/supply anchor for every actionable trade. Do not describe this as the requested full multi-family visual desk.
- Existing safety protections remain: refresh fail-closed for affected symbols; DNS quality and invalidation; sweep/reclaim confirmation; 0.35% entry-to-zone proximity; minimum 2R; stale Discord retry revalidation; strict AI confidence validation in `main.validate_trade()`; contiguous 5m coverage required before confirmed TP/SL/TIME outcomes. The active DNS worker still does not call the separate `main.validate_trade()` validator, as previously documented.
- Discord formatter includes setup, optional measured confidence, zone, rationale, invalidation, entry/SL/TP and paper disclaimer; closure messages are separate. No new Discord delivery was verified in this cycle.

### Default-branch workflow observation
- Queried the latest 10 scheduled runs on `main`. Most recent returned run is [42020401643](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42020401643), created 2026-11-05 11:36:58 UTC (17:06:58 IST), successful on `main` and running the legacy `advance-alerts` workflow. No later `main` run appeared in the latest-10 response as of 17:57 IST; this is a schedule gap observation, not proof that the workflow is disabled.
- `main/.github/workflows/alerts.yml` still schedules every 10 minutes and runs legacy `python main.py` with legacy Discord webhook secrets configured. The default branch has not been modified. Actual Discord delivery is not established.
- Owner decision remains required before pausing the legacy workflow or approving a cutover. Do not alter `main`, enable the branch schedule, deploy or enable live trading.

### Quant Discovery
- OI + volatility expansion screen remains rejected for BTC, ETH and XAUT; BTC all eight OOS rows negative at 10 bps, ETH's small positive best row fails 20 bps stress and has negative train/validation, XAUT is only 14 OOS trades and negative in train/validation and at 20 bps. No strategy edge is established and no candidate is eligible for production alerts.
- Funding settlement event attribution/units and observed spread/depth remain unresolved; funding is not included in historical P&L.

### Next steps
1. Restore/confirm OpenAI API quota, then manually dispatch one paper-only visual-desk run from GitHub Actions and inspect raw/annotated six-timeframe charts, model output, candidate comparison, risk decisions and Discord delivery.
2. Redesign the visual analyst/schema/validator so independent setup families can compete and return `NO_TRADE` without a mandatory DNS anchor; wire this into the active worker only after tests.
3. Keep unresolved paper positions open when 5m coverage is incomplete; never infer an exit across a gap.
4. Obtain owner decision on the legacy `main` schedule before any cutover. No `main` edits, PR merge, deployment, secret change, live trading or exchange orders.
## Supervisor verification — 2026-11-05 19:22 IST (automation cycle)

### Repository, PR and CI
- Re-read the live branch ref and PR #1. ai-quant-rebuild head and PR head both resolve to a5d017c4470f6f9f987ebec7ae283415659d402c; PR #1 remains open, draft, unmerged and mergeable, base main, 286 commits ahead / 0 behind, 48 changed files. No review threads were returned.
- Latest exact-head push CI [42036914428](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42036914428) and PR CI [42036924765](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42036924765) both completed successfully. The PR job passed compilation, visual pipeline, DNS worker, paper lifecycle, report/feedback, secret-format, derivatives parser/archive, Quant Discovery, public Delta OHLCV, funding/mark/OI and historical archive-pilot steps.
- Current PR CI log explicitly reports 17 DNS/lifecycle tests passed, 6 daily-report tests, 3 feedback tests, 7 secret-format tests, 7 derivatives-history tests, 7 derivatives-archive tests and 10 Quant Discovery tests. It is an offline/test + public-data CI run, not a live visual desk cycle.
- Latest branch commit a5d017c changes README model/API-credit documentation only. It sets the default model identifier to gpt-6-luna and reasoning effort to low; no fresh OpenAI request was made, so model availability, image support and strict structured-output compatibility are not verified by this run. The last known live API response remains HTTP 429 insufficient_quota / credit_balance_exhausted.

### Latest feed evidence (PR CI at 2026-11-05 13:34:55 UTC)
- All 18 BTCUSD / ETHUSD / XAUTUSD native timeframe checks passed (5m, 15m, 1h, 4h, 1d, 1w); closed-bar and freshness checks passed.
- Latest closed 5m values at that snapshot: BTCUSD 79,662.50; ETHUSD 2,389.80; XAUTUSD 4,102.64. These are historical CI observations, not current quotes.
- Funding availability: 70 hourly candles each for BTC, ETH and XAUT; mark: 864 five-minute candles per contract; OI: 72 hourly candles per contract.
- BTC historical pilot: 1,051 candles, 100% observed coverage, zero gaps. The run uploaded no chart-review artifacts.

### Visual architecture — requirement still not met
- The current README, PR description and ai_analyst.py prompt are explicit: DNS is the mandatory primary location framework; trend pullback, momentum, breakout/retest, FVG, RBS/SBR, sweeps and range/mean-reversion are only confirmations/sub-setups at or near a qualifying DNS band. Standalone candidates away from DNS are rejected.
- Active runtime remains worker.py → dns_worker.py → ai_analyst.map_dns() for map refresh and dns_engine.detect_local_setup() for the local sweep/reclaim trigger. The broad multi-setup ai_analyst.analyse() function is not wired into this active worker. Therefore independent strategy families do not yet compete for the single best setup as requested. Do not describe the full multi-family visual desk as implemented.
- The branch workflow .github/workflows/alerts.yml has a 5-minute schedule but scheduled execution is gated by ENABLE_GITHUB_SCHEDULE == 'true'; manual dispatch is allowed. No visual-desk run or chart-review artifact was found in the current branch run list. Do not enable the schedule or dispatch an alerting run until API quota and paper-only validation prerequisites are confirmed.

### Risk controls, outcomes and Discord
- Current DNS worker retains fail-closed map-refresh handling, DNS quality/invalidation checks, sweep/reclaim confirmation, existing 0.35% entry/zone proximity and 2R gates, one open paper position per symbol, and fresh-market/current-map revalidation before delayed Discord alert retries.
- Strict numeric AI confidence >=75 is implemented in the separate main.validate_trade() path, but the active DNS worker does not call that validator. DNS-local signals are instead gated by the local detector's zone/structure/risk checks; do not claim both paths have identical checks.
- Paper outcomes require contiguous closed 5m coverage; a gap leaves the position unresolved rather than allowing a later TP/SL to be misreported as the first exit. Discord execution/outcome formatting is covered by tests, but no actual webhook delivery was established by CI.
- No chart images were available from the current CI run for visual inspection, and no new AI signal or trading recommendation was generated.

### Default-branch operational warning
- Latest observed scheduled default-branch run [42039207590](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42039207590), created 2026-11-05 13:49:34 UTC, completed successfully on main and executed the legacy python main.py step.
- Its job environment included configured DISCORD_WEBHOOK, DISCORD_WATCH_WEBHOOK and DISCORD_TRIGGER_WEBHOOK secrets (values masked). The run logs do not prove a Discord message was delivered.
- main/.github/workflows/alerts.yml still schedules advance-alerts every 10 minutes and runs the legacy main.py path. No changes were made to main; owner decision remains required before pausing the legacy workflow or cutover.

### Quant Discovery
- EXP-001 remains rejected (30/30 baseline OOS combinations negative). The OI + volatility expansion screen remains rejected for BTC, ETH and XAUT; no candidate is eligible for production alerts.
- Funding settlement-event attribution/units and historical spread/depth remain unresolved. No funding P&L conversion or performance claim is permitted.

### Exact next steps
1. Restore/confirm API project quota and verify the configured gpt-6-luna identifier against the actual API before any manual request. Do not change secrets in this workflow.
2. Redesign the analyst prompt/schema/validator so independent DNS, trend/pullback, momentum, breakout/retest and mean-reversion candidates can compete from chart evidence; preserve the visual model as decision-maker and return NO_TRADE when none passes.
3. Connect that multi-family selection to the active worker behind paper-only validation; keep mechanical gates and contiguous-bar outcome handling.
4. Only after quota is confirmed, manually run a paper-only cycle, inspect raw/annotated BTC/ETH/XAUT six-timeframe images, candidate comparisons and validator decisions, then verify Discord delivery and a complete paper outcome.
5. Obtain owner decision on the legacy main schedule before cutover. Do not modify main, merge PR #1, deploy, change secrets, enable live trading or place orders.

## Supervisor verification — 2026-11-05 20:20 IST (unreadable DNS-map resilience)

### Repository and CI
- Code/test head: `53bdde265fc6ed26f1b9aefd9e414daa826742c5`; PR #1 remains open, draft, unmerged and mergeable. The branch is 289 commits ahead of `main`, 0 behind, with 48 changed files.
- Code fix commit: `db12fba273077642eb9a179f06f8ceca180f0c60`. Regression-test commit: `53bdde265fc6ed26f1b9aefd9e414daa826742c5`.
- Exact-head workflow run [42048541172](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42048541172) completed successfully. Compilation, visual pipeline, DNS worker, replay, daily report, feedback, secret-format, derivatives parser/archive, Quant Discovery, live OHLCV, derivatives smoke and historical pilot steps all passed.
- The DNS/local watcher runner explicitly passed 17 tests, including new `test_worker_keeps_managing_positions_when_dns_map_is_unreadable`. No PR review threads were returned.

### Safety fix
- `dns_worker.run()` previously called `dns_engine.load_map()` before downloading fresh candles and managing existing paper positions. If the map file was corrupt/unreadable, the exception aborted the cycle before TP/SL/TIME monitoring.
- The worker now catches map-load failure, continues fetching fresh market candles and managing existing paper positions, but blocks pending/new entries for affected symbols. It does not automatically overwrite the unreadable map or invoke the AI mapper while the map is unavailable.
- Regression asserts position management runs once, the local detector and execution alert are not called, and state is saved.
- This is a fail-closed safety improvement; no entry threshold or live-trading capability changed.

### Fresh feed evidence (PR CI at 2026-11-05 14:48:52 UTC)
- All 18 BTCUSD / ETHUSD / XAUTUSD × 5m/15m/1h/4h/1d/1w closed-bar and freshness checks passed.
- Latest closed 5m snapshots: BTCUSD 78,846.50; ETHUSD 2,362.20; XAUTUSD 4,085.34. These are CI observations, not current quotes.
- Funding availability: 71 hourly candles per contract; mark: 864 five-minute candles per contract; OI: 72 hourly candles per contract.
- BTC historical pilot: 1,051 candles, 100% observed coverage, zero gaps.
- Workflow artifact list is empty; this CI run did not publish chart-review images and does not establish a live AI chart decision or Discord delivery.

### Remaining blockers and research status
- The active worker remains DNS-map + local sweep/reclaim only. The broad `ai_analyst.analyse()` multi-setup selector is not wired into the active worker, and actionable trades still require a DNS anchor. Independent trend/pullback, momentum, breakout/retest and mean-reversion candidates cannot yet compete independently.
- Branch `.github/workflows/alerts.yml` schedules every five minutes but scheduled execution is gated by `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; manual dispatch is permitted. Do not enable scheduled execution or dispatch an alerting run until API quota and paper-only prerequisites are confirmed.
- Last known OpenAI quota blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; no fresh API request was made. No new raw/annotated chart, AI decision or Discord webhook delivery is verified.
- The default `main` workflow still contains the legacy 10-minute `advance-alerts` schedule running `python main.py` with legacy Discord webhook configuration. The last specifically documented successful scheduled run is [42039207590](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42039207590) at 13:49:34 UTC. No `main` changes were made; owner decision remains required before pausing/cutover.
- EXP-001 and the OI/volatility expansion screen remain rejected. No validated edge or production-eligible research candidate exists. Funding event attribution/units and historical spread/depth remain unresolved.

### Exact next steps
1. Restore/confirm API project quota, then manually run one paper-only visual cycle and inspect raw/annotated BTC/ETH/XAUT six-timeframe images, model output, candidate comparisons, validator decisions and Discord delivery.
2. Redesign analyst prompt/schema/validator so independent evidence-supported setup families can compete and return `NO_TRADE` without a mandatory DNS anchor; connect it to the active worker only behind the existing mechanical risk gates.
3. Retain fail-closed map handling and contiguous 5m outcome coverage; unresolved positions remain open rather than generating unconfirmed exits.
4. Obtain owner decision on the legacy `main` schedule before any cutover. Do not modify `main`, merge PR #1, deploy, change secrets, enable live trading or place orders.

## Supervisor verification — 2026-11-05 21:07 IST (Discord confidence formatting)

### Repository / PR / CI
- Branch ai-quant-rebuild code/test head: 73da58f467b29ecbfc0c763b39221ef75b887b55. PR #1 remains open, draft, unmerged, mergeable; 292 commits ahead of main, 0 behind, 48 changed files. Main ref remains e93ee289b36d47ca774e9a285fc76a2f4cbb5795.
- Push CI [42056574107](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42056574107) and PR CI [42056587041](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42056587041) both completed successfully on the exact code/test head. Compile, visual pipeline, DNS worker, lifecycle, replay, reports, feedback, secret format, derivatives, Quant Discovery, live Delta feed and historical pilot steps passed.
- No open inline PR review threads were returned. The latest branch run did not upload chart-review artifacts; this was a CI test/feed run, not a visual-desk analysis cycle.

### Low-risk Discord formatting fix
- discord.send_ai_trade() previously used float(confidence), which treated booleans as numeric scores (True became 1/100), accepted numeric strings, and allowed fractional values even though the validator/schema require an integral score.
- Updated the formatter to display confidence only for a finite integral numeric value from 0 through 100. Booleans, strings, fractional, non-finite and out-of-range values are omitted; an integral float such as 86.0 is rendered as 86/100.
- Implementation commit: [d70db9c](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/d70db9c3e40552ee7b7bf7db5021bd628f214c4c).
- Regression commit: [73da58f](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/73da58f467b29ecbfc0c763b39221ef75b887b55). CI explicitly passed test_discord_execution_alert_rejects_malformed_confidence on push and PR runs. No risk thresholds changed.

### Fresh public market-data CI snapshot (2026-11-05 15:36:21 UTC)
- All 18 closed-bar/freshness checks passed for BTCUSD, ETHUSD and XAUTUSD across 5m, 15m, 1h, 4h, 1d and 1w.
- Latest closed 5m observations: BTCUSD 76,585.00; ETHUSD 2,284.35; XAUTUSD 4,094.78. These are CI observations, not current quotes or trade recommendations.
- Funding availability: 72 hourly candles per contract; mark: 864 five-minute candles per contract; OI: 72 hourly candles per contract.
- BTC historical pilot: 1,051 candles, 100% observed coverage, zero gaps. This pilot is a small archive smoke test, not the full research dataset.

### Model and visual pipeline
- Official OpenAI API documentation confirms gpt-6-luna is a valid Responses API model with image input and structured outputs. Sources: [Models](https://developers.openai.com/api/docs/models) and [GPT-6 Sol/Luna availability](https://openai.com/index/introducing-gpt-6-sol-and-luna/).
- This confirms model identifier/feature support only. The repository's API key quota and an actual Responses request were not tested; the last known live failure remains HTTP 429 insufficient_quota / credit_balance_exhausted.
- The active worker remains DNS-map + local sweep/reclaim. The analyst prompt requires every actionable candidate to be anchored to a directional DNS zone; trend pullback, momentum, breakout/retest and mean-reversion cannot compete independently. The broad multi-setup analyst is not yet wired into the active worker.
- No raw/annotated multi-timeframe chart artifacts or fresh model decision were available in this cycle. No Discord execution delivery was verified.

### Default-branch workflow
- Latest observed scheduled main run in the Actions listing: [42047540852](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42047540852), created 2026-11-05 14:42:05 UTC (20:12:05 IST), successful and explicitly ran legacy python main.py. The job environment contained configured legacy Discord webhook secrets (values masked); logs do not prove a Discord message was delivered.
- The preceding observed schedule run was [42039207590](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42039207590), created 13:49:34 UTC (19:19:34 IST). No later scheduled main run appeared in the first Actions page at this check; this is a schedule-gap observation, not proof the workflow is disabled.
- main/.github/workflows/alerts.yml still schedules the legacy advance-alerts workflow every 10 minutes. No main change was made. Owner decision remains required before pausing/cutover.

### Quant Discovery
- EXP-001 remains rejected; the OI/volatility-expansion screen remains rejected for BTC, ETH and XAUT. No candidate has survived the required OOS and cost robustness checks.
- Funding settlement-event attribution/units and historical spread/depth remain unresolved; no funding P&L conversion or profitability claim is permitted. The 1,051-candle BTC pilot is insufficient for the requested multi-year, multi-asset walk-forward research.

### Exact next steps
1. Keep the Discord confidence formatting fix; verify the latest documentation-only handoff commit's CI.
2. Restore/confirm API project quota, then run one manually dispatched paper-only visual cycle when available; inspect raw and annotated BTC/ETH/XAUT six-timeframe charts, model outputs, candidate comparison, validator decisions and Discord delivery.
3. Redesign the analyst prompt/schema/validator so independent evidence-supported setup families can compete and return NO_TRADE without a mandatory DNS anchor; wire this into the active worker only behind unchanged mechanical risk gates.
4. Expand and hash-verify the historical datasets for BTC, ETH and XAUT across required timeframes; retain chronological train/validation/OOS and walk-forward testing with realistic costs and explicit unavailable funding/spread inputs.
5. Obtain owner decision on the legacy main schedule before cutover. Do not modify main, merge PR #1, deploy, change secrets, enable live trading or place orders.

## Supervisor handoff — 2026-11-05 (AI-free deterministic multi-strategy quant desk)

### Architecture change on ai-quant-rebuild

User approved replacing the OpenAI/visual-AI decision-maker with a fully quantitative, rule-based multi-strategy supervisor. The new active paper runtime on this branch is:

worker.py -> quant_worker.py -> quant_strategies.py -> quant_supervisor.py

It does not import or call ai_analyst.py, dns_worker.py, or legacy main.py. It has no OpenAI API key/model/credit requirement. Public Delta OHLCV is still the market-data source. trade_lifecycle.py independently tracks already-open paper positions on contiguous closed 5m candles.

### Independent strategy families added

- TREND_PULLBACK: 4h/1h EMA trend agreement, 15m EMA20 pullback/reclaim, 5m breakout confirmation.
- BREAKOUT_RETEST: 1h 20-bar range break, 15m retest and close back through the level, 5m confirmation.
- VOLATILITY_EXPANSION: 15m ATR expansion versus its preceding 48-bar median, 20-bar breakout, 4h/1h direction.
- LIQUIDITY_SWEEP_REVERSAL: 15m sweep of the prior 20-bar high/low and close back inside the range, then 5m confirmation.
- MEAN_REVERSION: 1h Bollinger/RSI excursion and re-entry, gated to a balanced 4h regime.
- MOMENTUM_CONTINUATION: 1h directional return, 4h/1h alignment, 15m displacement and 5m follow-through.

Each strategy is an independent hypothesis and emits its own candidate; the engines do not combine incompatible directions or labels.

### Supervisor and paper safety

- Latest closed 5m price is the only candidate entry reference; stale or off-price candidates are rejected.
- Finite positive price levels and direction-specific SL/TP ordering are required.
- Minimum R:R remains 2.0.
- Stop distance must be between 0.35 and 2.5 ATR(15m).
- Rule-quality points must be an integer >=75; this is a transparent deterministic rubric, not a win probability.
- Reported R:R must match actual entry/stop/target geometry.
- A nearby opposing 4h swing obstacle invalidates a nominal 2R target.
- Opposing long/short candidates with less than an 8-point score separation yield NO_TRADE.
- One open paper position per symbol.
- All six timeframes must be fresh; the most recent 50 available bars (or all available bars when fewer exist) must be continuous. Weekly XAUT is allowed with its shorter listing history (20+ weekly bars); absence of a 50-week EMA is treated as no weekly trend, not fabricated context.
- Paper lifecycle remains gap-safe; missing bars prevent declaring a later TP/SL/TIME as the first confirmed exit.
- Discord execution formatting is quant-specific and labels the score as rule-quality points, not probability. No WATCH/status alerts.

### Promotion remains deliberately disabled

quant_supervisor.APPROVED_STRATEGIES remains an empty set. Existing EXP-001 and OI/volatility results were rejected and the new six rules have not yet completed a full historical out-of-sample/walk-forward/cost robustness run. Therefore candidates are logged as RESEARCH_ONLY; the quant worker sends no new execution alerts for them until a reviewed strategy promotion is recorded. Do not add strategy IDs to the allowlist based on synthetic tests or rule intuition.

### Runtime and workflow

- worker.py now runs the AI-free quant worker.
- Docker Compose service/container is salty-quant-paper-desk; OpenAI variables removed from .env.example and runtime compose configuration.
- .github/workflows/alerts.yml is now the branch paper desk workflow: manual dispatch or opt-in schedule (ENABLE_GITHUB_SCHEDULE=true); no OpenAI secret required; it runs quant_worker.py and uploads research/quant_signals.jsonl for 14 days.
- The persistent worker requires one instance and a writable persistent /data volume. No deployment was performed; the workflow schedule was not enabled.
- The legacy scheduled workflow on default main was not modified. Resolve that separately before any production cutover.

### Code/tests added

- trade_lifecycle.py
- quant_strategies.py
- quant_supervisor.py
- quant_worker.py
- test_quant_engine.py
- discord.send_quant_trade()
- Updated worker.py, Dockerfile, Compose, .env.example, README, CI and paper-desk workflow.

Latest commits as of this handoff: 7867722 (weekly-history regression), 278fa1c (weekly XAUT eligibility), 5df165f (ATR test fixture correction), 71465a0 / 64ed438 (paper lifecycle tests), 1858b20 (AI-free scheduled/manual paper workflow), 9cbf08f (README rewrite), plus the new quant engine/supervisor/test additions in the preceding commits.

### CI status at handoff

- The initial CI run on head ca6a251, run 42060881086, failed one new unit test because its fixture changed the stop but did not update its reported R:R. All earlier visual, DNS and replay tests passed; the new quant suite had 13/14 passing. The fixture was corrected in 5df165f.
- Another edge found during review: XAUT has only about 29 weeks of available weekly history. Requiring 55 weekly bars blocked all candidate evaluation for Gold despite sufficient 4h/1h/daily context. The minimum weekly context was lowered to 20 actual bars only; the weekly EMA50 remains unavailable and returns neutral/no trend. No missing bars were filled and no trade threshold was loosened.
- Regression test test_short_gold_weekly_history_keeps_lower_timeframe_strategies_available was added in 7867722.
- At the time of handoff, the latest new CI run for head 7867722 had not yet appeared in the GitHub workflow-runs endpoint. Re-check push and PR CI before further code edits; do not claim the new test suite is green until then.

### Historical data constraints / next research

- The Library archive salty_quant_historical_ohlcv_3y_verified.zip is available locally to the research operator and was previously verified at 926,209 candles across 18 BTC/ETH/XAUT datasets. Its manifest/coverage data must be rechecked before every experiment.
- BTC 5m has large gaps (largest 911,100 seconds); ETH 5m has large gaps (largest 164,400 seconds); XAUT begins 2026-04-17 and has only ~6.6 months/29 weekly candles. Missing data must remain missing; candidate generation should skip relevant windows.
- Next research task: build deterministic historical replay for each of the six strategy IDs against verified archives. Freeze each rule/config before chronological splits; use next-bar fills, same-bar SL-first handling, fees, spread/slippage stress and funding only after contract event-time attribution is independently verified. Report trade counts, win rate, expectancy, PF, max drawdown, longest loss streak, frequency, regime and robustness; all six strategy IDs stay research-only pending sufficient OOS/walk-forward evidence.
- Historical spread/depth is still unavailable; funding raw-unit/event attribution remains unresolved. Use explicit stressed-cost scenarios rather than silently setting unknown costs to zero.

### Safety boundaries

No main modifications, PR merge, deployment, secrets change, scheduled-workflow enablement, live trading or exchange orders. PR #1 remains a draft and unmerged. The new system is a deterministic paper/shadow desk, not a validated profitable trading system.


---

## Latest research handoff

See [Quant Discovery first chronological multi-asset screen — 2026-11-05](quant_discovery/SCREEN_2026-11-05.md) for the verified archive hash, frozen hypotheses, OOS/walk-forward metrics, cost assumptions, decision and exact next steps.
