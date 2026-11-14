# Salty Quant Supervisor Handoff — 2026-11-06 16:28 IST

## Exact repository state

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Code/test head before this handoff: `a6c802d675c3580990cd3493f01c380c7bd0c2c5`.
- PR #1: open, draft, unmerged; 422 commits ahead of main, 0 behind; head `a6c802d`, base `main`.
- Main remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- PR reviews and inline review threads: none found.
- Latest exact-head PR CI: [42206377202](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42206377202), run 719, completed successfully. The job's compile, visual pipeline, visual-first, new workflow-contract test, agent, DNS, quant, lifecycle, Discord, derivatives, archive and live feed steps all completed successfully.
- The connector exposes PR-triggered workflow runs; a separate push-run ID for this head was not surfaced. Combined commit-status endpoint returned no status entries, so do not infer push CI from that endpoint.

## Bug found and fixed — manual visual tools workflow was routed to the wrong worker

The manual `.github/workflows/tools.yml` task named `visual-desk-run` previously executed `python main.py`. The direct `main.py` entrypoint on this branch invokes `dns_worker.run()`, so the button labelled as a visual desk run actually launched the legacy coded DNS worker rather than the independent visual analyst.

Fixes committed only on `ai-quant-rebuild`:
- `1ec7955c9ed38c345fd31a9ee359c79e09816a62` — route `visual-desk-run` to `ENABLE_VISUAL_PAPER=true python visual_worker.py`; add explicit boolean `confirm_visual_paper` input defaulting to false; set the visual research/chart output paths; upload decision log and raw chart/manifest artifacts with 14-day retention.
- `98074a2547c5d759da6f04cc9b1fe1a26120d60d` — add `test_visual_workflow_contract.py` to assert confirmation, correct worker routing, output paths and artifact uploads.
- `a6c802d675c3580990cd3493f01c380c7bd0c2c5` — run the new contract test in `.github/workflows/ci.yml`.

The new test passed in PR CI run 42206377202. This corrects the manual tools shortcut; it does not dispatch the workflow or activate any schedule.

## Fresh data-feed evidence — PR CI at 2026-11-06 10:56:25 UTC (16:26:25 IST)

All 18/18 closed-candle and freshness checks passed for BTCUSD, ETHUSD and XAUTUSD across 5m, 15m, 1h, 4h, 1d and 1w.

Latest 5m closed-price snapshots:
- BTC: 76,136.00
- ETH: 2,238.75
- XAUT: 4,056.37

Other observations:
- Funding: BTC 67, ETH 67, XAUT 71 hourly candles.
- Mark price: 864 five-minute candles per instrument.
- Open interest: 72 hourly candles per instrument.
- BTC 5m historical bootstrap pilot: 1,051 candles, 100.0% coverage, zero gaps; SHA-256 prefix `ce347a4ea473`.
- XAUT weekly history remains 29 candles; long-horizon Gold inference remains weak.

These are CI-time observations, not current quotes. Derivatives series availability does not establish funding settlement attribution or executable spread/slippage.

## Visual-first pipeline and execution controls

- The independent analyst receives raw six-timeframe chart images: 1w, 1d, 4h, 1h, 15m and 5m.
- It compares evidence-supported candidates independently: SMC/market structure, visual supply-demand, liquidity sweeps/reclaims, support/resistance, trend pullback, momentum, breakout/retest, volatility expansion, range rejection/mean reversion and other justified behaviours.
- The model selects at most one immediately actionable candidate or `NO_TRADE`. No coded DNS/zone/market-structure engine chooses, ranks or substitutes a trade.
- Mechanical gates remain unchanged: confidence >=75; quality >=75; R:R >=2.0; stop 0.35–2.5 trigger-timeframe ATR; entry-zone deviation <=0.35%; at least two distinct evidence timeframes including trigger; fresh watermarks; MARKET entry only; one open/pending paper position per symbol; conflicting opposing actionable candidates fail closed under the existing 8-point quality margin.
- Visual Discord alerts are execution-focused and include setup, entry zone, entry, stop, target, R:R, trigger, context, rationale, target rationale, invalidation, evidence/conflicts and cancellation conditions. Messages above 1,900 characters are refused, not truncated. No visual WATCH/status messages.
- Outcome tracking uses closed 5m candles, SL-first same-candle ambiguity, unresolved status across missing bars, contiguous-window TIME confirmation, and separate TP/SL/TIME updates. Failed outcome delivery is queued for retry.
- Position/state files are atomically written, but GitHub Actions cache is evictable; there is no durable database guarantee.

## Real visual / AI / Discord status

- No manual `workflow_dispatch` visual-paper run was executed in this pass; no fresh chart images were available to inspect.
- The latest PR CI artifact list is empty because CI does not execute `visual_worker.py`; this is expected and is not evidence of a visual run.
- No real OpenAI vision response, actionable setup selection, or Discord webhook delivery was verified.
- Last recorded real OpenAI blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested.
- The corrected `tools.yml` manual `visual-desk-run` now requires `confirm_visual_paper=true` and calls the correct visual worker. The separate `alerts.yml` manual lane also requires `lane=visual` and `confirm_visual_paper=true`. No visual schedule was enabled or dispatched.

## Quant Discovery — research only

- `quant_supervisor.APPROVED_STRATEGIES = frozenset()`; no research candidate can enter deterministic execution alerts.
- EXP-001: all 30 baseline OOS asset/timeframe/family cells negative at the tested 10 bps round-trip plus adverse carry assumption; all 270 stop/target variants negative. Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, seven consecutive losses.
- OI/volatility expansion: BTC best row -0.0313R over 45 OOS trades; ETH best row +0.0493R over 67 trades but train/validation negative and 20 bps stress -0.0640R; XAUT +0.2863R over only 14 OOS trades, with negative train/validation and 20 bps stress -0.0305R. All rejected.
- Historical spread/depth, executable market impact and funding settlement attribution remain incomplete. No candidate is described as an edge or promoted.

## Legacy main workflow

- Main `.github/workflows/alerts.yml` was inspected and remains scheduled every 10 minutes, running `python main.py` with legacy WATCH/TRIGGER webhook configuration.
- The last observed run in the preceding handoff was [42189082666](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42189082666), successful on main SHA `e93ee289`. This pass did not have a repository-wide Actions-run listing endpoint, so do not call that the latest current run.
- Do not modify or disable main or perform cutover without owner authorization.

## Next steps

1. Re-check branch/PR head and CI after this handoff commit.
2. Restore usable OpenAI API quota.
3. Manually dispatch one confirmed visual-paper cycle using either `tools.yml` task `visual-desk-run` plus `confirm_visual_paper=true`, or `alerts.yml` lane `visual` plus `confirm_visual_paper=true`.
4. Inspect the resulting raw chart PNGs and manifest; verify hashes/watermarks, actual model candidate comparison, risk validation, and real Discord delivery.
5. Track every emitted paper signal until a confirmed TP, SL or TIME update.
6. Resolve legacy-main workflow cutover only with owner authorization.
7. Continue pre-registered chronological OOS/walk-forward research; do not promote unvalidated candidates.

## Safety

No main changes, PR merge, deployment, secret changes, schedule activation, workflow dispatch, live trading, exchange orders or risk-threshold reductions were performed in this supervision pass.
