# Salty Quant — Deterministic Multi-Strategy Paper Desk

This branch keeps two selectable paper/research lanes. The default `WORKER_MODE=quant` runs the deterministic multi-strategy supervisor without AI calls. Set `WORKER_MODE=dns` to run the visual DNS mapper plus a local five-minute watcher; its optional Bull/Bear/Chief Trader debate is invoked only after a local DNS setup appears. Both lanes are paper-only and keep deterministic risk checks authoritative.

## Current operating mode: shadow research only

The six strategy families are implemented and run independently on closed OHLCV candles. Candidates are scored, mechanically validated, compared, and written to a durable JSONL research log. They are **not** sent to Discord as execution alerts yet.

`quant_supervisor.APPROVED_STRATEGIES` is intentionally empty. The existing EXP-001 and OI/volatility screens did not validate a production-ready edge, so no strategy is currently promoted. Do not populate that set until a frozen strategy version has passed the documented chronological out-of-sample, walk-forward, parameter-neighbourhood, regime and stressed-cost review. The quality score is a transparent rule rubric, not a probability or measured win rate.

The worker still manages any already-open paper positions in the shared state file and sends their confirmed TP/SL/TIME outcomes. It does not submit broker/exchange orders.

## Runtime architecture

1. `data.py` fetches public, closed Delta Exchange India OHLCV for BTCUSD, ETHUSD and XAUTUSD on 5m, 15m, 1h, 4h, 1d and 1w, validates candle integrity/freshness, and maintains rolling cache files.
2. `quant_strategies.py` evaluates six independent strategy families using only closed OHLCV:
   - Trend pullback (4h/1h EMA trend, 15m EMA20 pullback/reclaim, 5m confirmation).
   - Breakout/retest (1h 20-bar range break, 15m level retest, 5m confirmation).
   - Volatility expansion (15m ATR expansion plus 20-bar breakout, aligned with 4h/1h trend).
   - Liquidity sweep reversal (15m sweep and close back inside a prior 20-bar range, then 5m confirmation).
   - Mean reversion (1h Bollinger re-entry and RSI extreme, only in a balanced 4h regime).
   - Momentum continuation (1h directional move, 4h/1h trend alignment, 15m displacement and 5m follow-through).
3. `quant_supervisor.py` validates finite prices, direction/level ordering, 2R minimum, stop distance between 0.35 and 2.5 ATR, a minimum 75/100 rule-quality score, signal-candle freshness and one open paper position per symbol. Near-equal opposite-side candidates cause NO_TRADE. The top candidate is only a research preview unless its strategy ID is explicitly promoted after validation.
4. `quant_worker.py` runs once per new closed 5m candle, records all candidates and the supervisor decision in `research/quant_signals.jsonl`, and only sends an execution alert for a promoted strategy. No model calls or image interpretation are involved.
5. `trade_lifecycle.py` independently tracks open paper positions from contiguous closed 5m candles. A data gap leaves the outcome unresolved; it cannot infer a first TP/SL across an unobserved interval. Same-candle ambiguity is resolved conservatively as SL first.
6. `discord.py` formats deterministic quant execution alerts and separate confirmed TP/SL/TIME updates. There are no WATCH/status messages. Alert delivery failure does not open a paper position.

## Visual DNS sub-setup watcher

With `WORKER_MODE=dns`, the visual AI still owns the demand/supply map. The local watcher does not derive zones; it tests independent closed-5m confirmations only at active quality >=3 AI-mapped bands:

- Liquidity sweep/reclaim.
- Demand or supply zone rejection.
- BOS/CHOCH-style break of the recent 5m swing after a DNS reaction.
- 15m EMA20/EMA50 trend pullback with 5m reclaim.
- Three-candle FVG retrace when the imbalance overlaps the mapped DNS band.
- RBS/SBR role reversal: close through the mapped band, a separate retest candle that holds it, then 5m follow-through.

Every candidate must remain within 0.35% of its mapped band, use the nearest eligible opposing DNS band as target, and offer at least 2R. Zone invalidation is checked using the zone's own timeframe. The watcher returns separate candidates; the worker ranks them by zone quality and R multiple, debates at most one per symbol/cycle, and still permits only one active paper position per symbol. Pattern labels are descriptive OHLCV rules, not proof of resting liquidity or a validated profitable edge.

## Scoring and risk controls

- Strategy families produce separate candidates; incompatible long and short ideas are never blended.
- A candidate must match the latest closed 5m price exactly and pass the mechanical level/ATR/2R checks.
- Rule-quality points are assembled from higher-timeframe alignment, the setup trigger, 5m confirmation, volume confirmation and valid risk geometry. They are not calibrated probabilities.
- Selection requires a clear winner. Near-tied opposing candidates result in NO_TRADE.
- Only strategy IDs in `APPROVED_STRATEGIES` may send execution alerts. The set is empty today; research previews are logged only.
- One open paper position per symbol is allowed.
- No order, leverage change, account mutation or live-trading action exists in this worker.

## AI and legacy modules

The default `quant` lane does not require `OPENAI_API_KEY`, chart images or DNS map refreshes. The optional `dns` lane reuses the visual DNS map pipeline: one batched map refresh when a symbol has no map, its refresh interval expires, or a mapped zone is invalidated. The local watcher then checks closed candles on every worker cycle without calling a model.

For a rare confirmed DNS candidate, `ai_trade_agents.py` can run three separate roles in sequence: Bull Researcher, Bear Researcher and Chief Trader. This is opt-in through `AI_TRADE_DEBATE_ENABLED=true`; an explicit Chief Trader APPROVE is required when enabled. Missing API access, malformed output, REJECT or NO_TRADE blocks that candidate. The agents cannot change entry, stop or target. The deterministic DNS validation and paper position limits remain authoritative. See [TRADINGAGENTS_ADAPTATION.md](TRADINGAGENTS_ADAPTATION.md) for the design and setup.

## Instruments and data

- BTC: Delta Exchange India BTCUSD perpetual.
- ETH: Delta Exchange India ETHUSD perpetual.
- Gold: Delta Exchange India XAUTUSD Tether Gold perpetual; this is not spot XAUUSD.
- Public candle data needs no Delta credentials. Optional Delta credentials are used only by a strictly read-only startup check.
- The six native resolutions are fetched directly. Missing intervals are not filled.
- The worker checks the freshness of all six intervals before generating candidates.

## Run locally

1. Copy `.env.example` to `.env`.
2. Configure `DISCORD_TRIGGER_WEBHOOK` (or `DISCORD_WEBHOOK`) for future promoted alerts and existing paper outcome delivery. OpenAI credentials are not needed.
3. Install and test:
   ```bash
   pip install -r requirements.txt
   python -m compileall -q .
   python test_quant_engine.py
   python test_quant_backtest.py
   python test_ai_trade_agents.py
   python test_dns_engine.py
   python smoke_delta_feed.py
   ```
4. Run one paper/shadow cycle:
   ```bash
   python quant_worker.py
   ```
5. Run the aligned persistent worker:
   ```bash
   docker compose up -d --build
   docker compose logs -f
   ```

The default worker uses the AI-free quant lane. For the visual DNS lane, set `WORKER_MODE=dns` in `.env`. To add the three-role candidate debate, also set `AI_TRADE_DEBATE_ENABLED=true` and configure `OPENAI_API_KEY`. Keep the debate disabled to use only the infrequent DNS map refresh and the local watcher.

The persistent `./salty_data` volume stores state, rolling candles, quant candidate logs and the worker heartbeat. Use one worker instance only.

## Configuration

- `WORKER_INTERVAL_SECONDS`: aligned worker cycle interval; default 300 seconds.
- `DATA_DIR`: rolling OHLCV cache directory.
- `STATE_PATH`: persistent paper position/state JSON.
- `QUANT_RESEARCH_PATH`: append-only deterministic candidate/decision log; default `research/quant_signals.jsonl`.
- `DISCORD_TRIGGER_WEBHOOK` or `DISCORD_WEBHOOK`: execution/outcome destination.
- `DELTA_API_KEY`, `DELTA_API_SECRET`: optional read-only startup validation only.

GitHub Actions schedule remains opt-in through `ENABLE_GITHUB_SCHEDULE=true`; leave it unset unless a single scheduler is deliberately selected. Manual dispatch performs one paper/shadow cycle. No deployment or schedule enablement is performed by code commits.

Implementation notes and validation scope for the DNS-anchored SMC watcher are in [SMC_SUBSETUP_WATCHER_2026-11-06.md](quant_discovery/SMC_SUBSETUP_WATCHER_2026-11-06.md).

## Quant Discovery and promotion protocol

Research is separate from the runtime signal engine. Existing historical screens rejected the baseline candidates; no strategy is currently production-approved. New hypotheses must be tested on verified historical data with:

- Data hashes, coverage, gaps, UTC timestamps and contract provenance.
- Closed-candle decisions and next-executable-bar fills in the backtester.
- Chronological train/validation/untouched OOS splits, purge/embargo and at least three walk-forward folds where data permits.
- Fees, spread, slippage and funding only when event semantics are verified; unavailable costs remain explicit stress assumptions, never silently zero.
- Win rate, sample size, expectancy, profit factor, max drawdown, longest losing streak, trade frequency and regime dependence.
- Parameter-neighbourhood and 1.5x/2x stressed-cost robustness.
- A written promotion review before adding a strategy ID to `APPROVED_STRATEGIES`.

The verified archive and experiment outputs live outside Git where appropriate. XAUT has materially shorter history than BTC/ETH; its results must not be described as three-year evidence. A green CI run proves code and feed checks, not a profitable trading edge.

## Safety boundary

This branch is paper-only. It does not place exchange orders, enable live trading, change credentials, deploy infrastructure, or modify the default `main` branch. The legacy default-branch scheduled workflow is separate and must be resolved explicitly before any production cutover.
