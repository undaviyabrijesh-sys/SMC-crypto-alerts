# Salty Quant Supervisor Handoff — 2026-11-07 09:19 IST

## Exact repository checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Functional fix commit: [`0da36e35480971e8e43294f7f90cc8b32a8a725d`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/0da36e35480971e8e43294f7f90cc8b32a8a725d) — quant active-symbol guard now includes pending visual alerts.
- Regression test commit / branch head before this handoff: [`2b6b626002fd82a966d33801fa7c45c3aee2aaf8`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/2b6b626002fd82a966d33801fa7c45c3aee2aaf8).
- Base `main`: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`; main was not modified.
- PR #1 is open, draft, mergeable and unmerged; 441 commits ahead, 0 behind, 89 changed files. No submitted reviews or inline review threads.
- Do not merge PR #1 or modify `main`.

## Fix made in this supervision pass

A cross-lane duplicate-prevention gap was found:

- `visual_worker.py` correctly treats open positions, legacy pending alerts and `pending_visual_alerts` as active for a symbol.
- `quant_worker.py::_active_symbol()` previously checked only open positions and legacy `pending_alerts`. A failed visual Discord delivery could leave a pending visual signal, while a subsequent deterministic quant cycle would not see it and could select another same-symbol entry if a strategy were ever approved.
- Fixed `_active_symbol()` to include `pending_visual_alerts`. No strategy rules, approval allowlist, risk threshold, or alert behavior was changed.
- Added `test_pending_visual_alert_blocks_quant_entry_for_same_symbol`, asserting BTC is blocked while its visual alert is pending and ETH remains unaffected.
- GitHub diff confirms only `quant_worker.py` and `test_quant_engine.py` changed in these two functional commits.

## CI evidence for the fix

- PR CI [run 42335852251](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42335852251), run number 754, completed successfully on exact test head `2b6b626002fd82a966d33801fa7c45c3aee2aaf8`.
- All 24 job steps completed; all 21 substantive steps passed.
- Log explicitly reports `test_pending_visual_alert_blocks_quant_entry_for_same_symbol ... ok`.
- Visual pipeline, independent visual-first mocked cycle, workflow contract, DNS watcher, quant replay, risk/supervisor, daily report, feedback, secret-format, derivatives parser/archive, Quant Discovery, live Delta OHLCV, derivatives probes and historical BTC pilot all passed.
- Artifact list for this PR run was empty. The GitHub connector's commit-workflow-runs view filters to PR-triggered runs; no separate push-triggered run was independently verified. Combined commit-status endpoint returned no separate status records. Do not claim push CI or external required-check enforcement.
- A non-blocking Node `url.parse()` deprecation warning appeared.

## Latest CI data-feed snapshot (not current quotes)

The successful CI log recorded the Delta public feed probe at approximately **2026-11-07 03:51:51 UTC**. All 18 instrument/timeframe checks passed across BTCUSD, ETHUSD and XAUTUSD, for 5m, 15m, 1h, 4h, 1d and 1w.

| Instrument | 5m close | 15m close | 1h close |
|---|---:|---:|---:|
| BTC | 75,818.50 | 75,761.50 | 76,007.50 |
| ETH | 2,241.15 | 2,239.85 | 2,246.20 |
| XAUT | 4,064.81 | 4,064.81 | 4,064.02 |

- Funding hourly: BTC 68, ETH 68, XAUT 72 candles.
- Mark price 5m: 864 candles per instrument.
- Open interest hourly: 72 candles per instrument.
- BTC historical 5m pilot: 1,051 candles, 100% coverage, zero gaps; SHA-256 prefix `a81466d2b82a`.
- XAUT weekly series remains only 29 candles. Do not make long-horizon claims from this sample.
- These are timestamped CI observations, not guaranteed current market prices.

## Visual-first chart-to-AI path

Inspected branch files `visual_first_analyst.py`, `visual_worker.py`, `visual_chart.py`, `trade_lifecycle.py`, `discord.py`, `state.py`, `quant_worker.py`, `alerts.yml` and `tools.yml`.

- The independent visual analyst receives raw six-timeframe images (5m, 15m, 1h, 4h, 1d, 1w) and compares SMC/market structure, supply-demand, liquidity sweeps, support/resistance, trend pullbacks, momentum, breakout/retest, volatility expansion, mean reversion and other evidence-supported families.
- It selects at most one candidate or `NO_TRADE`. `visual_worker.py` imports `visual_first_analyst` and `visual_chart.render_symbol_chart`; it does not import the DNS/zone decision engine. The chart renderer is called without DNS annotations in this lane. Coded DNS is not the decision-maker.
- The validator checks fresh candle watermarks, analysis timestamp, candidate IDs, MARKET entry eligibility, entry-zone distance, directional entry/stop/target geometry, actual R:R, ATR stop distance, confidence/quality, distinct timeframe evidence, supporting evidence, cancellation conditions, existing positions and opposing actionable candidates.
- Hard thresholds unchanged: confidence >=75; quality >=75; minimum R:R >=2.0; stop 0.35–2.5 trigger-timeframe ATR; entry band within 0.35% of latest closed 5m price; at least two distinct evidence timeframes including trigger; one open or pending paper position per symbol; opposing actionable candidate must be at least eight quality points weaker or the cycle fails closed.
- `tools.yml` visual run requires manual `task=visual-desk-run` and `confirm_visual_paper=true`. `alerts.yml` scheduled runs are opt-in and run AI-free `quant_worker.py`; a manual visual cycle is explicitly confirmed and paper-only.
- Latest CI used mocked model requests. No real chart bundle, OpenAI vision response, selected real paper signal or Discord webhook delivery was verified. Last documented OpenAI blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested. No workflow was dispatched.

## Discord and outcome lifecycle

- Shared `discord._post()` rejects messages above 1,900 characters instead of truncating.
- Visual alert includes setup family, entry zone/price, stop, target, validated R:R, trigger timeframe/condition, higher-timeframe context, rationale, target rationale, invalidation, evidence, conflicts and cancellation conditions.
- Lifecycle uses closed 5m candles, conservative same-candle SL-first resolution, gap-aware exit handling and separate TP/SL/TIME updates. Missing candles can leave an outcome unresolved rather than fabricating an exit.
- Cross-run state still relies on GitHub Actions cache and may be evicted. Outcome P&L is gross before fees, spread, slippage and funding.

## Quant Discovery

- `quant_supervisor.APPROVED_STRATEGIES = frozenset()`; no strategy is approved for production.
- EXP-001: all 30 baseline OOS combinations and 270 stop/target variants were negative at 10 bps round-trip plus 1 bp/8h adverse carry stress. Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, seven consecutive losses, 25.76 trades/month.
- OI expansion remains rejected: BTC negative; ETH's small positive 10 bps OOS result fails train/validation consistency and turns negative at 20 bps; XAUT has only 14 OOS trades and turns negative at higher cost.
- Historical OHLCV archive: 926,209 candles across 18 datasets. Derivatives archive: 758,119 candles across nine BTC/ETH/XAUT series. XAUT begins 2026-04-17 (~6.6 months).
- Funding units/sign and settlement-event attribution remain unresolved. Do not treat hourly funding candle closes as realized cashflow. Historical executable spread/depth/market impact are unavailable; costs are stress assumptions, not measured fills.
- Do not rerun identical screens without new validated data or a pre-registered hypothesis. No research candidate enters execution alerts.

## Derivatives archive preservation

- GitHub Actions artifact `13383865992`, source run [41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516), was previously downloaded and preserved outside Actions retention.
- Mounted ZIP re-verified during this pass: 16,854,903 bytes, 12 files, SHA-256 `f16d0bc18eddcce7637c9643d9176590c8bb55fe9de6be1da9c717bdf7949a27`.
- Durable Library backup recorded at `/Salty Quant Research/salty-quant-derivatives-archive-13383865992.zip`.
- Original GitHub artifact expires **2026-11-19 02:37:57 UTC**. Verify the Library copy hash again if rematerialized.

## Blockers and exact next steps

1. Restore/confirm OpenAI project quota through owner controls. Do not change secrets in this workflow.
2. After quota is restored, the human owner must explicitly confirm one paper-only visual cycle through GitHub Actions manual dispatch (`task=visual-desk-run`, `confirm_visual_paper=true`). Inspect raw chart artifacts, image hashes/watermarks, model candidate comparison, validator result and actual Discord delivery.
3. Improve durable position persistence beyond evictable Actions cache before relying on uninterrupted long-running tracking.
4. Verify funding interval, units, sign and settlement timestamps against contract metadata, WebSocket `fi`/`nfr` and an independently observed realized funding event before funding-adjusted backtesting.
5. Owner should inspect branch protection / required CI settings. Previous integration attempts could not read protection/ruleset state; do not claim required checks are enforced.
6. Keep PR #1 draft and unmerged; keep main unchanged. No live trading, orders, deployments, secret changes, schedule activation or risk-threshold reductions.

## Safety

Only `ai-quant-rebuild` was changed. No main changes, PR merge, deployment, secret modification, manual visual workflow dispatch, schedule activation, live trading, exchange orders or unvalidated strategy promotion were performed.
