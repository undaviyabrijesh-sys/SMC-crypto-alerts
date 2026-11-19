# Salty Quant Terminal — read-only API

The FastAPI adapter exposes persisted repository data to the Quant Terminal. It is intentionally a **read-only projection**: it does not call exchange endpoints, fetch candles, run a strategy, run a backtest, mutate state.json, send Telegram/Discord messages, or submit orders.

## Run locally

From the repository root:

\`\`\`bash
python -m pip install -r requirements.txt
uvicorn quant_terminal.api.main:app --host 127.0.0.1 --port 8000
\`\`\`

The default is loopback-only. If the API must be reached by a separate trusted server process, set QUANT_API_TOKEN in the API process and send Authorization: Bearer <token> from that server. Never put this token in a NEXT_PUBLIC_* variable or browser bundle. No CORS origins are enabled. Do not expose this API directly to the public internet; deployment requires a separate authentication, network, rate-limit and audit review.

Paths are resolved from the repository root unless an explicit path environment variable is supplied:

- DATA_DIR (default market_data)
- STATE_PATH (default state.json)
- QUANT_RESEARCH_PATH (default research/quant_signals.jsonl)
- QUANT_RESEARCH_LEDGER (default research/RESEARCH_LEDGER.md)
- QUANT_DISCOVERY_DIR (default quant_discovery)

## Endpoints

All data endpoints are GET only. Every response carries a source and an explicit availability state; unavailable values remain null rather than being filled with zeros.

| Endpoint | Read source | Purpose |
|---|---|---|
| /api/v1/health | repository paths + quant_supervisor.APPROVED_STRATEGIES | API health, persisted-store presence and actual approved-strategy count |
| /api/v1/markets | existing data.normalize + persisted {SYMBOL}_{TIMEFRAME}.csv | latest closed candle and per-timeframe freshness for BTC, ETH and XAU/XAUT |
| /api/v1/scanner/candidates | tail of research/quant_signals.jsonl | latest recorded candidate/decision per symbol; records older than 20 minutes are stale |
| /api/v1/research/experiments | research/RESEARCH_LEDGER.md | latest ledger sections; does not infer approval from prose |
| /api/v1/backtests | quant_discovery metadata, primary/metrics CSVs and result reports | index of saved artifacts; it never launches a backtest |
| /api/v1/paper/positions | read-only JSON parse of state.json | open paper positions and pending outcomes |
| /api/v1/paper/history | read-only JSON parse of state.json | retained closed paper trade history |
| /api/v1/risk/summary | paper state + quant_supervisor.APPROVED_STRATEGIES | open-position count and retained gross-R diagnostics |

## Status semantics and limitations

- live for a market means the latest persisted closed 5m candle is within the repository freshness limit and the last 15 candles are contiguous. It is not a websocket tick or a guaranteed exchange connection.
- Each timeframe is assessed separately. A fresh 5m feed does not imply every higher timeframe is fresh.
- stale means data exists but fails its age/continuity checks. unavailable means the source is missing or unreadable.
- Paper state is unavailable when state.json has not been created or cannot be safely parsed; this is not reported as an empty account.
- The current paper state does not persist account capital or position quantity. Account equity and notional exposure therefore remain unavailable. The retained-history drawdown is a gross-R diagnostic over the retained window, not account drawdown or fee-adjusted equity.
- Backtest artifacts are indexed from persisted research outputs. The API does not recompute metrics or promote candidates.
- quant_supervisor.APPROVED_STRATEGIES remains authoritative. A score or research preview is not an approved strategy.

## Safety boundary

There are no order, cancel, amend, alert-send, worker-run or backtest-run endpoints. No exchange credentials are imported by this adapter. Keep the API local until the separate deployment security review is complete.
