# Quant Terminal build log

## 2026-11-19 — Read-only FastAPI adapter (Phase 2 foundation)

- Added quant_terminal/api/main.py with GET-only health, market, scanner, research, backtest-artifact, paper-position, paper-history and risk-summary endpoints.
- Reused the existing data.normalize, config.SYMBOLS and quant_supervisor.APPROVED_STRATEGIES; did not copy the strategy or backtest engines into the dashboard.
- Market responses read persisted OHLCV CSVs only. The API never fetches from an exchange and reports per-timeframe freshness.
- Paper endpoints parse state.json without calling state.load or writing defaults. Missing/unreadable state is unavailable, not an empty account.
- Backtest endpoint indexes persisted quant_discovery artifacts only; it does not execute or recalculate experiments.
- Security: loopback-only when QUANT_API_TOKEN is unset; constant-time Bearer-token comparison when configured; no CORS; response no-store; no mutating routes.
- Added offline tests for freshness, missing/stale data, JSONL/ledger/artifact reads, paper-state non-mutation, GET-only routes and optional token protection.
- No deployment, live order, alert or production-rule changes.

### Checks

- Local API unit tests: 13 passed using isolated fixture modules for the existing root imports.
- Local compileall for the new API package: passed.
- GitHub Actions API contract workflow #9 (run 44478652326) completed successfully: dependency install, API compile and all 13 unit/HTTP contract tests passed against the actual repository modules.
- The broader deterministic-quant CI run 44478652449 was still in progress at this log update; its later steps are not claimed as passed.
- Follow-up full deterministic-quant CI run #2174 (run 44478766743) completed successfully, including the repository's existing offline test suites, live Delta OHLCV check, funding/mark/OI probe and small historical-archive pilot. This passed after the API dependency and adapter changes.


## 2026-11-19 — Overview and Live Markets read-only integration (Phase 3 foundation)

- Added `quant_terminal/app/api/quant/[...path]/route.ts`, a same-origin Next.js server-side proxy with an explicit allowlist for the eight read-only API endpoints.
- Proxy defaults to loopback FastAPI at 127.0.0.1:8000. A non-loopback upstream requires a server-only token and HTTPS. Browser-supplied auth headers are not forwarded; redirects are rejected; only documented query parameters are accepted; requests time out after 10 seconds.
- Connected the Overview to persisted health, market, scanner, research-ledger, backtest-artifact, paper-position and risk snapshots. Data refreshes every 30 seconds.
- Connected the Live Markets page to the actual configured BTC, ETH and XAU/XAUT market records, including last persisted close, age, venue and per-timeframe freshness.
- Replaced static strategy examples and synthetic market rows with API-backed records. Paper equity remains unavailable because the source state does not persist account capital. The UI explicitly distinguishes a fresh persisted candle cache from a websocket/live executable quote.
- Added market freshness and snapshot provenance UI. Candlestick chart rendering remains pending; no synthetic chart data is generated.
- Added `.github/workflows/quant-terminal-frontend.yml` to install dependencies, run TypeScript type-checking and build the Next.js app on relevant branch changes.
- Updated frontend/API documentation with server-only environment configuration and proxy security constraints.
- No exchange, strategy, paper-lifecycle, alert, production or main-branch logic was changed. No deployment performed.

### Checks

- GitHub Actions frontend workflow was added and triggered by the branch commits. Type-check/build results must be read from the resulting run before claiming success.
- Existing API contract tests were not modified in this increment; prior 13/13 API contract pass remains the last verified API test result.


### Frontend integration verification — 2026-11-19

- GitHub Actions run 44513113410 completed successfully on commit 67a5f3e7daa0c789d82fff667195ab565d042257. Dependency installation, TypeScript type-check and production Next.js build all passed.
- A second full frontend verification run 44513405351 also completed successfully after the month-parameterized research builder change. A later superseded run was cancelled during the production build after its type-check had passed; the successful run remains the verification result.
- Overview and Live Markets use the same-origin proxy and actual API payloads. The proxy's server-only token is never referenced by client components.


### Final integration CI on 2026-11-19

- Latest branch commit at this update: `986cc027143abbc5c16f999d80dbe1a52dcbdeb8`.
- Frontend workflow [44513797683](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44513797683) completed successfully: npm dependency install, `npm run typecheck`, and `npm run build`.
- Read-only API workflow [44513797676](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44513797676) completed successfully: dependency install, API compile, and all 13 API contract tests.
- No frontend/API deployment was performed.

## 2026-11-19 — Scanner and Strategy Research read-only UI integration

- Connected the existing scanner and research API snapshots to dedicated navigation views; no new backend endpoints were added.
- AI Scanner now shows persisted per-symbol freshness, decision status/reason, candidate risk geometry, RR, rule-quality points, evidence timeframes, rationale/invalidation and recorded rejections. It is a view of the deterministic scanner log, not a new AI or signal-generation engine.
- Strategy Research now renders recent research-ledger sections. It explicitly does not infer validation status from headings or promote strategies.
- Added responsive scanner/candidate/research timeline styling in `app/globals.css`.
- Frontend push run [44552763666](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44552763666) and PR run [44552777079](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44552777079) passed dependency installation, TypeScript type-check and production Next.js build.
- Read-only API PR run [44552777259](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44552777259) passed. Full deterministic CI was still running at this update.
- No deployment, exchange credentials, live order routes, alert mutations or production changes.

## 2026-11-20 — Backtesting artifact inventory UI (Phase 4 foundation)

- Extended the frontend backtest snapshot contract to include the persisted artifact inventory already returned by `GET /api/v1/backtests`.
- Added a dedicated Backtesting view showing artifact count, source, file size, recorded symbol/strategy/trade metadata, metadata details and CSV column names when present.
- Every record is labelled `FILE ONLY`; the page explicitly states that artifact presence does not prove a completed/reproducible test, positive expectancy, validation or strategy promotion.
- The page does not launch or recompute backtests. The existing deterministic backtest engine and persisted artifacts remain the source of truth.
- No new API endpoint or engine was added; paper trading, account equity, and full normalized performance analytics remain pending.
- Added responsive styling for artifact cards and metadata.
- Frontend TypeScript/production-build verification is triggered by the branch changes; no result is claimed until the corresponding workflow is inspected.
- No deployment, live order routes, exchange credentials, alert mutations, production changes or main-branch changes.

### Backtesting UI verification — 2026-11-20

- Frontend workflow [44597784862](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44597784862) completed successfully after the Backtesting page changes: dependency installation, TypeScript type-check and production Next.js build all passed.
- Read-only API workflow [44597784912](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44597784912) completed successfully: API compile and all existing read-only API contract tests passed. No API code changed in this increment.
- Full deterministic repository CI [44597785323](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44597785323) was still in progress at this build-log update; no final conclusion is claimed here.
- ETH archive-replication PR self-test [44597784701](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44597784701) passed the deterministic parser/feature tests. The PR lane intentionally skipped historical downloads; the full archive run remains separate and unverified.
- No deployment, production mutation, exchange order, alert-send route or main-branch change.

## 2026-11-20 — Paper Trading, Portfolio and Trade History views

- Extended the frontend data contract with typed paper position, paper history and expanded risk-summary fields.
- The dashboard now reads GET /api/v1/paper/history in parallel with existing paper positions and risk endpoints.
- Paper Trading view displays persisted open simulated positions, entry/stop/target geometry, R:R, status, source and snapshot time. It is explicitly read-only.
- Portfolio view displays only fields already persisted by the paper risk endpoint: open positions/symbols, pending outcomes, retained gross-R sum and retained gross-R drawdown. Account equity, notional exposure and circuit-breaker state remain unavailable and are displayed as such.
- Trade History view displays the bounded recent sample from the existing lifecycle history endpoint, including entry/exit, status, exit time and stored gross R. Gross R is not represented as net account P&L.
- Added responsive horizontally scrollable paper position/history tables, portfolio symbol chips and a known-limitations panel.
- No backend endpoint, paper lifecycle, state file, execution route or exchange adapter was changed. No simulated trade was created or modified by the UI.
- The prior Backtesting-only frontend build passed in run 44597784862. The new Paper Trading/Portfolio/Trade History frontend changes are awaiting their own latest TypeScript and production-build verification; no pass is claimed until that run is inspected.
- No deployment, main-branch change, production-rule change, live alert or exchange order.

## 2026-11-20 — ETH replication runner summary aggregation fix

- The frozen Binance ETHUSDT replication's first full historical run [44597989645](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44597989645) passed deterministic tests and reached the final side/regime summary stage, then failed because a two-column pandas groupby yields (key_tuple, group), not three separate values.
- Fixed the summary aggregation in research/binance_ethusdt_ema20_cross_exchange_replication.py and added a side_regime_groupby deterministic regression test. Seven self-test groups now run before any historical download.
- Updated the workflow to run the expensive frozen replication only on workflow_dispatch, pull_request, or a push with the explicit [run-eth-replication] marker. Ordinary branch pushes remain in the deterministic-only lane.
- Targeted rerun [44635977816](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44635977816) passed the deterministic step and was still in the archive-download/event-study step at the time of this log update. No market performance result is claimed until the run and uploaded artifact are inspected.
