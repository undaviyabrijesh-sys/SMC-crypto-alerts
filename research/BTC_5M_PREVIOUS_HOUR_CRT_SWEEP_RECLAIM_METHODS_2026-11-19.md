# BTC 5m previous-hour CRT-style sweep/reclaim — methods

**Study date:** 2026-11-19. **Status:** completed exploratory diagnostic; no promotion. This is a mechanical CRT-style prior-hour range sweep/reclaim definition, not a claim that all discretionary CRT implementations are equivalent.

## Data

- Delta BTCUSD 5-minute OHLCV archive; 210,239 rows.
- 2024-11-16 11:30 UTC through 2026-11-16 11:20 UTC.
- Zero missing 5-minute intervals; zero invalid OHLC rows.
- SHA-256: 5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb.

## Signal and reference

- Aggregate into UTC-aligned hourly candles; only hours with all 12 expected 5-minute bars are eligible.
- For a signal bar in hour H, use the immediately preceding completed hour H-1.
- Short: 5-minute high exceeds prior-hour high by more than 0.1; close returns below prior-hour high but remains above prior-hour low; close location is at or below 0.25 or 0.40.
- Long: exact inverse; close location is at or above 0.75 or 0.60.
- Discard a candle sweeping both sides.

## Entry, risk and exits

- Immediate variant: next 5-minute open.
- Confirmation variant: next bar must break the sweep candle's low (short) or high (long), without taking the opposite sweep extreme; enter at the following open.
- Wilder ATR(14), seeded with first 14 true-range observations.
- Stop beyond sweep extreme by 0.1 × ATR(14).
- Target: opposite prior-hour range boundary (only if at least 1R away) or fixed 2R.
- Maximum hold 12 five-minute bars; 12-bar cooldown after exit; one position per configuration.
- Same-bar stop/target resolves stop-first; adverse stop gaps fill at bar open; favorable target gaps are capped at target.
- Flatten at close of the 5-minute candle ending 00:00, 08:00 or 16:00 UTC. Funding cashflow itself is not modeled.

## Configurations and costs

Eight configurations: close-location threshold 0.25/0.40 × immediate/next-bar-break confirmation × prior-hour opposite boundary/2R target. Costs: 0, 4, 7, 10 and 20 bps round trip. Primary decision cost: 10 bps.

## Chronological partitions

By source row index, without shuffling:
- Development: [0, 147167); 2024-11-16 11:30 through 2026-04-11 11:20 UTC.
- Validation: [147167, 178703); 2026-04-11 11:25 through 2026-07-29 23:20 UTC.
- OOS: [178703, 210239); begins 2026-07-29 23:25 UTC.

OOS was not evaluated because no configuration passed the development/validation gate.

## Promotion gate

At 10 bps, an exact configuration needed at least 100 development and 30 validation trades, PF >1.10 and net R >0 in both partitions, and at least 55% positive active months in both. No configuration passed.

## Limitations

One BTC instrument/source; no ETH replication; no actual spread or market-impact simulation; no funding cashflow (positions are flattened before funding boundaries); OHLC intrabar path unavailable, so same-bar ambiguity resolves stop-first.
