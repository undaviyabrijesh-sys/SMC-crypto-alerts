# Salty Quant Supervisor Handoff — 2026-11-06 21:53 IST

## Exact repository checkpoint (before this handoff commit)

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Branch HEAD: `5359207cd5187880f196ed47e30d947d265097e7` — **Record verified derivatives archive and funding audit** (2026-11-06 16:02:28 UTC).
- Base `main`: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- GitHub compare: **429 ahead, 0 behind**; merge base equals main.
- PR #1: open, draft, mergeable, unmerged; 429 commits, 84 changed files; no submitted reviews or inline review threads.
- Branch API reports `protected: false`. No classic branch protection is active; ruleset enforcement was not verified.
- No code fix was warranted in this pass. The latest source commit is a research/data audit, not a trading-rule change.

## Exact-head CI evidence

Both workflows completed successfully on `5359207`:

- Push CI [42248630164](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42248630164): completed / success.
- PR CI [42248639233](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42248639233): completed / success.
- Each run's `test` job passed all 21 substantive steps: dependency install, compile, offline visual pipeline, visual-first contracts and mocked paper cycle, manual workflow contract, agent contract tests, DNS watcher tests, quant replay/supervisor, daily reports, feedback, secret-format checks, derivatives parsers/archive, Quant Discovery unit tests, live Delta OHLCV, derivatives-history probes and historical BTC pilot.
- Both run artifact lists were empty. These CI runs do not execute a real visual AI cycle.
- Combined commit status endpoint returned no separate status records; Actions run conclusions above are the CI evidence.

## Latest CI feed snapshot (historical, not live quotes)

PR CI probe at 2026-11-06 16:03 UTC (21:33 IST):

- All **18/18** BTCUSD / ETHUSD / XAUTUSD checks passed across 5m, 15m, 1h, 4h, 1d and 1w.
- Latest closed 5m prices: BTC **75,833.00**, ETH **2,229.70**, XAUT **4,044.85**.
- Closed candle counts: 1,151 (5m), 1,343 (15m), 1,079 (1h), 719 (4h); daily BTC/ETH 364, XAUT 203; weekly BTC/ETH 149/143, XAUT 29.
- Funding: BTC 65 hourly candles, ETH 65, XAUT 69. Mark prices: 864 five-minute candles per instrument. OI: 72 hourly candles per instrument.
- BTC 5m historical pilot: 1,051 candles, 100% coverage, zero gaps.
- XAUT weekly history remains short at 29 candles. Feed snapshot is about 20 minutes before this checkpoint, not a current market quote.

## Visual-first pipeline and controls

- `visual_first_analyst.py` uses raw six-timeframe images (5m, 15m, 1h, 4h, 1d, 1w), compares independent evidence-supported families and selects at most one candidate or `NO_TRADE`.
- Current prompt explicitly says **no mandatory DNS anchor**; SMC, supply-demand, liquidity, S/R, trend/pullback, momentum, breakout/retest, volatility expansion and mean reversion are independent alternatives. Coded DNS/zone/sweep logic is not a decision-maker.
- `visual_worker.py` validates chart watermarks, candidate identity, market entry, entry-zone deviation, stop/target geometry, reported R:R, ATR distance, confidence/quality, multi-timeframe evidence, cancellation conditions, open positions and opposing actionable candidates. It never substitutes a different model candidate.
- Gates remain unchanged: confidence >=75; quality >=75; R:R >=2.0; stop 0.35–2.5 trigger-timeframe ATR; entry-zone deviation <=0.35%; at least two distinct evidence timeframes including trigger; one open/pending paper position per symbol; opposing actionable candidate must be at least 8 quality points weaker or fail closed.
- `.github/workflows/tools.yml` manual visual lane requires `task=visual-desk-run` and `confirm_visual_paper=true`, then runs `ENABLE_VISUAL_PAPER=true python visual_worker.py`.
- `.github/workflows/alerts.yml` has a five-minute cron but is gated by `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; when enabled, scheduled runs route to AI-free `quant_worker.py`, while manual `lane=visual` dispatch routes to `visual_worker.py`. No schedule was enabled.
- GitHub Actions query for branch `ai-quant-rebuild` returned **0 workflow_dispatch runs** and **0 schedule runs**. No real visual dispatch, raw chart bundle, manifest artifact, real OpenAI vision response, selected real paper candidate or Discord webhook delivery was verified.
- Last recorded real OpenAI blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested.
- Visual Discord alert includes setup family, entry zone, entry, stop, target, R:R, trigger, context, rationale, target rationale, invalidation, evidence/conflicts and cancellation conditions. It refuses messages >1,900 chars rather than truncating.
- Lifecycle tracks closed 5m bars, resolves same-candle ambiguity SL-first, refuses to infer exits across missing bars, requires a contiguous window for TIME exit, and sends separate TP/SL/TIME updates. Retry TTL fix remains covered by `test_visual_alert_retry_preserves_original_analysis_expiry`.
- State writes are atomic, but Actions cache can be evicted; durable cross-run position persistence is not guaranteed.

## Quant Discovery and archive audit

- `quant_supervisor.APPROVED_STRATEGIES` remains empty. No research candidate is approved or promoted.
- EXP-001: all 30 baseline OOS asset/timeframe/strategy cells and all 270 stop/target variants were negative at the stated 10 bps round-trip plus 1 bp/8h adverse-carry stress. Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, 7 consecutive losses, 25.76 trades/month.
- OI expansion: BTC 45 OOS trades, -0.0313R; ETH 67 trades, +0.0493R at 10 bps but negative in train/validation and at 20 bps; XAUT 14 trades, +0.2863R at 10 bps but weak sample and negative at 20 bps. Reject all.
- New latest commit `5359207` adds `quant_discovery/DERIVATIVES_ARCHIVE_AUDIT_2026-11-06.md`. It independently verified the derivatives ZIP from run [41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516), artifact ID `13383865992`: 758,119 candles across nine series, all CSV hashes/row counts match manifest; ZIP SHA-256 `f16d0bc18eddcce7637c9643d9176590c8bb55fe9de6be1da9c717bdf7949a27`.
- Artifact remains available (`expired=false`), 16,854,903 bytes, expiry **2026-11-19 02:37:57 UTC**. XAUT starts 2026-04-17 (about 6.6 months); BTC/ETH funding and BTC OI contain gaps.
- Funding OHLC candle units/event-time semantics are unresolved. Raw close values must not be treated as realized cashflow, summed as hourly accruals or scaled until validated against contract metadata, funding interval (`fi`), next funding timestamp (`nfr`) and a realized funding record. Existing adverse-carry assumption remains a stress scenario, not measured funding. Historical spread/depth/executable impact also unavailable; unknown costs must not be zeroed.
- Mark-price history can support valuation experiments but is not an executable fill. No new strategy backtest was run in this pass because funding semantics are unresolved and the latest archive commit is a schema/integrity audit, not a new validated signal hypothesis.

## Default-branch legacy workflow

- Last observed scheduled main run remains [42241071005](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42241071005), created 2026-11-06 15:13:46 UTC (20:43:46 IST), successful on main SHA `e93ee289`.
- Its job executed `python main.py` with legacy WATCH/TRIGGER webhook variables present (values masked). This proves script execution, not Discord delivery.
- `main/.github/workflows/alerts.yml` retains the ten-minute legacy schedule and coded DNS/score path. Main was not modified. Owner authorization is required for pause/cutover.

## Exact next steps

1. Keep `main` untouched and PR #1 draft/unmerged.
2. Restore usable OpenAI project quota through owner account controls; do not change secrets in this supervision run.
3. When explicitly confirmed, dispatch one paper-only visual cycle; inspect chart PNGs, manifest hashes/watermarks, model candidate comparison, validator decision and actual Discord delivery.
4. Download and preserve artifact `13383865992` before its 2026-11-19 02:37:57 UTC expiry; independently revalidate its archive manifest and hashes.
5. Confirm funding interval, units, sign and event-time attribution against contract metadata and an independently observed realized funding record before implementing funding P&L. Add unit/sign/negative-rate/missing-event/boundary tests, then rerun chronological train/validation/OOS and walk-forward screens with explicit costs.
6. Keep all research-only candidates out of execution alerts. Do not promote without adequate OOS and robustness evidence.
7. Improve position persistence beyond evictable Actions cache; review required CI checks/branch rules with owner-level access.
8. Resolve legacy-main workflow migration only with owner authorization.

## Safety

No main changes, PR merge, deployment, secret modification, workflow dispatch, schedule activation, live trading, exchange orders or risk-threshold reductions were performed in this pass.
