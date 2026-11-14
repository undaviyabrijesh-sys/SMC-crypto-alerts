# Salty Quant Supervisor Handoff — 2026-11-06 13:20 IST

## Exact repository state at handoff preparation

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Verified code head before this handoff file: `b8261a4b80896247dc4a26c446b493679e8f4157`.
- PR #1: open, draft, unmerged; head `b8261a4`, base `main`; 415 commits, 76 changed files.
- `main` remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`; compare is 415 ahead / 0 behind.
- PR has no submitted reviews or review threads at this checkpoint.
- GitHub branch metadata reports `ai-quant-rebuild` is not protected. CI ran successfully, but branch-protection required checks are not configured on this branch.
- This handoff is being added as a follow-up commit. On resume, fetch the live branch head and PR again; do not assume the code head above is still the branch tip.

## Changes made in this supervision pass

Two small commits on `ai-quant-rebuild`:

1. `583acab1676310502d36e79d1252f69b190a4937` — persist raw visual chart evidence for audit.
   - Writes each generated six-timeframe PNG under `visual_artifacts/<cycle_id>/<symbol>.png`.
   - Writes an atomic `manifest.json` with cycle ID, UTC creation time, SHA-256 per image and exact six-timeframe closed-candle watermarks.
   - Verifies the image hash, symbol and complete watermark set; rejects invalid cycle IDs.
   - Persistence failure is fail-closed: no new signal is created.
   - Adds a 14-day GitHub Actions artifact upload to the explicit paper workflow and ignores the local artifact directory in Git.
2. `b8261a4b80896247dc4a26c446b493679e8f4157` — keep the local artifact path out of the model prompt metadata while retaining it in the audit decision log.

The existing mocked end-to-end visual-paper test now verifies the saved image bytes, manifest cycle ID, SHA-256 and six timeframe watermarks.

## Exact-head CI

Both workflows passed on code head `b8261a4`:

- Push CI [42183330488](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42183330488): success.
- PR CI [42183334845](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42183334845): success.

Both ran compilation, visual pipeline tests and mocked paper cycle, agent contracts, DNS watcher, quant replay/supervisor, daily report, feedback, secret-format, derivatives parser/archive, Quant Discovery, live public feed, derivatives history and historical bootstrap. Quant Discovery unit tests: 12 passed.

The CI run artifact list is empty because CI does not run the visual worker. The new chart artifact is produced only by an explicitly confirmed visual-paper workflow run.

## Fresh feed evidence — push CI at 2026-11-06 07:49:24 UTC (13:19:24 IST)

- 18/18 closed-candle and freshness checks passed: BTCUSD, ETHUSD and XAUTUSD × 5m/15m/1h/4h/1d/1w.
- 5m close snapshots: BTC 75,678.50; ETH 2,230.70; XAUT 4,038.21. These are CI-time snapshots, not current quotes.
- Derivatives history: for each of BTC/ETH/XAUT, 72 hourly funding candles, 864 five-minute mark candles and 72 hourly OI candles were available. Availability does not validate funding settlement attribution or executable costs.
- BTC 5m historical bootstrap pilot: 1,051 candles, 100% coverage, zero gaps; SHA-256 prefix `4df417f0cca0`.
- XAUT weekly history remains short at 29 candles (daily history 203 candles).

## Visual-first pipeline and execution gates

- The analyst inspects raw six-panel images (1w, 1d, 4h, 1h, 15m, 5m) and compares independent evidence-supported SMC/structure, supply-demand, liquidity sweep/reclaim, support/resistance, trend pullback, momentum, breakout/retest, volatility expansion and mean-reversion candidates.
- The model selects at most one immediately actionable candidate or `NO_TRADE`. No coded DNS/zone/market-structure engine selects, ranks or substitutes a setup.
- Mechanical gates remain unchanged: confidence >=75, quality >=75, R:R >=2.0, stop 0.35–2.5 trigger-timeframe ATR, entry-zone deviation <=0.35%, at least two distinct evidence timeframes including trigger, at least two distinct alignment references, exact fresh chart watermarks, MARKET entry only, no existing open/pending position per symbol, and fail-closed handling of similarly strong opposing candidates (8-point quality margin).
- Visual Discord alert is execution-focused and includes setup family, entry zone, entry, stop, target, R:R, trigger, context, rationale, target rationale, invalidation, evidence/conflicts and cancellation conditions. It refuses a message over 1,900 characters; no WATCH/status message is emitted by the visual lane.
- Lifecycle uses contiguous closed 5m candles; same-candle TP/SL ambiguity resolves SL-first; gaps prevent fabricated outcomes; TP/SL/TIME are separate outcome updates. P&L in outcome messages is gross before fees, spread, slippage and funding.
- Local state writes are atomic, but cross-run GitHub Actions cache remains evictable; no durable database guarantee. The new chart artifact retention is 14 days, not permanent storage.

## Real image / AI / Discord status

- No fresh visual-paper workflow dispatch was observed on `ai-quant-rebuild`. The only recent workflow-dispatch records are older runs on `main` dated 2026-11-01.
- No actual chart-image bundle, real OpenAI vision response, selected live-paper setup or actual Discord webhook delivery was verified in this cycle.
- The latest CI artifact list was empty because no visual worker was run.
- Last recorded real OpenAI blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested or changed.
- PR branch `.github/workflows/alerts.yml` keeps scheduled execution opt-in through `vars.ENABLE_GITHUB_SCHEDULE == 'true'`; scheduled lane is AI-free Quant Discovery. A one-cycle visual-paper run requires manual dispatch with `lane=visual` and `confirm_visual_paper=true`. No dispatch or schedule activation was performed.
- On the next confirmed visual run, inspect the `salty-visual-charts-<run_id>` artifact even if the vision request fails; the raw images and manifest are now uploaded for 14 days.

## Legacy main workflow — still active

- Latest observed default-branch run: [42182778052](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42182778052), created 2026-11-06 07:43:47 UTC (13:13:47 IST), main SHA `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`, completed success.
- Job steps confirm `python main.py`.
- Main `.github/workflows/alerts.yml` remains scheduled every 10 minutes and supplies legacy `DISCORD_WEBHOOK`, `DISCORD_WATCH_WEBHOOK` and `DISCORD_TRIGGER_WEBHOOK` variables.
- This is the old coded DNS/score WATCH/TRIGGER lane, separate from the visual-first PR. A successful workflow run does not prove a Discord message was delivered. Owner decision is required before any cutover; do not modify or disable `main` without explicit authorization.

## Quant Discovery — research only

- EXP-001: all 30 OOS asset/timeframe/family cells were negative at the 10 bps round-trip plus adverse-carry stress; all 270 tested stop/target variants were negative. Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, seven consecutive losses.
- OI expansion: BTC negative. ETH's best +0.0493R over 67 OOS trades fails train/validation consistency and turns negative at 20 bps. XAUT's +0.2863R uses only 14 OOS trades and fails consistency/cost stress.
- `APPROVED_STRATEGIES` remains empty. No research candidate is eligible for production execution alerts.
- Funding event/unit attribution, executable spread/slippage/depth and longer XAUT history remain blockers. Do not treat the cost assumptions as measured execution.

## Work and safety

- No research candidate, live signal or confirmed TP/SL/TIME outcome was generated.
- No actual Discord webhook delivery is claimed.
- No `main` changes, PR merge, deployment, secret change, workflow dispatch, schedule activation, live trading, exchange order or threshold reduction.
- No failing tests remained on verified code head `b8261a4`.

## Precise next steps

1. Re-check live branch head, PR #1, exact-head CI and latest main workflow run.
2. Restore usable OpenAI API quota. Then have the owner explicitly dispatch one visual-paper cycle on `ai-quant-rebuild` with `lane=visual` and `confirm_visual_paper=true`.
3. Inspect the uploaded raw BTC/ETH/XAUT six-panel chart artifacts and manifests; verify actual model response, candidate comparison, risk validation, decision JSONL and actual Discord delivery. If no candidate passes, no execution alert.
4. Verify each emitted signal through the separate confirmed TP/SL/TIME lifecycle update. Do not infer outcomes through missing bars.
5. Decide how to retire or cut over the legacy main WATCH/TRIGGER workflow before any migration; no authorization to change main exists.
6. Improve durable position state beyond evictable Actions cache without storing secrets; continue chronological OOS/walk-forward research and keep all unvalidated candidates out of production alerts.

A fresh chat in the Salty trades project must re-check live GitHub state and artifacts before acting.