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

### Paper lifecycle UI verification and ETH replication result — 2026-11-20

- Frontend workflow [44636199511](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199511) completed successfully after Paper Trading, Portfolio and Trade History integration: dependency installation, TypeScript type-check and production Next.js build all passed.
- Read-only API workflow [44636199683](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199683) completed successfully: API compilation and all read-only API contract tests passed. No API endpoint or paper lifecycle code changed in this increment.
- Full deterministic repository CI [44636199485](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199485) completed successfully, including offline visual/quant/paper contracts, public Delta OHLCV and OI checks, funding/mark/OI history probes and the archive pilot.
- ETHUSDT frozen Binance cross-exchange replication [44635977816](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44635977816) completed successfully after the side/regime aggregation fix. Its 1.89 MB artifact was downloaded and independently inspected: all 53 archive checksums and ZIP CRCs passed, 47,424 15m bars were continuous, and the source hash matched metadata.
- ETH result: 17 qualifying events, 16 matched controls. 1h net mean -17.08bp/PF 0.437; 4h net mean +30.18bp/PF 2.198, but 4h median -13.18bp and day-cluster confidence intervals crossed zero. Removing the two largest 4h winners made the mean negative. No stop/target, R, account PnL or funding cashflow study was performed; no promotion.
- Durable ETH report, summary JSON, monthly/fold/cost/side-regime CSVs and research-ledger entry are committed. Full source/trade/control files remain in the Actions artifact for 30 days.
- Updated the ETH workflow condition so pull requests and ordinary pushes run deterministic tests only; full historical archive download is restricted to workflow_dispatch or a push with the explicit [run-eth-replication] marker. A duplicate PR-triggered run had already been queued under the previous guard; it is tracked separately and is not used as additional evidence.
- No deployment, main-branch change, paper-state mutation, live alert or exchange order.

### ETH replication reproducibility and workflow-cost guard — 2026-11-20

- A second full run [44636199588](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199588) completed and uploaded artifact 14584126868. After download/extraction, all 14 files were byte-identical to the first successful run 44635977816, including the raw 15m source, archive manifest, events/controls, all return tables, monthly/fold/cost/side-regime outputs, report and summary metadata. Source SHA-256 matched exactly.
- The duplicate was already queued under the earlier pull-request trigger condition. The workflow guard was then tightened: PRs and ordinary pushes execute deterministic tests only; full historical download is allowed only for workflow_dispatch or an explicitly marked [run-eth-replication] push.
- The byte-identical rerun confirms deterministic reproducibility of the frozen archive download and event-study outputs. It is not a new sample, independent exchange, or temporal OOS validation.

### Backtesting inventory — normalized ETH event-study records

- Added a discoverable METADATA JSON and METRICS CSV for the completed Binance ETHUSDT 15m EMA20/4h regime event study.
- The existing read-only backtest artifact index already scans METADATA JSON and METRICS CSV files; the existing UI displays recorded metadata, CSV columns and bounded sample rows. No new API endpoint or backtest engine was added.
- Metadata marks the result completed_inconclusive, identifies 17 events/16 matched pairs, records the source hash and archive verification, and explicitly leaves trade_count null because the study is fixed-horizon rather than a stop-based trade backtest.
- Metrics CSV exposes the 1h/4h means, medians, descriptive PF, matched lift, confidence intervals and month/fold stability to the artifact inventory. The dashboard remains a local read-only development app; no deployment or remote runtime integration was performed.

## 2026-11-20 — Paper lifecycle, portfolio and Backtesting inventory integration

- Paper Trading, Portfolio and Trade History views are connected to existing GET-only API snapshots. They display persisted paper positions, bounded closed-trade history, gross-R diagnostics and explicit unavailable values for account equity, notional exposure and circuit-breaker state. No paper state mutation or order controls.
- Added normalized METADATA JSON and METRICS CSV artifacts for the ETH cross-exchange event study and BTC VWAP trend-continuation matrix. Existing backtest inventory patterns already index these filenames; no duplicate backtest engine or API endpoint was introduced.
- Added an API regression test that verifies the Backtesting artifact index reads both metadata JSON and normalized metrics CSV. The first test run failed because the CSV fixture contained literal backslash-n text; the fixture was corrected using chr(10). Latest API workflow [44637177057](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44637177057) passed, and full deterministic CI [44637177166](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44637177166) passed.
- Frontend TypeScript and production build for Paper Trading/Portfolio/Trade History passed in [44636199511](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199511). API compile/contract tests passed in [44636199683](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199683).
- ETH replication: full Binance cross-exchange run [44635977816](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44635977816) and independent rerun [44636199588](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636199588) both succeeded; all 14 extracted files were byte-identical. Result remains 1h rejected / 4h inconclusive, no promotion.
- BTC VWAP trend-continuation 648-config matrix [44636952868](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44636952868) succeeded and its artifact was independently audited. Zero training-qualified configurations; no validation pass; no OOS. Report and normalized files are committed under quant_discovery/.
- Added two more deterministic tests to the VWAP script (UTC-day VWAP reset and exact 648-config count), then added an end-exclusive split-boundary metadata helper/test. Latest self-test-only workflow [44637457514](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44637457514) passed all 11 deterministic tests. Historical download, matrix, summary and artifact steps were skipped as intended.
- The VWAP workflow now requires workflow_dispatch or a push containing [run-btc-vwap-matrix] to run the expensive 2-year matrix; ordinary pushes run tests only. The ETH workflow similarly requires workflow_dispatch or [run-eth-replication], and its artifact-upload step is gated to the same full-run condition. Two intermediate ETH PR runs failed because the upload step still ran after the historical download was skipped; the upload guard was corrected, and [44637089205](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44637089205) passed.
- Current UI is still a local read-only development app. No deployment, main-branch modification, production rule change, live alert, paper-state write or exchange order.

## 2026-11-20 — AI Analyst and Risk Management evidence views implemented

- Connected the final two first-release terminal sections using the existing read-only API snapshots; no new API endpoint or second risk engine was added.
- AI Analyst is explicitly a deterministic evidence brief, not a claim of an external generative-model connection. It summarizes persisted market freshness, scanner candidate counts, research-ledger entries, backtest artifact inventory, paper position state and authoritative approved-strategy count. It does not predict prices, create signals or promote strategies.
- Risk Management displays the existing retained gross-R diagnostics, open/pending paper counts and per-position entry-to-stop price distance when those fields exist. It explicitly leaves account equity, notional exposure, monetary position risk, daily loss limit and circuit-breaker state unavailable because the source paper schema does not persist the required capital/quantity/control inputs.
- No account-level risk is inferred from position count or price distance. Gross-R drawdown is labeled as a retained diagnostic, not account-equity drawdown.
- Updated the Overview eyebrow to remove a stale hard-coded calendar date.
- Frontend type-check/production build for these latest two views is pending the next frontend workflow run. Existing API contracts remain unchanged; no order, alert or paper-state mutation routes were added.
- No deployment, main-branch modification or production rule change.

## 2026-11-20 — Backtesting CSV evidence preview

- Extended the existing Backtesting artifact cards to render a collapsed, horizontally scrollable preview of the last up to 25 rows already returned by the read-only API for persisted CSV artifacts.
- The preview uses the artifact's recorded column names and row values verbatim; it does not calculate, normalize, or promote performance metrics in the browser.
- Kept the API's existing 512 KB per-file parsing cap and 25-row response bound. Files without supported CSV rows continue to show metadata/provenance only.
- Added compact responsive table styling. No API route, engine, paper state, execution behavior, or strategy validation gate changed.
- Next frontend check: TypeScript and production build on `ai-quant-rebuild`.


## 2026-11-20 — Backtesting CSV evidence preview and ETH Supertrend result indexing

- Backtesting artifact discovery now indexes all CSV files contained in the bounded `quant_discovery/` directory, rather than only PRIMARY/METRICS-named CSVs. The API still reads at most 512 KB per CSV and returns only the last up to 25 rows.
- The UI displays those persisted rows in a collapsed, horizontally scrollable preview. It renders recorded values verbatim; it does not recalculate performance or infer validation/promotion.
- Added an API regression test for monthly and trade-named CSV discovery plus the 25-row bound.
- Completed authoritative ETH Supertrend workflow [44693535437](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44693535437). All 53 official archive checksums passed; 47,424 contiguous bars were reconstructed. Development: 332 trades, PF 0.789, -24.25R, DD -28.58R, 13-loss streak. Validation: 75 trades, PF 0.748, -8.26R, DD -18.42R, 11-loss streak. Both gates failed; final 15% holdout remains retired/not evaluated. Full report and normalized result tables are committed under `quant_discovery/`.
- No API order/alert routes, strategy engines, paper state or production rules changed.


## 2026-11-20 — ETH funding schedule caveat recorded

- Corrected the ETH Supertrend result metadata/report: the earlier 00:00/08:00/16:00 UTC exclusion was only an assumed default-8h grid, not a verified historical ETHUSDT settlement schedule. Binance USD-M can switch settlement frequency; exact historical funding records expose `fundingTime`, `fundingRate` and `markPrice`.
- The 543 excluded / 500 remaining signal counts are now explicitly conditional on that proxy. The negative price-cost development/validation findings remain recorded, but no funding-aware PnL is claimed.
- Added a frozen funding-cashflow audit preregistration. It is an accounting correction only: same signal rules, no parameter tuning, no OOS, no promotion.

## 2026-11-20 — Actual ETH funding cashflow results indexed for Backtesting
- Added the 1,483-row official ETHUSDT funding snapshot and reproducible actual-funding audit outputs to the research branch.
- Committed normalized metadata, funding-aware trade ledgers, monthly/regime/side summaries, cost sensitivity and ambiguous-settlement rows under quant_discovery/. The existing read-only Backtesting artifact index discovers these CSV/metadata/report files; it does not recompute them.
- The audit is explicitly research-only and rejected; no strategy promotion, paper-state mutation, live order or alert route was added.


## 2026-11-20 — Backtesting metadata exposes funding evidence
- Expanded the read-only artifact metadata projection to include decision, parent workflow, funding record count/hash, funding accounting status, primary assumed round-trip cost and source-data end time.
- The ETHUSDT actual-funding audit metadata and its four saved trade ledgers are now discoverable in Backtesting. All trade-ledger CSVs are below the API's 512 KB preview cap; the UI still shows only the last 25 rows per file and does not recompute results.
- Added a regression test for these funding-evidence fields. The data remains research-only and rejected; no promotion state or live execution route was added.


## 2026-11-20 — BTC/ETH pair study indexed in Backtesting

- Added normalized pair-study RESULTS Markdown, METADATA JSON, METRICS CSV and diagnostic monthly/regime CSVs under `quant_discovery/`; the existing read-only artifact index discovers these files without a new endpoint or backtest engine.
- The indexed record is explicitly `completed_rejected`: 576 nominal configurations, zero training-eligible, zero validation passes, OOS not evaluated. The full matrix and raw trades remain in the GitHub Actions artifact; the committed CSVs are bounded summaries.
- Metadata records the source hashes, workflow/artifact IDs, chronological boundaries, primary assumed cost and the conditional funding-avoidance caveat. No UI-side metric calculation or strategy promotion.
- Existing frontend/API implementation is unchanged. This is data indexing only; no paper-state, order, alert or production rule mutation.
