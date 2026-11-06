# Salty Quant Supervisor Handoff — 2026-11-06 21:26 IST

## Exact repository state at checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts`
- Working branch: `ai-quant-rebuild`
- Branch HEAD before this documentation commit: `accc121d678405e55cda37873b12e78ae3d805bf`
- HEAD commit: `Save 18:54 IST supervisor handoff`, authored 2026-11-06 13:25:00 UTC.
- Base `main`: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`; compare result: 427 ahead, 0 behind.
- PR #1: open, draft, mergeable, unmerged; 427 commits, 82 changed files; no submitted reviews and no inline review threads.
- Branch API reports `protected: false`. The branch-protection endpoint itself returned 403 for this integration; do not assume required checks are enforced.
- No source-code change or failing test was identified in this pass. This checkpoint is documentation only.

## CI evidence

Exact-head `accc121d`:
- Push CI [42225320821](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42225320821): completed successfully.
- PR CI [42225332964](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42225332964): completed successfully.
- PR job [127917255053](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42225332964/job/127917255053): all 21 substantive steps passed, including compilation, offline visual tests, mocked visual cycle, manual visual workflow contract, lifecycle/risk, Discord formatting, quant tests, live OHLCV, derivatives probes and historical BTC pilot.
- The PR CI run uploaded no artifacts; it was not a real visual-analysis run.

## Latest feed snapshot from CI (not current quotes)

PR CI feed probe at 2026-11-06 13:25:42 UTC (18:55:42 IST):
- All 18 BTCUSD / ETHUSD / XAUTUSD timeframe checks passed across 5m, 15m, 1h, 4h, 1d and 1w.
- Latest 5m closes: BTC 75,918.50; ETH 2,239.25; XAUT 4,049.49.
- Candle counts: 1,151 on 5m, 1,343 on 15m, 1,079 on 1h, 719 on 4h; BTC/ETH daily 364, XAUT daily 203; BTC/ETH weekly 149/143, XAUT weekly 29.
- Funding: 70 hourly candles per instrument; mark prices: 864 five-minute candles per instrument; open interest: 72 hourly candles per instrument.
- BTC 5m historical pilot: 1,051 candles, 100% coverage, zero gaps.
- XAUT weekly history is short (29 candles). Treat it as limited context.
- This snapshot is from 18:55 IST, about 2.5 hours before this handoff; it is not a live market quote.

## Visual-first pipeline and risk

- `visual_first_analyst.py` receives raw six-timeframe images (5m, 15m, 1h, 4h, 1d, 1w), compares independent evidence-supported setup families, and returns one selected candidate or `NO_TRADE`.
- It explicitly prohibits a coded DNS/zone/market-structure detector from selecting or ranking the trade.
- `visual_worker.py` validates freshness, chart watermarks, entry geometry, candidate identity, ATR stop distance, R:R, confidence/quality and conflicting candidates before paper alert creation.
- Existing gates remain: confidence >=75, quality >=75, R:R >=2.0, stop 0.35–2.5 trigger-timeframe ATR, entry-zone deviation <=0.35%, at least two distinct evidence timeframes including trigger, MARKET entry only, one open/pending paper position per symbol, opposing-candidate quality margin 8 points; fail closed otherwise.
- Manual `.github/workflows/tools.yml` dispatch requires `task=visual-desk-run` and `confirm_visual_paper=true`, then runs `ENABLE_VISUAL_PAPER=true python visual_worker.py`.
- Branch `.github/workflows/alerts.yml` is schedule-gated by `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; scheduled branch runs currently route to `quant_worker.py`, while manual `lane=visual` routes to `visual_worker.py`. Do not enable the schedule or dispatch without the required owner confirmation and a usable vision API quota.
- No visual workflow dispatch, chart PNG/manifest artifact, real vision response, selected real paper candidate, or actual Discord webhook delivery was found/verified in this pass. Last recorded real OpenAI failure remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested.
- Discord visual messages include setup family, entry zone, entry, stop, target, R:R, trigger, context, rationale, target rationale, invalidation, evidence/conflicts and cancellation conditions. Messages above 1,900 characters are refused rather than truncated.
- Lifecycle uses closed 5m bars, SL-first same-candle ambiguity, no inferred exit across missing bars, contiguous-window TIME confirmation and separate TP/SL/TIME updates. Failed deliveries are queued for retry.
- State writes are atomic, but Actions cache can be evicted; cross-run position durability is not guaranteed.

## Quant Discovery

- `quant_supervisor.APPROVED_STRATEGIES` remains empty. No research candidate is approved or promoted.
- EXP-001: all 30 baseline OOS asset/timeframe/strategy cells and all 270 tested stop/target variants were negative at the baseline cost assumptions.
- Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, 7 consecutive losses, 25.76 trades/month.
- ETH post-hoc volatility-expansion/downtrend slice: +0.0946R over 113 OOS trades, PF 1.140, but selected post hoc and turns negative under 20 bps cost stress; hypothesis only.
- OI expansion: BTC 45 OOS trades, -0.0313R; ETH 67 trades, +0.0493R at 10 bps but negative at 20 bps and train/validation; XAUT 14 trades, +0.2863R at 10 bps but weak sample and negative at 20 bps. Reject all.
- Historical spread/depth, executable impact and funding settlement attribution remain incomplete. Unknown costs must not be treated as zero.
- Derivatives archive artifact: [run 41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516), artifact ID `13383865992`, 758,119 candles across nine datasets, previously hash-verified; documented expiry 2026-11-19 02:37:57 UTC. Download and store durably before expiry, then independently revalidate. Do not assume this artifact is a permanent repository file.
- An older append-only section in `QUANT_DISCOVERY.md` says a previous handoff had approved replacing the visual AI with a quant-only decision-maker. Treat that as historical context only; the current instruction is explicitly visual-first, with Quant Discovery isolated and research-only.

## Default-branch legacy workflow

- Latest observed scheduled main run: [42241071005](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42241071005), created 2026-11-06 15:13:46 UTC (20:43:46 IST), completed successfully on main SHA `e93ee289`.
- Job [127971189087](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42241071005/job/127971189087) executed `python main.py`; its environment showed configured `DISCORD_WEBHOOK`, `DISCORD_WATCH_WEBHOOK` and `DISCORD_TRIGGER_WEBHOOK` variables (values masked). No workflow artifacts were present. This proves the legacy script ran, not that a Discord message was delivered.
- `main/.github/workflows/alerts.yml` retains the ten-minute `advance-alerts` schedule and legacy WATCH/TRIGGER path. Main was not modified. Owner authorization is required before any pause/cutover.

## Exact next steps

1. Keep `main` untouched and PR #1 draft/unmerged.
2. Restore usable OpenAI project quota through the owner's normal account controls; do not change secrets in this supervision run.
3. When explicitly authorized, dispatch exactly one paper-only visual cycle with `task=visual-desk-run` and `confirm_visual_paper=true`; inspect raw chart images, manifest hashes/watermarks, model comparison, validator decisions and actual Discord delivery.
4. Continue independent chronological train/validation/OOS and walk-forward research. Keep every unvalidated candidate out of execution alerts.
5. Download/revalidate the derivatives archive before its documented expiry and place it in durable storage.
6. Improve position persistence beyond evictable Actions cache; review branch protection/required checks with repository-owner access.
7. Resolve legacy-main workflow migration only with owner authorization.

## Safety

No main changes, PR merge, deployment, secret modification, workflow dispatch, schedule activation, live trading, exchange orders or risk-threshold reductions were performed.
