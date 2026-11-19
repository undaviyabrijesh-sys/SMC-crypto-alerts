# Salty Quant Terminal

The web interface for **SALTY QUANT AI — QUANT TERMINAL**. This is a crypto-first research and paper-trading dashboard, built as a separate frontend so the existing Python research and paper engines remain authoritative.

## Current status

**Phase 0 — UI foundation.** The current page is a navigation and visual shell only. It does not connect to an exchange, load market prices, generate signals, run backtests, or submit orders. Any unavailable metric is intentionally shown as unavailable rather than fabricated.

## Product modules

- Overview — system health, feed freshness, strategy approval state and paper-trading summary.
- Live Markets — BTC, ETH, XAUT and liquid perpetual markets.
- Scanner — candidates from the existing deterministic strategy engine.
- Strategy Research — hypotheses, experiment history and validation state.
- Backtesting — reproducible runs, costs, equity and risk analytics.
- Paper Trading — open positions and confirmed TP/SL/TIME lifecycle events.
- Portfolio / Trade History — paper ledger, realized and unrealized results.
- AI Analyst — answers grounded in accessible market/research/ledger data.
- Risk Management — exposure, sizing, drawdown and circuit-breaker visibility.

## Architecture boundaries

1. **Frontend:** Next.js App Router + React + TypeScript under this directory.
2. **Backend:** Reuse existing Python modules in the repository (`data.py`, `quant_strategies.py`, `quant_supervisor.py`, `quant_backtest.py`, `quant_worker.py`, `trade_lifecycle.py`, `options_collector.py`). Do not fork their trading logic into TypeScript.
3. **API:** Add a small, documented, read-only FastAPI adapter in a later phase. The browser must never receive exchange credentials or direct trading permissions.
4. **Storage:** Read persisted research logs, experiment metadata and paper state through an explicit adapter. Validate schemas and timestamps before display.
5. **Charts:** Add charting only after the API contract is stable; chart candles must carry exchange, symbol, timeframe, timestamp and freshness metadata.

## Read-only API contract (planned)

- `GET /api/v1/health` — service status, build/version and dependency checks.
- `GET /api/v1/markets` — instruments, latest closed candles/mark snapshots and freshness.
- `GET /api/v1/scanner/candidates` — current research candidates and validation reasons.
- `GET /api/v1/research/experiments` — experiment summaries and frozen ruleset versions.
- `GET /api/v1/backtests` — saved run metadata and result metrics.
- `GET /api/v1/paper/positions` — open and historical paper positions.
- `GET /api/v1/risk/summary` — paper exposure, drawdown and circuit-breaker state.

Every response should include `as_of`, `source`, and a status such as `live`, `stale`, or `unavailable`. Do not silently substitute cached or synthetic data for live data.

## Development sequence

1. Dashboard shell and architecture contract.
2. Read-only API and feed freshness indicators.
3. Scanner and research views backed by saved repository data.
4. Backtest analytics with fees, slippage, funding (when defensible), and reproducible run metadata.
5. Paper ledger and trade lifecycle views.
6. Data-grounded AI Analyst.
7. Tests, security review, accessibility and deployment-readiness checklist.

## Non-negotiable safety and research rules

- Crypto first; keep adapters extensible for Indian markets without mixing market calendars or execution assumptions.
- Research/shadow, validated and paper states must remain visibly distinct.
- Do not promote a strategy merely because it has a high score or an attractive historical result. Existing validation gates remain authoritative.
- No live order endpoints, exchange account mutations or real-money trading.
- No secrets or API keys in browser code, commits, test fixtures or logs.
- Do not deploy or change production alerts without explicit approval.
- If a data source is missing or stale, display that fact and suppress misleading metrics.

## Local development

Requirements: Node.js 20.9+ and npm.

```bash
cd quant_terminal
npm install
npm run dev
```

Open http://localhost:3000. The initial shell is deliberately feed-independent; backend integration is a subsequent phase.
