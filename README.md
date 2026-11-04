# Salty Quant AI — Visual Market Desk

This development branch replaces the old coded SMC decision path with a vision-first AI analyst.

## Core design

1. GitHub Actions wakes every 5 minutes.
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
- The public historical candle endpoint is used; no Delta API key is needed for market data.
- Each of the six native resolutions is fetched directly from Delta (5m, 15m, 1h, 4h, 1d, 1w). Each request is deliberately kept below the API's 2,000-candle response cap.
- These are traded-price candles for the configured Delta contracts, not Yahoo proxies or an unrelated spot/futures feed.

## Required GitHub settings

Add repository secrets:
- OPENAI_API_KEY
- DISCORD_TRIGGER_WEBHOOK (or DISCORD_WEBHOOK)

Optional repository variable:
- OPENAI_MODEL (defaults to gpt-6.1-terra)

The default model is selected for visual reasoning and frequent chart analysis. Model and reasoning effort can be changed without changing strategy logic.

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

## Data persistence and rollout

- market_data/ and research/ are carried between GitHub Actions runs through Actions cache. This is a rolling development store, not a permanent database. Cache eviction or workflow inactivity can remove it; a durable database/object store is a later production task.
- Scheduled GitHub Actions workflows run from the repository's default branch. This development branch will not run on its five-minute schedule until the workflow is merged to the default branch. It can be tested manually where workflow dispatch is available.
- GitHub's schedule is best-effort and may be delayed. The pipeline deduplicates by closed 5m candle, so delayed invocations do not create repeated analyses.
- No strategy hit rate or backtest performance is claimed. First collect and label AI decisions, then build a replay/evaluation harness from preserved charts, candle data, prompts and outcomes.

## Local validation

    pip install -r requirements.txt
    python test_visual_pipeline.py

The tests are offline and do not call the OpenAI API.

## Legacy modules

zones.py, score.py, news.py, replay.py and the original test_synthetic.py remain in the repository for reference. The new main.py does not import the old zone finder, old confluence scorer, or old WATCH/TRIGGER pipeline.
