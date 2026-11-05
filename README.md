# Salty Quant AI — Visual Market Desk

This development branch replaces the old coded SMC decision path with a vision-first AI analyst.

## Core design

1. A single persistent worker wakes on aligned five-minute boundaries.
2. The data layer refreshes closed Delta OHLCV candles for BTCUSD, ETHUSD and XAUTUSD and persists the rolling market data.
3. The local DNS engine loads the last AI-authored market map and monitors every new closed 5m candle without an AI call.
4. A separate map-only multimodal AI request runs only when a map is missing, its four-hour refresh is due, or a confirmed 1h close breaks a mapped zone. All due symbols are batched into one request.
5. AI returns demand/supply bands, quality, timeframe, visual evidence, liquidity, bias and structure only. It does not select entries or issue trade recommendations.
6. The local engine's first deliberately narrow detector looks for a 5m liquidity sweep beyond an AI zone, reclaim close, confirming close beyond the sweep candle, and at least 2R room to the nearest opposing AI zone.
7. Confirmed local candidates are paper-alerted to Discord; the existing closed-candle tracker reports TP, SL or TIME separately. No broker orders are placed.

## Demand and supply visual workflow

Demand and supply (DNS) is the primary location framework on this branch. The vision model first maps demand/supply bands from the raw six-timeframe chart photo. Liquidity sweeps, CHOCH/BOS, trend pullbacks, FVGs, RBS/SBR, breakout/retests, momentum and range/mean-reversion patterns are evaluated only as sub-setups or confirmations at a relevant DNS zone; a mid-range standalone pattern cannot qualify.

After the AI response, the same six-panel chart is rendered a second time with the model-reported demand bands (green), supply bands (red), and selected entry band (yellow outline) drawn only on their source timeframe panels. The original raw image remains the model input, so overlays do not steer the model's own zone detection. The chart renderer preserves each panel's original price scale and does not calculate zones.

The latest review image for each symbol is atomically saved under `DATA_DIR/review_charts/<SYMBOL>_latest.png` (default `market_data/review_charts/`). Every successful visual decision also records its zone output and review-image path/hash in the research JSONL log. These review images are audit aids, not signals and not a replacement for chart review.

The mechanical trade gate now requires a LONG entry band to overlap an AI-mapped demand zone, or a SHORT entry band to overlap an AI-mapped supply zone, with zone quality at least 3/5 and current-price proximity within the existing threshold. Existing confidence, 2R, stop/target ordering, freshness and position limits remain unchanged. All other setup families remain secondary confirmations and cannot bypass DNS.

Live visual verification requires a successful OpenAI API response. The last recorded real request reached the API but returned HTTP 429 `insufficient_quota / credit_balance_exhausted`; CI and synthetic chart tests do not establish that live AI zone detection is accurate or profitable. Restore API quota, run one manual paper-only cycle, then inspect the three latest review images and subsequent paper outcomes before making a performance claim.


## AI map + local engine separation

The active worker is `dns_worker.py`, not the former AI-per-candle `main.py` path. It refreshes OHLCV and runs the local watcher every five minutes. The AI map call is separate and only runs when a symbol has no map, the map reaches its configured age (default four hours), or the latest closed 1h candle invalidates a mapped zone.

The persistent registry is `market_data/dns_map.json` (Docker volume: `/data/market_data/dns_map.json`). Every accepted AI map is versioned; previous maps are retained for audit. The AI response is map-only: demand/supply zones, quality, timeframe, evidence, liquidity, bias and structure. No entry, stop or target is requested from the model.

The first local detector is intentionally conservative and narrow: it requires a 5m candle to sweep beyond a mapped zone and close back through the far edge, the next 5m candle to confirm beyond the sweep candle extreme, and at least 2R room to the nearest opposing AI zone. A confirmed 1h close beyond a zone's distal boundary blocks local triggers from that zone while a refresh is attempted. This is an initial testable detector, not a validated profitable strategy and not yet a complete implementation of every DNS sub-setup.

The map refresh default is four hours and can be changed with `DNS_MAP_REFRESH_HOURS`. Local scanning makes no OpenAI request. If an AI refresh fails, the last map is retained, invalidated zones remain blocked, and the local watcher continues only where the map remains structurally valid. Trade alerts and outcomes are paper-only; no exchange orders are submitted.

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
- The local watcher runs every five minutes without AI calls. AI map refreshes are age/event driven (four-hour default), batched across due symbols, and throttled to at most one failed refresh attempt per symbol every 30 minutes.
- One open paper position per symbol is allowed.
- The first local detector supports only a confirmed DNS liquidity-sweep/reclaim pattern, with entry at the confirming closed 5m candle and a target at the nearest opposing mapped zone. Other sub-setups are not yet wired into the local detector.
- Trade tracking is paper tracking, not a broker fill and not an exchange order. The entry is assumed at the confirming closed 5m candle close so the signal lifecycle can be measured consistently.
- If Discord delivery fails, the alert is retried briefly; undelivered signals are not silently marked as active paper trades.
- Same-candle TP/SL ambiguity is resolved conservatively as SL first.
- Trade outcomes are sent as separate Discord messages when TP, SL or TIME exits are confirmed from closed 5m candles.
- A daily paper P&L summary helper exists but is disabled in the provided Docker and GitHub Actions configurations (`ENABLE_DAILY_PNL_REPORT=false`). Only enable it after an explicit request; the default Discord stream is execution alerts plus confirmed TP/SL/TIME outcomes.

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
- Writes one CSV per symbol/timeframe plus manifest.json and coverage.csv. Reports include duration-estimated requested-range coverage and observed-span coverage, missing-bar/gap counts, empty request windows, row count and SHA-256.
- Writes atomically and keeps temporary chunks under historical_data/.work/.

The archive defaults to historical_data/ and is intentionally Git-ignored. Store this folder on durable local or mounted storage and back it up; do not commit large market datasets or treat a short-lived CI cache as the research archive. XAUTUSD is Delta's Tether Gold perpetual, not spot XAUUSD. This first collector records traded-price OHLCV only; it does not infer spread, order-book depth or funding costs. Those inputs must remain explicitly unavailable until separately collected and validated.

A cloud collection workflow is available at `.github/workflows/historical-archive.yml`. Its output is a temporary GitHub Actions artifact (14-day retention), not permanent storage. Export verified archives to durable storage and keep the raw files out of Git. The workflow is guarded against accidental repeat downloads.

Delta documents a maximum of 2,000 candles per historical-candle response. See the official [Delta historical OHLC candles API documentation](https://docs.delta.exchange/).

## Local validation

    pip install -r requirements.txt
    python test_visual_pipeline.py
    python smoke_delta_feed.py
    python smoke_delta_auth.py

The offline test suite does not call the OpenAI API. The Delta feed smoke test uses the public market-data API. The authenticated smoke test requires DELTA_API_KEY and DELTA_API_SECRET to be set in the private environment and the machine's public IP to be included in the Delta key's whitelist. It makes one read-only request and does not place orders.

## Legacy modules

zones.py, score.py, news.py, replay.py and legacy_synthetic_tests.py remain for reference. The new main.py does not import the old zone finder, old confluence scorer, or old WATCH/TRIGGER pipeline.


### Quant Discovery initial screen

After extracting the verified historical archive into historical_data/, run:

    python quant_discovery/initial_screen.py --data-dir historical_data

The script verifies all 18 CSV hashes/row counts before writing OOS, cost, regime, parameter-robustness and walk-forward summaries to quant_discovery/results/. Read quant_discovery/EXP001_INITIAL_SCREEN.md before interpreting results. The initial fixed-parameter screen rejected all baseline candidates at the stated cost scenario; no research result feeds production alerts.
