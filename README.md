# advance_alerts

Two-stage Discord alerts for BTC, ETH and XAUUSD (no LLM or API key needed).

- **WATCH**: price is approaching a zone and the confluence score is high enough. Not an entry.
- **TRIGGER**: price entered the zone and a 15m candle closed back beyond it. Final entry, SL, TP.
- **CANCEL**: zone broken, R:R gone, or the watch expired.

## How zones are found (market structure, no trend filter)
1. An ATR zigzag on 1h candles marks real swing tips. A tip only counts after price moved 2 ATR away from it,
   so minor swings never create zones.
2. Demand = the lowest candle at the origin of an up-leg whose impulse leaves a fair value gap (FVG) within
   3 candles. Supply is the mirror at swing highs. Zone box = that tip candle's high to low.
3. Strength = how far the leg went in ATR (more impulse = stronger zone), plus FVG size.
4. **A zone stays tradable until a body close breaks it.** Retests do not use it up, and a zone from a week ago
   works as long as it has not broken (zones up to 14 days old are scanned, `ZONE_MAX_AGE_BARS`). Each retest's
   reaction (how far price moved away, in ATR) is measured, and bigger reactions add to the score.
   The same zone can alert again after a WATCH closes, but only once price has moved 1.5 ATR away and come back
   (`REARM_ATR`), so you don't get repeat alerts while price sits at the zone.
5. **Role reversal**: a body close through a zone with 1.5+ ATR follow-through flips it (broken support becomes
   resistance and the reverse). Its first retest from the other side is tradable like any zone.
6. Buy at support, sell at resistance regardless of bias. There is no trend gate.
7. TP = nearest opposing zone edge or unswept swing tip (liquidity). SL = beyond the tip + 0.25 ATR.

## Setup
1. Put all these files at the top level of your repo, then create `.github/workflows/alerts.yml` from `alerts.yml`.
2. Create two Discord webhooks and add repo secrets `DISCORD_WATCH_WEBHOOK` and `DISCORD_TRIGGER_WEBHOOK`.
   (A single `DISCORD_WEBHOOK` also works.)
3. Optional Kronos hook: have your Kronos job write `kronos_bias.json` in the repo root:
   `{"BTC": "up", "ETH": "down", "XAU": "flat"}`. When a bias exists it is a hard filter (flat or opposite = skip).
   With no bias file the filter is not applied and the WATCH message says so.
4. Try it: `pip install -r requirements.txt && DRY_RUN=1 python main.py`
5. Offline logic tests: `python test_synthetic.py`

## See how often it fires (needs internet)
`python replay.py --days 50` replays the last ~50 days and prints WATCH/TRIGGER counts, trades per
day, win rate and average R per symbol. Past news, calendar blackouts and Kronos forecasts are not replayed, so
live counts will be lower. Same-candle SL/TP hits count as losses.

## Score and gates
- Gates: Kronos agreement (when available), min R:R 2.5 at WATCH and 2.0 at TRIGGER, high-impact USD event
  blackout (60 min before, 30 after), one active watch per symbol, gold skipped when its market is closed.
- Score (0-100, threshold 60): impulse strength, FVG size, swing-tip zone, distance, R:R, past retest reaction, plus Kronos,
  funding (crypto) and headline sentiment. All settings are in `config.py`.

## Known limits
- Cron runs are delayed or skipped sometimes, so this suits 1h zones with 15m confirmation, not 3m scalping.
- Headline sentiment is a crude keyword count and only a mild nudge.
- Repeated retests of one zone can weaken it in practice. There is no cap yet; use the replay to see if one is needed.
- Yahoo, the calendar feed, Google News RSS and OKX funding could not be tested from the build sandbox. If one
  fails the run logs a warning and continues.
- Every alert is logged in `state.json`. Check the real hit rate per symbol before trusting the thresholds.

## Where is the workflow file?
`.github/workflows/alerts.yml` is in a hidden folder (names starting with a dot are hidden on phones and some
file managers). A visible copy is in `github_workflow/alerts.yml`. In GitHub, create the file at the path
`.github/workflows/alerts.yml` (use "Add file > Create new file" and type that path) and paste it in.


## Triggered signal lifecycle

A WATCH remains a candidate and is not counted as a trade. When the 15m rejection
confirmation creates a TRIGGER, the bot assigns a unique Signal ID and stores an
OPEN paper position with its actual entry, stop, target and trigger-candle timestamp.
On later runs, candles strictly after that trigger candle are checked for TP/SL.
A gap through a level is filled at the candle open; if both TP and SL are inside one
candle range, SL is conservatively assumed first. The first confirmed outcome sends
a separate Discord closure message and is saved to trade_history. If neither level
is reached within TRADE_MAX_HOURS (default 48), the position is closed as TIME
using the latest available close. New WATCH signals for a symbol are held while it
has an open triggered position. State is persisted through the existing GitHub
Actions cache. This is paper tracking only; it does not place exchange orders.
