# Salty Trades — SMC alert engine

Two-stage Discord alerts for BTC, ETH and a COMEX gold-futures proxy (GC=F).
- WATCH: price approaches a higher-timeframe zone; not an entry.
- TRIGGER: closed 15m rejection with executable entry, SL and TP.
- CANCEL: zone invalidated, stale setup, excessive entry drift, or poor confirmed R:R.
- Closure update: paper-tracked TP / SL / TIME outcome.

## Signal process
1. 1h ATR zigzag identifies confirmed swing tips.
2. Zones require an impulsive departure with an FVG.
3. Body-close breaks invalidate zones; strong displacement can flip zone role.
4. Retests are counted and capped.
5. Targets use opposing zones or unswept swing liquidity; planned R:R must meet its floor.
6. 1h EMA20/EMA50 alignment and EMA50 slope gate direction. Neutral and countertrend setups are skipped.
7. 15m close back outside the zone confirms rejection. Stop distance, entry drift and confirmed R:R are checked before TRIGGER.
8. Kronos is an optional hard directional veto. News and funding are low-weight context.
9. One active watch or paper position per symbol.

The 0–100 score is a heuristic ranking, not a win probability.

## Research caveats
- Settings are not statistically calibrated. Compare replay with the previous version before claiming improvement.
- Yahoo OHLC can be delayed, incomplete or stale. GC=F is COMEX futures, not spot XAUUSD.
- GitHub scheduled workflows can be delayed; this is not designed for scalping.
- Paper tracking does not execute exchange orders.
- Actions cache persistence is best-effort and may lose state on eviction; use a persistent database before relying on lifecycle tracking.

## Run
Set Discord secrets `DISCORD_WATCH_WEBHOOK`, `DISCORD_TRIGGER_WEBHOOK` (or `DISCORD_WEBHOOK`). Optional Kronos JSON:
`{"BTC":"up","ETH":"down","XAU":"flat"}`.

Install: `pip install -r requirements.txt`
Dry run: `DRY_RUN=1 python main.py`
Tests: `python test_synthetic.py && python test_quality.py`
Replay: `python replay.py --days 50 --cost-bps 5`
