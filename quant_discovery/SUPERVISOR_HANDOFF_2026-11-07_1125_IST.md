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
