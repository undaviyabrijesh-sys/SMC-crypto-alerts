# Salty Quant Supervisor Handoff — 2026-11-06 18:54 IST

## Exact repository state

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Current branch head before this handoff: `c313066752d51c61c8efc99f1bdeca4209b4e705`.
- PR #1: open, draft, unmerged; head `c313066752d51c61c8efc99f1bdeca4209b4e705`, base `main`; 426 commits ahead / 0 behind; 81 changed files.
- Main remains `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- No submitted PR reviews or inline review threads.
- Current branch-protection endpoint returned HTTP 403 (resource not accessible by this integration); protection/required-check state could not be independently re-verified in this pass. Do not change settings without owner authorization.

## Low-risk bug fixed in this pass

- Commit [329f498](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/329f498157e422b22785028b23e3a076ff865019): `visual_worker._retry_pending_visual_alerts()` previously replaced `analysis_time` with the retry time on every failed Discord delivery. This reset the 10-minute expiry window on every cycle, so a pending alert could remain retryable indefinitely. The retry now preserves the original analysis timestamp.
- Commit [c313066](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/c313066752d51c61c8efc99f1bdeca4209b4e705): added `test_visual_alert_retry_preserves_original_analysis_expiry`. It simulates a failed retry at age 9 minutes, verifies the original timestamp is retained, then verifies the alert is dropped at age 11 minutes.
- No entry, stop, target, confidence, quality, strategy, or risk threshold was changed.

## Exact-head CI

Both workflows passed on current head `c313066`:

- Push CI [42225078026](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42225078026), completed successfully.
- PR CI [42225087995](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42225087995), completed successfully.
- PR job steps passed: compilation; offline visual pipeline; independent visual-first contracts and mocked paper cycle; manual visual workflow contract; agent/DNS tests; quant replay and supervisor; reporting/feedback; secret-format checks; derivatives parsing/archive; Quant Discovery tests; live Delta OHLCV; funding/mark/OI probes; historical archive pilot.
- CI log explicitly passed `test_visual_alert_retry_preserves_original_analysis_expiry`.
- Both current-head CI artifact listings were empty, as these test workflows do not run the real visual worker.
- Previous code head `4ca2407` also had successful push CI [42219231505](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42219231505) and PR CI [42219237595](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42219237595).

## Latest feed evidence (CI-time, not current quotes)

PR CI live probe at 2026-11-06 13:23:51 UTC (18:53:51 IST):

- 18/18 closed-candle/freshness checks passed for BTCUSD, ETHUSD and XAUTUSD across 5m, 15m, 1h, 4h, 1d and 1w.
- 5m close snapshots: BTC 75,925.00; ETH 2,240.55; XAUT 4,050.66. These are CI-time values, not current quotes.
- Funding history: 70 hourly candles per instrument.
- Mark-price history: 864 five-minute candles per instrument.
- Open-interest history: 72 hourly candles per instrument.
- BTC 5m historical bootstrap pilot: 1,051 candles, 100% coverage, zero gaps; SHA-256 prefix `7e10bc8a2e78`.
- XAUT weekly history remains only 29 candles.

## Visual-first pipeline / manual workflow

- Inspected `.github/workflows/tools.yml`, `.github/workflows/alerts.yml`, `visual_worker.py`, `visual_first_analyst.py`, `test_visual_workflow_contract.py`, `main.py`, `trade_lifecycle.py`, `state.py`, and `discord.py`.
- Manual `visual-desk-run` requires `confirm_visual_paper=true` and invokes `ENABLE_VISUAL_PAPER=true python visual_worker.py`; the prior route-to-`main.py` bug is fixed.
- The model receives raw six-timeframe charts (5m, 15m, 1h, 4h, 1d, 1w), compares independent evidence-supported setup families, and selects at most one candidate or `NO_TRADE`. DNS/zone code does not decide or rank the visual setup.
- Chart artifacts persist raw images plus SHA-256 hashes and candle watermarks; the manual visual workflow uploads them with 14-day retention.
- Actions API query found zero `workflow_dispatch` runs on `ai-quant-rebuild`; no chart PNG/manifest artifact exists from a real visual cycle. No live vision request, selected real paper candidate, or actual Discord webhook delivery is verified.
- Last recorded real OpenAI blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; it was not re-tested. Do not dispatch without explicit user confirmation.

## Risk, alerts and lifecycle

- Visual gates unchanged: confidence >=75, quality >=75, minimum R:R >=2.0, stop 0.35–2.5 trigger-timeframe ATR, entry deviation <=0.35%, at least two distinct evidence timeframes including trigger, fresh watermarks, MARKET entry only, one open/pending paper position per symbol, opposing candidate tie margin 8 points; fail closed rather than substitute another candidate.
- Visual Discord alert includes setup family, entry zone, entry, stop, target, R:R, trigger, context, rationale, target rationale, invalidation, evidence/conflicts and cancellation. Over-1,900-character visual messages are refused rather than truncated; visual lane emits no WATCH/status messages.
- Lifecycle uses closed 5m bars, SL-first same-candle ambiguity, no inferred exit across gaps, contiguous-window TIME confirmation, and separate TP/SL/TIME updates. Failed outcome delivery is queued for retry.
- State writes are atomic, but cross-run GitHub Actions cache can be evicted; there is no durable database guarantee.
- A successful workflow run is not proof that a Discord webhook message was delivered.

## Quant Discovery

- `quant_supervisor.APPROVED_STRATEGIES` remains empty. No research candidate is promoted.
- EXP-001: all 30 baseline OOS asset/timeframe/strategy cells and all 270 tested stop/target variants were negative at 10 bps round-trip plus 1 bp/8h adverse carry stress. Least-negative BTC 1h mean reversion: 176 OOS trades, 39.77% win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, 7 consecutive losses, 25.76 trades/month. It turns positive only at 5 bps and is negative at the 10 bps baseline.
- ETH 15m volatility expansion baseline: 214 OOS trades, 37.85% win rate, -0.0785R expectancy, PF 0.894, -43.408R max drawdown, 9 consecutive losses, 32.48 trades/month.
- Post-hoc ETH 15m volatility-expansion / 1h-downtrend slice: +0.0946R OOS over 113 trades, PF 1.140, -25.603R max drawdown, 7 consecutive losses; train expectancy -0.0052R (349 trades), validation +0.1223R (153), OOS +0.0946R (113). This regime was selected post hoc and turns -0.1111R at 20 bps costs; hypothesis only, not an edge.
- OI expansion: BTC 45 OOS trades, 42.22% wins, -0.0313R expectancy, PF 0.9337, -7.8709R max DD, 6 loss streak, 6.59 trades/30d; 20 bps expectancy -0.1365R. ETH 67 trades, 43.28% wins, +0.0493R at 10 bps, PF 1.0896, -10.8919R max DD, 5 loss streak, 10.04 trades/30d, but 20 bps expectancy -0.0640R and train/validation are negative. XAUT 14 trades, 71.43% wins, +0.2863R at 10 bps, PF 1.7499, -3.7874R max DD, 2 loss streak, 10.43 trades/30d, but train/validation are negative and 20 bps expectancy -0.0305R. Reject all.
- Historical spread/depth, executable market impact and funding settlement attribution remain incomplete. No edge claim.

## Legacy main workflow

- Main `.github/workflows/alerts.yml` retains the legacy ten-minute schedule and runs `python main.py` with old WATCH/TRIGGER configuration.
- Latest observed scheduled main run [42216567670](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42216567670) completed on main SHA `e93ee289` at 2026-11-06 12:17:44 UTC (17:47:44 IST). Recent returned schedule history shows irregular gaps; do not assume the ten-minute cadence is being met. The job log proves `python main.py` ran, not Discord delivery.
- Do not modify or disable main or cut over without owner authorization.

## Next steps

1. Restore usable OpenAI API quota without changing secrets in this supervision workflow.
2. When explicitly authorized, manually dispatch one visual-paper cycle with `task=visual-desk-run` and `confirm_visual_paper=true`; inspect raw images/manifest, model comparison, validation and real Discord delivery.
3. Track each emitted paper signal to a confirmed TP, SL or TIME update.
4. Improve durable position persistence beyond evictable Actions cache.
5. Re-check branch protection/required checks when the integration can access that endpoint.
6. Resolve legacy-main workflow cutover only with owner authorization; continue chronological OOS/walk-forward research without promoting weak candidates.

## Safety

No main changes, PR merge, deployment, secret changes, workflow dispatch, schedule activation, live trading, exchange orders or risk-threshold reductions were performed in this pass.
