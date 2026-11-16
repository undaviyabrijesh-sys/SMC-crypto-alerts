# Salty Quant — Deterministic Multi-Strategy Paper Desk

This branch contains three selectable paper lanes. The default `WORKER_MODE=quant` is the AI-free multi-strategy research/shadow lane. `WORKER_MODE=dns` is the separate visual DNS-map plus local watcher lane. `WORKER_MODE=visual` routes to the independent visual-first analyst, but it is disabled unless `ENABLE_VISUAL_PAPER=true` is explicitly set. All lanes are paper-only; no exchange orders are submitted.

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

## Visual-first independent paper analyst

The visual lane is separate from the DNS watcher. `visual_first_analyst.py` receives fresh, unannotated six-timeframe chart images (5m, 15m, 1h, 4h, 1d and 1w) and compares independent candidates: SMC/market structure, visually mapped supply/demand, liquidity sweeps, support/resistance, trend pullback, momentum, breakout/retest, volatility expansion, range rejection and mean reversion. No coded zone or market-structure detector selects, ranks or vetoes these candidates.

The model returns materially viable candidates with context/timeframe alignment, entry quality, invalidation, stop distance, target rationale, estimated R:R and conflicts. It selects one candidate ID or returns `NO_TRADE`. The mechanical validator does not substitute another candidate; it checks fresh chart watermarks, candidate identity, latest-price proximity, confidence and quality >=75, R:R >=2, stop distance 0.35–2.5 ATR, at least two evidence timeframes, one open/pending position per symbol, and a clear quality margin over any opposing actionable candidate. A close or stronger opposing candidate forces NO_TRADE.

Only an immediately actionable market setup can become a paper execution alert. Future retests are not sent as WATCH messages. The Discord visual alert includes setup family, entry band, trigger, invalidation, stop, target, rationale and cancellation conditions. Confirmed TP/SL/TIME outcomes are separate messages through the existing closed-5m lifecycle.

Run one local paper cycle only with explicit opt-in:

```bash
ENABLE_VISUAL_PAPER=true python visual_worker.py
```

For the persistent worker, set `WORKER_MODE=visual` and `ENABLE_VISUAL_PAPER=true`. The GitHub manual workflow also requires `lane=visual` and `confirm_visual_paper=true`; scheduled runs remain on the quant lane unless the pre-existing schedule opt-in is enabled. A valid `OPENAI_API_KEY` and usable API quota are required. Offline CI uses mocked model/API and Discord calls; it does not prove live delivery.

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

## Binance BTC/ETH options research data

The persistent worker also runs a read-only Binance Options collector. It does not change the paper-trading engine and never submits orders.

- Every five minutes (configurable), it records the current BTC/ETH option chain: underlying index, contract mark price, bid/ask/mark IV, delta, gamma, theta, vega, and per-contract open interest in contracts and USDT.
- On first run it queues up to 12 near-the-money contracts per underlying, limited to expiries within 90 days, and backfills up to 180 days of hourly option candles in small batches. Only completed candles with actual trade volume and trades are retained; no-trade placeholder bars and forming candles are excluded. Backfilled contracts are refreshed hourly.
- It also backfills 180 days of BTCUSDT and ETHUSDT Binance Spot 1h candles for the underlying signal series, then refreshes closed bars hourly.
- Default output path: `/data/market_data/binance_options` in Docker (or `$DATA_DIR/binance_options` elsewhere). Full-chain snapshots are daily CSVs under `snapshots/`; hourly contract history is under `historical_klines_1h/<BTC|ETH>/`; underlying candles are under `underlying/`. `collector_state.json` tracks progress and collection timestamps.
- A persistent mounted `/data` volume is required to retain the dataset across container restarts.

**Historical coverage limitation:** Binance's current Options API exposes historical contract candles, but its mark/IV/Greeks and open-interest endpoints return current snapshots, not historical time series. The collector therefore begins building a complete BTC/ETH IV/Greeks/OI history from its first successful live snapshot; it cannot recreate those metrics for earlier dates from the current API. Option trading can be sparse, so the 180-day candle backfill may contain far fewer than 180 days' worth of non-zero hourly bars. Expired contracts may also be unavailable from the current klines endpoint.

## Options Strategy Research Lab

The first backtest release evaluates five independent hourly strategies against Binance BTC/ETH option candles:

| ID | Strategy | Option position |
|---|---|---|
| OPT-01 | EMA8/EMA21 momentum plus 3-hour return confirmation | Buy ATM-nearest call on bullish signal or put on bearish signal |
| OPT-02 | 20-hour liquidity sweep followed by next-hour MSS confirmation | Buy call or put in the reversal direction |
| OPT-03 | EMA20 pullback/reclaim aligned with EMA20/EMA50 trend | Buy call or put in the trend direction |
| OPT-04 | New 12-hour vs 48-hour realized-range compression | Buy matched ATM call + put (long straddle) |
| OPT-05 | Same compression trigger | Buy matched 2% OTM call + put (long strangle) |

The engine uses only closed hourly underlying bars and actual traded option candles. A setup is known only after the underlying candle closes; entry is at the next eligible option candle open and is rejected when the option print is too late. No-trade bars are not forward-filled. Single-leg exits use premium stop/target levels, stop-first resolution when both levels occur in one candle, and a fixed holding limit. Straddles/strangles exit at a synchronized traded call/put candle after the holding horizon.

Run the backtest after the collector's initial history queue has completed:

```bash
python -m unittest -v test_options_research.py
python options_research.py --asset both --data-dir market_data/binance_options --out-dir research/options
```

For a Docker deployment with the persistent volume mounted:

```bash
python options_research.py --asset both --data-dir /data/market_data/binance_options --out-dir /data/research/options
```

Outputs include per-strategy CSV trades and JSON reports with train/validation/test splits (chronological 60/20/20 with a one-bar boundary purge), win rate, expectancy in model R, profit factor, drawdown, losing streaks, holding time, monthly summaries and per-contract trade-bar coverage. The initial defaults are 30% premium stop, 50% premium target and 4-hour maximum hold, with explicit fee, spread-proxy and slippage assumptions. They are research defaults, not optimized settings.

**Do not read the model PnL as a broker statement.** Historical bid/ask and book depth are unavailable in this feed; the spread is only a configured proxy. The engine does not model exchange contract multiplier/settlement, exercise, margin, liquidation or actual fill queue priority. Sparse option candles trigger conservative gap-guard exits and are flagged. This initial release is 1h only; it does not claim 5m/15m validation. Historical IV/Greeks/OI are not reconstructed: those snapshots begin accumulating prospectively. Every result stays research-only and does not promote a production strategy.

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

The default worker uses the AI-free quant lane. For the independent visual-first paper lane, set `WORKER_MODE=visual`, `ENABLE_VISUAL_PAPER=true` and configure `OPENAI_API_KEY`. The visual lane remains opt-in and fail-closed. For the separate DNS-map watcher, set `WORKER_MODE=dns`; the three-role Bull/Bear/Chief debate remains optional through `AI_TRADE_DEBATE_ENABLED=true`.

The persistent `./salty_data` volume stores state, rolling candles, quant candidate logs and the worker heartbeat. Use one worker instance only.

## Configuration

- `WORKER_INTERVAL_SECONDS`: aligned worker cycle interval; default 300 seconds.
- `DATA_DIR`: rolling OHLCV cache directory.
- `STATE_PATH`: persistent paper position/state JSON.
- `QUANT_RESEARCH_PATH`: append-only deterministic candidate/decision log; default `research/quant_signals.jsonl`.
- `ENABLE_VISUAL_PAPER`: explicit opt-in for the independent visual-first paper lane; default false.
- `VISUAL_FIRST_RESEARCH_PATH`: append-only visual candidate/decision log; default `research/visual_first_decisions.jsonl`.
- `VISUAL_FIRST_FAILURE_COOLDOWN_MINUTES`: API/data failure cooldown; default 30 minutes.
- `DISCORD_TRIGGER_WEBHOOK` or `DISCORD_WEBHOOK`: execution/outcome destination.
- `DELTA_API_KEY`, `DELTA_API_SECRET`: optional read-only startup validation only.

GitHub Actions schedule remains opt-in through `ENABLE_GITHUB_SCHEDULE=true`; leave it unset unless a single scheduler is deliberately selected. Manual dispatch performs one paper/shadow cycle; visual dispatch additionally requires the explicit `confirm_visual_paper=true` input. No deployment or schedule enablement is performed by code commits.

Implementation notes for the independent visual-first lane are in [VISUAL_FIRST_INDEPENDENT_ANALYST_V2_SPEC.md](quant_discovery/VISUAL_FIRST_INDEPENDENT_ANALYST_V2_SPEC.md). DNS watcher notes are in [SMC_SUBSETUP_WATCHER_2026-11-06.md](quant_discovery/SMC_SUBSETUP_WATCHER_2026-11-06.md).

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
