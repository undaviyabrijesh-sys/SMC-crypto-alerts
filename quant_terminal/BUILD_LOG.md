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
