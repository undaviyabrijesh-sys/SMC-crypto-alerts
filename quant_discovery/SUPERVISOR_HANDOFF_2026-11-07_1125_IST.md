# Salty Quant Supervisor Handoff — 2026-11-07 11:25 IST

## Exact repository checkpoint

- Repository: private `undaviyabrijesh-sys/SMC-crypto-alerts`.
- Working branch: `ai-quant-rebuild` only.
- Code/test checkpoint immediately before this handoff: [`c46133d15af93138c4be064daa976d33a1ced05d`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/c46133d15af93138c4be064daa976d33a1ced05d).
- PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1) remains open, draft, unmerged and mergeable. Base is `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- Do not merge PR #1 or modify `main`.

## Changes in this cycle

### EXP-003 same-candle timestamp bug

- The full historical run [42341048484](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42341048484) validated all 18 OHLCV datasets, completed EXP-001 and EXP-002, then failed in EXP-003 `validate_trades()` with `Trade exit timestamp must follow entry timestamp`.
- Downloaded and inspected its actual EXP-002 trade artifact: 8,191 OOS shadow trades; **1,112 (13.576%) have equal entry_time and exit_time; zero exit-before-entry rows**.
- This equality is valid in the source replay: entry is the next candle's open, and a stop/target may be hit during that same candle. Both fields are candle-open timestamps; the outcome is not visible until that candle closes.
- Fixed `quant_discovery/strategy_discovery.py` to reject only `exit_time < entry_time`. The existing `outcome_available_at = exit_time + timeframe duration` remains unchanged, preserving the no-look-ahead boundary.
- Added regression tests for a valid same-candle exit (including zero holding hours and availability only at candle close) and rejection of an exit before entry.
- The first test attempt exposed a test-fixture keyword mistake; corrected in [`c46133d`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/c46133d15af93138c4be064daa976d33a1ced05d).
- Exact code/test head CI: push [42344549231](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42344549231) and PR [42344552670](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42344552670) — **both success**. Quant Discovery unit suite: **27 tests passed**, including both new timestamp regressions.

### Fresh archive and EXP-001 / EXP-002 evidence

- The failed EXP-003 run still uploaded complete, verified artifacts:
  - OHLCV archive artifact ID `13562130235`, SHA-256 `63b33a096d4d577eb8111752b5a6944976883455f8d2c59a05c8bf6d24507ef7`.
  - Research artifact ID `13561499378`, SHA-256 `13c6d6da40cfd4c7909dc6b3c9da26a4f635f0c0f1c954cfaff7241e0f00a2c4`.
  - Both were still available when inspected; expiry was 2026-11-21 around 05:10 UTC.
- Archive validation: **18/18 datasets, 931,337 candles, no validation errors**. Venue/source is Delta Exchange India. BTC 5m had 6 internal gaps (98.9919% coverage), BTC 15m 3 gaps (99.7684%), BTC 1h 1 gap (99.9241%); ETH 5m 3 gaps and 15m 1 gap; all XAUT timeframes reported zero gaps. XAUT 1w contains only 29 bars, so weekly XAUT conclusions are not reliable.
- EXP-001: all 30 asset × timeframe × family OOS cells were negative at the 10 bps scenario. Least-negative row: BTC 1h mean reversion, n=177, 39.55% wins, -0.0205R expectancy, PF 0.969, max DD -18.078R, 7 consecutive losses.
- EXP-002: 42 asset × timeframe × strategy OOS cells, 8,191 shadow trades. Four cells were slightly positive at 10 bps; **all 42 were negative at 20 and 40 bps**. The four 10 bps positives:
  - BTC 1h EMA crossover: n=44, 43.18% wins, +0.0658R, PF 1.098, max DD -11.644R, 10-loss streak.
  - ETH 1h Bollinger squeeze: n=48, 41.67% wins, +0.0516R, PF 1.075, max DD -7.931R, 6-loss streak.
  - ETH 1h stochastic trend pullback: n=182, 42.86% wins, +0.0500R, PF 1.080, max DD -21.661R, 9-loss streak.
  - ETH 1h ADX/DMI trend: n=125, 41.60% wins, +0.0191R, PF 1.029, max DD -12.665R, 6-loss streak.
- Reject all EXP-001/002 candidates for promotion. The 10/20/40 bps costs and 1 bp per 8h adverse carry are assumptions, not measured spread, slippage or realized funding. Funding units/sign/settlement attribution remain unresolved.
- EXP-003 remains research-only. Its five prequential slices carry forward prior outcomes and are not independent OOS folds; each strategy stream is treated as a full-information shadow expert. A positive selector result would still require an untouched future dataset and stronger execution-cost evidence.
- `quant_supervisor.APPROVED_STRATEGIES = frozenset()`. No candidate has been promoted.

### Visual-first chart-to-AI pipeline

- Preserve the visual-first decision path. The analyst receives raw multi-timeframe chart images (5m/15m/1h/4h/1d/1w) and compares independent SMC/structure, supply-demand, liquidity sweep, support/resistance, trend/pullback, momentum, breakout/retest, volatility and mean-reversion candidates. It selects at most one actionable candidate or `NO_TRADE`; the coded DNS/zone engine is not the decision-maker.
- Mechanical validation remains fail-closed: confidence >=75, quality >=75, R:R >=2, stop distance 0.35–2.5 trigger-timeframe ATR, entry band within 0.35% of the latest closed 5m price, at least two distinct evidence timeframes including the trigger timeframe, one open/pending position per symbol, and an opposing candidate must be at least eight quality points weaker.
- Discord visual alerts are execution-focused and include setup, entry band/price, stop, target, R:R, trigger, context, rationale, target rationale, invalidation, supporting/conflicting evidence and cancellation conditions. `discord._post()` refuses messages over 1,900 characters rather than truncating.
- Lifecycle uses closed 5m candles, conservative same-candle SL-first handling and gap-aware TP/SL/TIME confirmation. Outcome updates are separate from entry alerts.
- No chart-image bundle was attached to current CI; the visual tests are mocked. No real vision cycle or actual Discord webhook delivery is proven. Last recorded OpenAI blocker is HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested. The visual lane remains opt-in; no visual schedule or workflow was activated in this cycle.

### Trade idea ledger and feed state

- Latest committed Crypto Trade-Idea Desk scan: 2026-11-07 05:14:42 UTC (10 liquid USDⓈ-M symbols), verdict `NO_TRADE`; no confirmed Discord entry alerts were recorded.
- SUI short remains watch-only: latest closed 15m close 0.8655 above 0.8615; volume 0.35× its 20-bar average; no breakdown plus failed retest.
- Known prior unalerted shadow ideas: ZEC long had a stop touch; ETH short had neither stop 2256 nor target 2205.11 touched at the last recorded check. Neither is a confirmed Discord trade.
- Critical continuity limitation: ledger `recovery_status=partial_unverified`; old Actions-cache `state.json` could not be recovered. Empty `active_alerted_setups` is not proof that no other worker position exists. Actions cache is not a durable lifecycle store.

## Current blockers and next actions

1. This handoff commit intentionally triggers a fresh historical archive run on the fixed EXP-003 code. Re-check its run, verify all 18 datasets, then inspect EXP-003 summary, five chronological slices, selected-trade counts, per-asset results, max DD/loss streak and 10/20/40 bps cost sensitivity. Do not infer success from the previous failed run.
2. Compare EXP-003 with EXP-001/002; do not promote a selector based on a small sample or these reused shadow streams. Keep the allowlist empty.
3. Owner must restore OpenAI quota before a real visual cycle can be run. After restoration, explicitly dispatch one paper-only visual cycle and inspect chart images, hashes/watermarks, model comparison, validator decision and actual Discord delivery.
4. Replace evictable Actions-cache state with durable persistence and reconcile old positions before claiming continuous lifecycle coverage.
5. Verify funding units, sign, interval and settlement timestamps against contract metadata and an independently observed realized event. Obtain historical spread/depth or keep those costs as clearly labelled stress assumptions.
6. Keep PR #1 draft/unmerged, `main` untouched, no deployment, no secret changes, no live trading and no exchange orders.

## Safety

This checkpoint did not modify `main`, merge PR #1, deploy infrastructure, change secrets, enable live trading, submit orders, or send a new Discord execution alert.

## Addendum — supervisor re-check, 2026-11-07 11:30 IST

### Archive trigger correction and current run

- The initial handoff commit `f41e237` did not start the archive: the workflow's push path filter only watched its own YAML file. This was corrected in [`15f5de4`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/15f5de4fe05bc341ea56a9fe16f99be888e240eb), which now also watches `bootstrap_historical_data.py` and the EXP-001/002/003 runner source files. A deliberate `RUN_HISTORICAL_ARCHIVE:` commit is still required.
- The corrected trigger started [Historical OHLCV archive run 42344719278](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42344719278) on fixed EXP-003 code. At this checkpoint its 3-year BTC/ETH/XAUT download step was still running; no EXP-003 result is claimed yet.
- The derivatives archive workflow was correctly skipped. The deterministic CI for workflow commit `15f5de4` passed on push [42344719411](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42344719411) and PR [42344723554](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42344723554). The PR remains draft/open/unmerged with head `15f5de4`.

### EXP-002 robustness interpretation

The four small positive 10 bps OOS rows are not stable across walk-forward folds or regimes:

- BTC 1h EMA crossover: only WF4 was positive (+0.3071R); WF1/WF2/WF3/WF5 were negative. Down regime was +0.3211R (n=17) while up regime was -0.0950R (n=27).
- ETH 1h ADX/DMI: only WF4 (+0.0154R) and WF5 (+0.0226R) were marginally positive; the first three folds were negative. Low-volatility expectancy was +0.0765R versus -0.0866R in high volatility.
- ETH 1h Bollinger squeeze: WF2/WF3/WF4 positive, WF1/WF5 negative. Low-volatility expectancy was +0.3561R (n=36) versus -0.8618R in high volatility (n=12).
- ETH 1h stochastic pullback: only WF5 positive (+0.2595R); WF1–WF4 were negative. High-volatility expectancy was +0.1523R versus -0.0592R in low volatility.

Together with all 42 cells turning negative at 20/40 bps, these results are fold- and regime-dependent, with weak sample sizes and drawdowns. None qualifies as a robust edge.

### Live public feed verification

- The exact-head deterministic CI smoke at 2026-11-07 05:55 UTC passed all **18/18** BTC/ETH/XAUT production symbol/timeframe combinations. Each instrument returned 1,151 closed 5m candles, 1,343 15m, 1,079 1h, 719 4h, 364 1d (XAUT 204) and 29–149 1w candles. The 5m/15m/1h last-close ages were approximately 0.9/10.9/55.9 minutes at probe time.
- Funding (70 hourly), mark (864 five-minute) and open-interest (72 hourly) public series were available for BTCUSD, ETHUSD and XAUTUSD. Availability is not proof of correct funding units/sign or realized settlement attribution.
- No raw multi-timeframe chart bundle was produced by this CI. Visual analyst tests are mocked; no real vision call, execution alert or Discord webhook delivery is claimed.


## Addendum — supervisor re-check, 2026-11-07 11:52 IST

### EXP-003 archive result and walk-forward defect

- Historical OHLCV archive run [42344719278](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42344719278) completed successfully. It verified 18/18 BTC/ETH/XAUT CSV datasets (931,337 candles) and completed EXP-001, EXP-002 and EXP-003. Research artifact ID: `13562749052`; archive artifact ID: `13562484386`; both expire around 2026-11-21 06:02 UTC.
- The first EXP-003 summary is negative at every tested cost. At 10 bps round trip: Follow-the-Winner n=707, expectancy -0.18075R, PF 0.7711, max DD -131.7574R, 11-loss-event streak; Follow-the-Loser n=2,343, -0.42300R, PF 0.5678, max DD -1003.4532R, streak 18; Pattern Match n=614, -0.22922R, PF 0.7151, max DD -148.8300R, streak 9; Meta-Ensemble n=966, -0.20684R, PF 0.7428, max DD -207.4331R, streak 13. All policies were also negative at 20 and 40 bps. These are research-only shadow-selector results, not production or live fills.
- Artifact inspection found a reporting defect: all 10,544 selected trades had a null walk-forward fold, so every one of the 240 fold/asset/policy/cost rows reported n=0. GitHub Actions installed pandas 3.1.1, which preserves inferred datetime resolution; the code converted timestamps to int64 seconds but compared them with nanosecond `Timestamp.value` bin edges. Overall summary counts were present, but the walk-forward breakdown was invalid and must not be used.
- Fixed this on `ai-quant-rebuild` in [`547fd6a`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/547fd6a6d4d3509af3c1a18f7c78608d50496317): EXP-003 now bins timezone-aware datetimes directly. The synthetic end-to-end regression now requires every selected trade to have a fold and the five fold counts to sum exactly to the corresponding summary counts.
- Exact-head push CI [42346505999](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42346505999) and PR CI [42346511540](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42346511540) both passed. Quant Discovery unit suite: 27 tests passed. Fresh corrected archive rerun [42346506072](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42346506072) is running; do not report corrected folds or new EXP-003 metrics until its artifact is inspected.
- EXP-001 remains negative across all 30 OOS cells at 10 bps. EXP-002 remains fragile: four of 42 cells were slightly positive at 10 bps, all 42 negative at 20/40 bps, and the small positives were fold/regime-sensitive. No candidate is promoted; `APPROVED_STRATEGIES` remains empty.

### Current feed, visual, risk and lifecycle state

- Exact-head CI again passed the public Delta feed probe for all 18 production symbol/timeframe combinations. Latest 5m/15m/1h close ages were approximately 0.5/5.5/20.5 minutes at the 06:20 UTC probe. Funding, mark and OI public series were available for BTCUSD, ETHUSD and XAUTUSD; availability does not validate funding units/sign or realized settlement attribution.
- Visual analyst still compares independent chart-supported setup families from raw 5m/15m/1h/4h/1d/1w images; deterministic code only applies data, arithmetic and risk gates. Confidence/quality >=75, minimum 2R, stop 0.35–2.5 trigger ATR, entry deviation <=0.35%, at least two distinct evidence timeframes including trigger, one open/pending position per symbol, and opposing-candidate quality margin >=8 remain unchanged.
- Discord visual alerts include entry band, entry, stop, target, R:R, trigger, context, rationale, target rationale, invalidation, supporting/conflicting evidence and cancellation conditions; messages over 1,900 characters are refused. Lifecycle remains closed-5m TP/SL/TIME with conservative same-candle SL-first and gap-aware confirmation.
- No fresh chart-image bundle, real vision call or actual Discord webhook delivery was produced. The last recorded OpenAI API blocker is HTTP 429 insufficient quota; exact-head CI's visual requests are mocked. Visual lane remains opt-in and no recurring visual worker was activated.
- Trade-idea ledger still records its last scan at 05:14:42 UTC as NO_TRADE, with no confirmed Discord entry delivery. Recovery remains partial/unverified because prior Actions-cache state could not be recovered; do not claim continuous position reconciliation.
- PR #1 remains open/draft/unmerged, based on `main` at `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`. No `main` change, deployment, secret change, live trading or exchange order.

### Exact next steps

1. Re-check run 42346506072 until complete; verify 18 dataset hashes and inspect corrected EXP-003 selected-trade fold coverage, five chronological slices, per-asset metrics, 10/20/40 bps sensitivity, drawdown, loss streak and regime dependence.
2. Compare corrected EXP-003 with EXP-001/002; keep all candidates rejected unless a separate untouched future dataset and realistic execution-cost evidence validate them.
3. Owner action: restore OpenAI API quota, then dispatch a single paper-only visual cycle and verify actual chart images, image watermarks, model output, validator decision and Discord delivery.
4. Replace evictable Actions-cache state with durable position storage and reconcile prior positions before claiming complete lifecycle tracking.
5. Validate Delta funding units, sign, interval and settlement timestamps against contract metadata and a realized event; obtain historical spread/depth or retain costs only as stress assumptions.
6. Keep PR #1 draft/unmerged and `main` untouched. No deployment, secrets, live trading or orders.


## Addendum — corrected EXP-003 replay completed, 2026-11-07 12:00 IST

### Historical archive and coverage audit

- Corrected replay [run 42346506072](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42346506072) completed successfully. All 18 expected Delta Exchange India CSV datasets passed row-count and SHA-256 validation; total **931,532 candles**. Research artifact ID `13564220631`; OHLCV archive artifact ID `13563074167`; both expire 2026-11-21.
- Coverage is not three full years for every instrument. BTC starts 2023-12-29; ETH starts 2024-02-06; XAUTUSD (Gold proxy) starts only 2026-04-17, so Gold has about 6.7 months of history and only ~18.6% of the requested three-year coverage. XAUT has 100% coverage within that shorter observed span, but its sample is insufficient for a multi-year robustness claim.
- BTC history contains material gaps: 5m has 7 gaps (largest ~8.4 days), 15m has 3 (largest ~34 hours), and 1h has 1 (~19 hours). ETH has 4 gaps on 5m and 1 on 15m (largest ~17.8 hours); higher timeframes had no reported gaps. Gap-affected windows must be excluded or explicitly modeled before relying on regime or execution conclusions.

### EXP-003 corrected walk-forward results

- The pandas datetime-resolution fix is confirmed by the production archive: **10,570 selected trades, zero null folds**. Fold counts: WF1 1,758; WF2 2,364; WF3 1,859; WF4 1,936; WF5 2,653. The five-fold totals reconcile to the selected-trade count for each policy/asset/cost summary.
- At 10 bps round-trip stress:
  - Follow-the-Winner: n=711, win rate 35.86%, expectancy -0.18277R, PF 0.7688, max DD -133.9182R, max loss streak 11, ~104 trades/month; all five folds negative.
  - Follow-the-Loser: n=2,349, 34.65%, -0.42457R, PF 0.5664, max DD -1009.6958R, streak 18, ~344/month; all five folds negative.
  - Pattern Match: n=614, 34.04%, -0.22922R, PF 0.7151, max DD -148.8300R, streak 9, ~90/month; all five folds negative.
  - Meta-Ensemble: n=970, 34.74%, -0.20821R, PF 0.7413, max DD -209.5939R, streak 13, ~142/month; all five folds negative.
- At 20 bps, all four policies remain negative overall. Follow-the-Winner is positive in only one of five folds (+0.04805R) but has overall expectancy -0.16109R; the other three policies are negative in all five folds. At 40 bps, all four policies are negative; Follow-the-Loser degrades to -1.74270R expectancy, PF 0.1379, max DD -4397.0432R and a 40-loss streak. Several 40 bps policies have very small samples or empty folds.
- EXP-001: 0/30 OOS cells positive. EXP-002: 4/42 positive at 10 bps, but 0/42 at 20/40 bps; small positives remain fold/regime fragile. EXP-003's corrected folds are now usable, but no selector is profitable across costs and chronological folds.
- These are historical shadow-trade results using stated cost/carry stress assumptions. Historical spread, depth, executable impact and realized funding attribution are not available. **No candidate is a validated edge.** Keep `APPROVED_STRATEGIES` empty and do not route any of these results into alerts.

### Current release and visual pipeline state

- Latest code/test commit remains [`547fd6a`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/547fd6a6d4d3509af3c1a18f7c78608d50496317); latest handoff commit before this addendum is `6ae8ce91`. Push CI [42346685689](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42346685689) and PR CI [42346690266](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42346690266) passed on the handoff head.
- PR #1 remains open, draft, unmerged and mergeable. Its base and live `main` SHA remain `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`; no `main` commit was made.
- Public Delta feed smoke checks passed all 18 symbol/timeframe combinations at the 06:20 UTC probe. Funding, mark and OI endpoints responded for BTC, ETH and XAUT, but funding sign/settlement accounting is not validated.
- No fresh chart bundle, real vision inference or Discord webhook delivery was produced. The visual worker remains manual/opt-in; OpenAI quota HTTP 429 remains the recorded blocker. No execution alert was sent in this cycle.

### Exact next steps

1. Find or connect a longer, gap-audited Gold/XAUT history source before treating Gold results as comparable with BTC/ETH; preserve the Delta XAUT dataset as a separate short-history sample.
2. Quantify and mask BTC/ETH gap windows, then rerun chronological/walk-forward comparisons with realistic fees, spread, slippage and validated funding.
3. Require a separate untouched future period and robustness across regimes/costs before considering any candidate an edge; keep the production allowlist empty.
4. Restore OpenAI API quota and perform one explicitly authorized paper-only visual cycle with actual chart images, response validation and confirmed Discord delivery.
5. Continue to treat the Actions cache as best-effort state recovery, not a durable ledger; recover/verify any open positions before claiming full lifecycle continuity.
6. Keep PR #1 draft/unmerged and `main` untouched. No deployment, secret changes, live trading or exchange orders.
