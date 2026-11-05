# Salty Quant AI — Visual Market Desk

This development branch replaces the old coded SMC decision path with a vision-first AI analyst.

## Core design

1. A single persistent worker wakes on aligned five-minute boundaries. GitHub Actions is available as a best-effort fallback/manual run, not the preferred clock.
2. The data layer downloads native OHLCV candles directly from Delta Exchange for BTCUSD, ETHUSD and XAUTUSD, removes still-forming candles, and carries a rolling raw-data store.
3. The chart renderer creates one six-panel image per symbol: Weekly, Daily, 4H, 1H, 15m and 5m, including candle wicks/bodies, price scale, timestamps and volume.
4. The images and a compact exact OHLCV snapshot are sent together in one multimodal OpenAI Responses API call.
5. The model visually identifies demand/supply bands, RBS/SBR, structure, liquidity, sweeps, imbalances and the trade idea. The old ATR zigzag/FVG zone finder and score engine are not called.
6. A deterministic safety layer checks the AI's proposed direction, entry freshness, stop/target ordering, minimum R:R and confidence threshold. It cannot create zones or trading setups.
7. Only validated actionable trade alerts are sent to Discord. The paper tracker reports TP, SL or TIME as a separate update.

## Data instruments

- BTC: Delta Exchange BTCUSD perpetual.
- ETH: Delta Exchange ETHUSD perpetual.
- Gold: Delta Exchange XAUTUSD Tether Gold perpetual.
- The public historical candle endpoint is used; no Delta API key is needed for market data. Delta's documentation explicitly marks `GET /history/candles` as unauthenticated, so adding an API key does not itself improve candle quality or historical coverage.
- An optional, strictly read-only Delta client signs a `GET /v2/users/trading_preferences` request at worker startup to verify the credentials. The client exposes no order, transfer, or account-mutation methods and logs only a pass/fail marker, not account preference contents.
- The six native resolutions are fetched directly from Delta (5m, 15m, 1h, 4h, 1d, 1w). Each request is deliberately kept below the API's 2,000-candle response cap.
- These are traded-price candles for the configured Delta contracts, not Yahoo proxies or an unrelated spot/futures feed.

## Recommended persistent worker deployment

Use one always-on Docker host (a small VPS or an always-on container service). Do not run multiple worker replicas because state and paper-position files are shared.

1. Copy .env.example to .env.
2. Add a valid OPENAI_API_KEY and DISCORD_TRIGGER_WEBHOOK to .env.
3. Start the worker with: docker compose up -d --build
4. Inspect logs with: docker compose logs -f
5. The persistent ./salty_data volume stores state, rolling OHLCV, AI decision history and a heartbeat file across restarts.

The worker runs immediately at startup, then aligns subsequent cycles to five-minute wall-clock boundaries. It never overlaps its own cycles. If one run overruns a boundary, it skips missed ticks rather than launching parallel analyses.

**Use exactly one scheduler.** The GitHub Actions schedule is disabled by default unless the repository variable ENABLE_GITHUB_SCHEDULE=true is explicitly set. Leave it unset when the Docker worker is running, or both runtimes could create duplicate independent paper signals. GitHub schedule is best-effort and may be substantially delayed; it should be treated as a fallback, not a precise five-minute service.

## Required runtime secrets

For Docker, use .env:
- OPENAI_API_KEY
- DISCORD_TRIGGER_WEBHOOK (or DISCORD_WEBHOOK)

Optional:
- DELTA_API_KEY
- DELTA_API_SECRET
- DELTA_API_BASE_URL (defaults to https://api.india.delta.exchange)
- OPENAI_MODEL (defaults to gpt-6.1-terra)
- OPENAI_REASONING_EFFORT (defaults to high)
- WORKER_INTERVAL_SECONDS (defaults to 300)

For GitHub Actions fallback, add OPENAI_API_KEY and DISCORD_TRIGGER_WEBHOOK (or DISCORD_WEBHOOK) as repository secrets. The optional Delta key is not checked on GitHub-hosted runners because Delta IP-whitelisting must match the runner's egress IP; use the authenticated smoke test from the whitelisted deployment host instead. Set repository variable ENABLE_GITHUB_SCHEDULE=true only when the Docker worker is not running.

## Alert behaviour

- No WATCH or generic market commentary messages are sent to Discord.
- No repeat AI analysis is performed for a symbol unless its latest fully closed 5m candle has changed.
- All available symbols are analysed together in one model call.
- One open paper position per symbol is allowed.
- The first release supports immediate MARKET entries only. A proposed entry must be within the configured tolerance of the last closed 5m price. Limit orders are not silently treated as fills.
- Trade tracking is paper tracking, not a broker fill and not an exchange order. The entry is assumed at the last closed 5m price so the signal lifecycle can be measured consistently.
- If Discord delivery fails, the alert is retried briefly; undelivered signals are not silently marked as active paper trades.
- Same-candle TP/SL ambiguity is resolved conservatively as SL first.
- Trade outcomes are sent as separate Discord messages.

## Data persistence and validation

- salty_data/ (Docker) stores state and raw data persistently. The GitHub Actions fallback uses Actions cache, which is a rolling development store and not a durable database.
- The live Delta feed was tested from GitHub Actions for BTCUSD, ETHUSD and XAUTUSD across all six intervals. The test also checks candle integrity, UTC timestamps, closed-bar filtering and the production freshness gate.
- CI runs Python compilation, offline rendering/signal-gate tests and the live public Delta feed smoke test.
- CI success does not prove that OpenAI API credentials are configured, that Discord webhooks deliver, or that any trading setup has positive expectancy.
- No strategy hit rate or backtest performance is claimed. First collect and label AI decisions, then build a replay/evaluation harness from preserved charts, candle data, prompts and outcomes.


## Quant Discovery — historical data bootstrap

The research archive is separate from the rolling market-data cache used by the visual analyst. It downloads public traded-price OHLCV for BTCUSD, ETHUSD and XAUTUSD on 5m, 15m, 1h, 4h, 1d and 1w. The default history window is three years; use explicit UTC dates to change it.

    python bootstrap_historical_data.py --years 3

A narrower first run can be used to validate connectivity and storage before a full archive:

    python bootstrap_historical_data.py --start 2026-10-01 --end 2026-11-05 --symbols BTC --timeframes 5m 1h

The collector:
- Uses Delta's public GET /v2/history/candles endpoint and never needs exchange credentials.
- Keeps each request within the documented 2,000-candle response cap and runs sequentially with a conservative delay.
- Retries rate limits and transient server/network failures with bounded backoff.
- Resumes interrupted symbol/timeframe downloads from local chunk checkpoints; completed, hash-verified archives are skipped on later runs.
- Validates timestamps and OHLCV values, removes duplicate timestamps deterministically, and never fills missing candles.
- Writes one CSV per symbol/timeframe plus manifest.json and coverage.csv. Reports include the requested-range and observed-span coverage, missing-bar/gap counts, empty request windows, row count and SHA-256.
- Writes atomically and keeps temporary chunks under historical_data/.work/.

The archive defaults to historical_data/ and is intentionally Git-ignored. Store this folder on durable local or mounted storage and back it up; do not commit large market datasets or treat a short-lived CI cache as the research archive. XAUTUSD is Delta's Tether Gold perpetual, not spot XAUUSD. This first collector records traded-price OHLCV only; it does not infer spread, order-book depth or funding costs. Those inputs must remain explicitly unavailable until separately collected and validated.

Delta documents a maximum of 2,000 candles per historical-candle response. See the official [Delta historical OHLC candles API documentation](https://docs.delta.exchange/).

## Local validation

    pip install -r requirements.txt
    python test_visual_pipeline.py
    python smoke_delta_feed.py
    python smoke_delta_auth.py

The offline test suite does not call the OpenAI API. The Delta feed smoke test uses the public market-data API. The authenticated smoke test requires DELTA_API_KEY and DELTA_API_SECRET to be set in the private environment and the machine's public IP to be included in the Delta key's whitelist. It makes one read-only request and does not place orders.

## Legacy modules

zones.py, score.py, news.py, replay.py and legacy_synthetic_tests.py remain for reference. The new main.py does not import the old zone finder, old confluence scorer, or old WATCH/TRIGGER pipeline.
