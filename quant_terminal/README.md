# Salty Quant Terminal

The web interface for SALTY QUANT AI — QUANT TERMINAL. This is a crypto-first research and paper-trading dashboard, built as a separate frontend so the existing Python research and paper engines remain authoritative.

## Current status

**Phase 2 — read-only API foundation implemented.** The Next.js page remains a navigation/visual shell and is not yet wired to the API. The new FastAPI adapter exposes persisted health, market freshness, scanner, research, backtest-artifact, paper-ledger and risk data. It does not fetch exchange data, run engines, mutate state, send alerts or submit orders. Missing data remains unavailable rather than being replaced with synthetic values.

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
2. **Backend:** Reuse existing Python modules (data.py, quant_strategies.py, quant_supervisor.py, quant_backtest.py, quant_worker.py, trade_lifecycle.py, options_collector.py). Do not fork trading logic into TypeScript.
3. **API:** quant_terminal/api/main.py is a separate read-only FastAPI projection over persisted repository data. It imports the existing candle normalizer and strategy-approval set, but never calls the market fetcher, worker, paper lifecycle or backtest runner.
4. **Storage:** Read persisted research logs, experiment metadata and paper state through an explicit adapter. Validate schemas and timestamps before display.
5. **Charts:** Add charting only after the API contract is stable; chart candles must carry exchange, symbol, timeframe, timestamp and freshness metadata.

## Read-only API

See api/README.md for the complete contract, status semantics, environment paths and security boundary. Available endpoints:

- GET /api/v1/health
- GET /api/v1/markets
- GET /api/v1/scanner/candidates
- GET /api/v1/research/experiments
- GET /api/v1/backtests
- GET /api/v1/paper/positions
- GET /api/v1/paper/history
- GET /api/v1/risk/summary

Run locally from the repository root:

    python -m pip install -r requirements.txt
    uvicorn quant_terminal.api.main:app --host 127.0.0.1 --port 8000

The API is loopback-only unless QUANT_API_TOKEN is configured. No CORS origins are enabled. Do not expose it publicly or deploy it until a separate authentication, network, rate-limit and audit review is complete. The frontend does not receive exchange credentials or the API token.

## Development sequence

1. Dashboard shell and architecture contract — complete.
2. Read-only API and feed freshness/status — backend foundation complete; frontend integration pending.
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

## Local frontend development

Requirements: Node.js 20.9+ and npm.

    cd quant_terminal
    npm install
    npm run dev

Open http://localhost:3000. The page is still feed-independent until the next frontend integration phase.
