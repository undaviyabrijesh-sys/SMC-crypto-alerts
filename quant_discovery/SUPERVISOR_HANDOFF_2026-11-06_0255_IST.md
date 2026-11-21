# Salty Quant Supervisor Handoff — 2026-11-06 02:55 IST

## Exact GitHub checkpoint

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts` (private).
- Working branch: `ai-quant-rebuild`.
- Current code/test head: [`f9ef735`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/f9ef735a6b3425c6d3716bd53147848b30992331).
- PR [#1](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/pull/1): open, draft, unmerged; base `main`; mergeable at checkpoint. Compare: 357 ahead / 0 behind. Base/main SHA: `e93ee289b36d47ca774e9a285fc76a2f4cbb5795`.
- Do not modify `main`, merge PR, deploy, change secrets, activate schedules, enable live trading or place orders.

## Code fix and exact-head CI

- Found that `quant_supervisor._finite_positive()` called `float(value)` without rejecting booleans. Python treats `True`/ `False` as integers, so malformed boolean entry/stop/target/ATR/current-price inputs could be coerced into numeric values.
- Fixed by rejecting booleans before numeric conversion; no threshold or risk gate was weakened.
- Added regression test `test_boolean_price_fields_and_current_price_are_rejected` covering entry, stop, target, ATR and current price.
- Commit: [`f9ef735`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/f9ef735a6b3425c6d3716bd53147848b30992331).
- Exact-head push CI [42112660673](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42112660673) — success.
- Exact-head PR CI [42112672680](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42112672680) — success.
- PR log explicitly shows the new boolean regression passing; all 19 quant-engine tests passed. Visual, agent, DNS, replay, reports, feedback, secret-format, derivatives-history, archive, Quant Discovery and live data-feed steps passed. One-time derivatives archive workflow was skipped by its configured guard, not failed.

## Latest feed evidence (CI snapshot, not current quotes)

PR CI live Delta probe at 2026-11-05 21:27:09 UTC:
- 18/18 BTCUSD, ETHUSD, XAUTUSD × 5m/15m/1h/4h/1d/1w closed-candle freshness checks passed.
- Snapshot 5m closes: BTC 75,853.0; ETH 2,230.25; XAUT 4,081.95. These are historical CI values, not current prices.
- Three-day derivatives probe: 70 hourly funding observations per contract, 864 five-minute mark candles per contract, 72 hourly OI candles per contract.
- BTC 5m historical archive pilot: 1,051 candles, 100% coverage and zero gaps for that pilot window only.
- Funding availability does not establish correct settlement-event attribution/units. Historical bid/ask spread, depth and market impact remain unavailable.

## Visual chart-to-AI architecture — still not compliant

- `worker.py` defaults to `WORKER_MODE=quant`, which calls AI-free `quant_worker.py`.
- Branch `.github/workflows/alerts.yml` directly invokes `quant_worker.py`; scheduled job is opt-in behind `ENABLE_GITHUB_SCHEDULE`.
- `WORKER_MODE=dns` calls `dns_worker.py`: AI-authored maps refresh infrequently, then a coded local sweep/reclaim detector creates candidates. Optional Bull/Bear/Chief review is disabled by default and only runs after that detector.
- `ai_analyst.py` inspects six-timeframe chart images, but prompt/schema/validator require a primary directional DNS band; trend, momentum, breakout, volatility and mean reversion are only DNS confirmations/refinements. Existing test explicitly asserts demand/supply first.
- Thus neither active branch lane runs independent visual candidate comparison on every closed-candle analysis cycle. No chart-review artifacts or live model decision were produced by CI; PR workflow artifact list was empty.
- Do not patch only the prompt and do not restore `zones.py` / `score.py` as decision-makers. Redesign a versioned schema, prompt, validator and worker together: vision compares independent setup families and chooses one candidate or `NO_TRADE`, then unchanged mechanical risk gates validate the selected plan.
- Last known real Responses API blocker remains HTTP 429 `insufficient_quota / credit_balance_exhausted`; this run did not test API quota or alter credentials.

## Risk, lifecycle and Discord

- Quant mechanical gates remain: quality >=75/100, minimum 2R, stop distance 0.35–2.5 ATR, entry exactly latest closed 5m price, stale-candle rejection, opposing directions within 8 quality points => NO_TRADE, one open paper position per symbol.
- `APPROVED_STRATEGIES` remains empty; all deterministic strategies are research-only and cannot emit execution alerts.
- DNS gates remain: confidence >=75, minimum 2R, directional visual zone quality >=3/5, entry deviation <=0.35%, one open position per symbol; malformed/API/review failures fail closed.
- Quant `trade_lifecycle.py` uses closed 5m bars, stop-first same-bar ambiguity, missing-bar protection and full 48h horizon before TIME. A parallel lifecycle remains in `main.py`; parity audit is outstanding.
- Discord execution format includes setup, entry, stop, target, R:R, context, rationale and invalidation. TP/SL/TIME updates are separate. Gross paper P&L is labelled as before fees/spread/slippage/funding. Actual webhook delivery remains unverified.
- Branch quant lane does not emit WATCH messages; legacy `main` workflow still can.

## Main-branch legacy workflow — unchanged

- `main` workflow `.github/workflows/alerts.yml` still runs every 10 minutes and invokes `python main.py`, with masked Discord webhook environment variables.
- Latest observed scheduled main run [42108530583](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42108530583), 2026-11-05 20:59:59 UTC, completed successfully. Job steps confirm legacy `python main.py` ran; no log evidence proves a Discord message was delivered.
- No main change was made. Owner authorization is required before pausing or replacing this workflow.

## Quant Discovery decision

- Prior archive: 926,209 candles across 18 asset/timeframe datasets; BTC/ETH multi-year, XAUT starts 2026-04-17 (~6.6 months), not a three-year gold history.
- Six setup families screened with chronological train/validation/OOS, purge/embargo, walk-forward and explicit fee/slippage/spread assumptions. No candidate passed adequate OOS and robustness criteria.
- Initial screen: all 18 15m asset/hypothesis OOS cells negative under stressed costs; only 8/180 folds had positive expectancy and PF >1, only four with >=30 trades. BTC 1h volatility expansion had 11 OOS trades and negative validation; reject.
- OI/volatility screen also rejected; some baseline positives turned negative at 20 bps. Funding is not included in prior replay because event-time/units attribution is unresolved; historical spread/depth and impact are unavailable.
- Do not populate `APPROVED_STRATEGIES` until adequate OOS sample, walk-forward, parameter-neighbourhood and stressed-cost validation pass. Do not claim an edge.

## Precise next steps

1. Re-check branch, PR, and exact-head CI after this handoff commit.
2. Design a versioned visual analyst contract for independent setup families, candidate comparison, rationale, one winner or `NO_TRADE`.
3. Update schema and mechanical validation together; preserve all existing confidence/quality, R:R, freshness, stop-distance, entry and one-position controls.
4. Connect fresh six-timeframe chart analysis every closed-candle cycle to the paper worker only after offline tests and opt-in integration tests; persist raw/review images and structured decisions.
5. Resolve API quota before a real paper-only vision test; do not alter secrets or retry quota failures repeatedly.
6. Audit lifecycle parity and retry-safe outcomes.
7. Obtain owner authorization before changing the legacy scheduled workflow on `main`.
8. Continue independent Quant Discovery; no unvalidated candidate may reach execution alerts.

No credentials or secrets are stored in this handoff.
