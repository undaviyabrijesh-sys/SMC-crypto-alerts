# Salty Quant Supervisor Handoff — 2026-11-07 08:08 IST

## Exact repository checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Branch and PR head before this handoff-only commit: [`a2e0d342013cf8bc64eb3e1df16b4b58c5c5aba4`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/a2e0d342013cf8bc64eb3e1df16b4b58c5c5aba4).
- Parent commit message: `Record Salty Quant supervision and preserve derivatives archive`; it adds only `quant_discovery/SUPERVISOR_HANDOFF_2026-11-07_0714_IST.md`. No functional source code changed after the last verified Discord sender fix.
- Base `main`: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`; main was not modified.
- PR #1 is open, draft, mergeable and unmerged; 438 commits ahead per PR metadata, 88 changed files. No submitted reviews or inline review threads.
- This document is committed as a new handoff-only commit on `ai-quant-rebuild`. Resolve the branch ref after this commit to obtain the exact post-handoff SHA; the parent checkpoint above is exact and reproducible.
- Do not merge PR #1 or modify `main`.

## CI at the parent checkpoint

- Push CI [42325857661](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42325857661): success.
- PR CI [42325862511](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42325862511): success.
- Both ran against exact head `a2e0d342013cf8bc64eb3e1df16b4b58c5c5aba4`.
- Both jobs completed all 21 substantive steps successfully: Python compilation; offline visual pipeline; independent visual-first contracts and mocked paper cycle; manual workflow contract; Bull/Bear/Chief agent contracts; DNS watcher; quant replay; AI-free multi-strategy supervisor; daily report; strategy feedback; OpenAI secret format; derivatives parser/archive; Quant Discovery tests; live Delta OHLCV; funding/mark/OI probes; and historical BTC pilot.
- Both workflow artifact lists were empty. These were CI and mocked tests, not a real visual dispatch, OpenAI vision response, paper signal, or Discord webhook delivery.
- Node.js 20 deprecation warnings appeared for GitHub Actions dependencies; non-blocking, no failed step.

## Latest verified data-feed snapshot (not current quotes)

Push/PR CI logged the live Delta probe at **2026-11-07 01:47:26–33 UTC (07:17:26–33 IST)**. At 08:08 IST this snapshot is about 51 minutes old.

- All 18 BTCUSD / ETHUSD / XAUTUSD combinations across 5m, 15m, 1h, 4h, 1d and 1w passed closed-bar, timestamp, OHLC and freshness checks.
- Closed 5m closes: BTC **75,974.00**, ETH **2,244.05**, XAUT **4,064.79**.
- Candle counts: 5m 1,151; 15m 1,343; 1h 1,079; 4h 719. Daily: BTC 364, ETH 364, XAUT 204. Weekly: BTC 149, ETH 143, XAUT 29.
- Funding hourly: BTC 66, ETH 66, XAUT 70. Mark price 5m: 864 per instrument. OI hourly: 72 per instrument.
- BTC historical 5m pilot: 1,051 candles, 100% coverage, zero gaps; SHA-256 prefix `4aeeb751b0c6`.
- XAUT weekly history remains short (29 candles); do not treat the weekly series as a robust long-horizon sample.
- These are timestamped CI observations, not current market prices. No new feed probe was run after 07:17 IST in this pass.

## Visual-first chart-to-AI pipeline

Inspected branch versions of `visual_first_analyst.py`, `visual_worker.py`, `trade_lifecycle.py`, `discord.py`, `state.py`, `.github/workflows/tools.yml`, `.github/workflows/alerts.yml`, and the V2 analyst spec.

- The analyst receives raw six-timeframe images (5m, 15m, 1h, 4h, 1d, 1w), compares independent SMC/market structure, supply-demand, liquidity sweeps, support/resistance, trend pullbacks, momentum, breakout/retest, volatility expansion, mean reversion and other evidence-supported setups.
- It selects at most one candidate or `NO_TRADE`. The analyst module has no DNS/zone-engine dependency. Coded DNS/zone/sweep logic is not the decision-maker; the validator does not substitute another candidate.
- Validator checks exact chart watermarks, analysis timestamp (within ±2 minutes), candidate IDs, selected candidate, market-entry eligibility, entry-zone deviation, directional entry/stop/target geometry, actual R:R, ATR stop distance, confidence/quality, distinct timeframe evidence, supporting evidence, cancellation conditions, open positions and opposing candidates.
- Hard thresholds unchanged: confidence >=75; quality >=75; minimum R:R >=2.0; stop 0.35–2.5 trigger-timeframe ATR; entry band within 0.35% of latest closed 5m price; at least two distinct evidence timeframes including trigger; one open/pending paper position per symbol; opposing actionable candidate must be at least eight quality points weaker or the cycle fails closed.
- `tools.yml` visual run requires `task=visual-desk-run` and `confirm_visual_paper=true`. `alerts.yml` schedule is opt-in via `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; scheduled runs execute the AI-free `quant_worker.py`, not the visual analyst. Manual visual runs require explicit confirmation.
- GitHub run history at this head showed only push and PR CI; no manual visual dispatch or scheduled paper run. No real chart bundle, vision response, selected real paper signal, or webhook delivery was verified. Last documented OpenAI blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested. No workflow was dispatched.

## Discord and outcome lifecycle

- Shared `discord._post()` rejects messages over 1,900 characters instead of truncating; messages within the limit are sent unchanged.
- Visual alerts contain setup family, entry zone/price, stop, target, validated R:R, trigger timeframe/condition, higher-timeframe context, rationale, target rationale, invalidation, evidence, conflicts and pre-entry cancellation conditions.
- Outcome tracker uses closed 5m candles, conservative SL-first handling when both TP and SL touch in one candle, gap-aware exits, and separate TP/SL/TIME updates. Missing bars can leave a trade unresolved; no outcome should be fabricated.
- Cross-run position persistence still uses GitHub Actions cache, which may be evicted. Outcome P&L is gross before fees, spread, slippage and funding.
- Existing shared Discord boundary regression tests passed in prior exact-head push CI: oversized messages are refused without webhook call; 1,900-character messages are delivered unchanged.

## Quant Discovery

- `quant_supervisor.APPROVED_STRATEGIES` remains empty. No candidate is eligible for production alerts.
- EXP-001: all 30 baseline OOS combinations and 270 stop/target variants were negative at 10 bps round-trip plus 1 bp/8h adverse carry stress. Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, seven consecutive losses, 25.76 trades/month.
- OI expansion remains rejected: BTC negative; ETH's small positive 10 bps OOS result fails train/validation consistency and turns negative at 20 bps; XAUT has only 14 OOS trades and turns negative at higher cost.
- OHLCV archive: 926,209 candles across 18 datasets. Derivatives archive: 758,119 candles across nine BTC/ETH/XAUT series. XAUT begins 2026-04-17 (~6.6 months).
- Funding candle units, sign and settlement-event attribution remain unresolved. Do not treat funding candle closes as realized cashflow. Historical executable spread/depth/market impact are unavailable; costs are explicit stress assumptions, not measured fills.
- Existing research reports `EXP001_INITIAL_SCREEN.md`, `OI_EXPANSION_SCREEN.md`, and `DERIVATIVES_ARCHIVE_AUDIT_2026-11-06.md` document rejection rationale and reproducible methodology. Do not re-run identical experiments without new validated data or a pre-registered hypothesis.

## Derivatives archive preservation

- GitHub Actions artifact `13383865992`, source run [41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516), was previously downloaded and preserved outside Actions retention.
- This runtime re-verified the mounted ZIP at `/mnt/data/salty-quant-derivatives-archive-13383865992.zip`: **16,854,903 bytes**, 12 files, SHA-256 `f16d0bc18eddcce7637c9643d9176590c8bb55fe9de6be1da9c717bdf7949a27`.
- Durable Library backup recorded at `/Salty Quant Research/salty-quant-derivatives-archive-13383865992.zip`.
- Original GitHub artifact expires **2026-11-19 02:37:57 UTC**. The verified Library copy is the preservation source; verify its hash again if rematerialized for analysis.

## Governance, blockers and precise next steps

- Branch protection and required-check status could not be verified: branch-protection endpoints returned HTTP 403 (resource not accessible by integration); repository rulesets returned HTTP 403 (plan restriction). Do not claim checks are enforced or disabled. Owner should inspect repository Settings and configure required CI checks if eligible.
- Restore/confirm OpenAI project quota through owner controls. Do not change secrets from this workflow.
- After quota is restored, the human owner must explicitly confirm one paper-only visual cycle through GitHub Actions manual dispatch (`task=visual-desk-run`, `confirm_visual_paper=true`). Inspect the actual chart artifacts, image hashes/watermarks, model candidate comparison, validator result and real Discord delivery. Do not dispatch without that confirmation.
- Improve durable position persistence beyond evictable Actions cache before relying on long-running lifecycle continuity.
- Verify funding interval/units/sign and settlement timestamps against contract metadata, WebSocket `fi`/`nfr` and an independently observed realized funding event before funding-adjusted backtesting.
- Preserve the visual-first decision boundary; keep quant candidates research-only; do not weaken thresholds or promote an unvalidated edge.

## Safety

Only `ai-quant-rebuild` may be changed. No main changes, PR merge, deployment, secret modification, manual workflow dispatch, schedule activation, live trading, exchange orders or risk-threshold reductions were performed in this supervision pass.
