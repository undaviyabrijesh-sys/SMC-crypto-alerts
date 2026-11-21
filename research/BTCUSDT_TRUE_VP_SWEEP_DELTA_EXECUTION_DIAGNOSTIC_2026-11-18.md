# BTCUSDT true VP edge-sweep + delta execution diagnostic — 18 November 2026

## Decision

**No edge established; exploratory only.** This is a post-hoc one-month execution diagnostic on September 2026 data already inspected in the parent true-footprint feature study. It is not a preregistered validation, not a multi-month backtest, and not eligible for promotion.

## Data provenance

- Market: Binance USD-M BTCUSDT perpetual.
- Period: 2026-09-01 00:00 UTC to 2026-10-01 00:00 UTC.
- Parent aggTrades pilot: [workflow 44295373196](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44295373196), [artifact 14422264499](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44295373196/artifacts/14422264499).
- Parent exact-price feature build: [workflow 44296515366](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44296515366), [artifact 14423707445](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44296515366/artifacts/14423707445).
- Derived-only repackage: [workflow 44296995345](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44296995345), [artifact 14423941566](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44296995345/artifacts/14423941566).
- Official aggTrades ZIP SHA-256: `252e92894886c2f752744656e4f1d7a278a75e1456aa32442451b07ee9703b80`.
- Matching official 5m kline ZIP SHA-256: `3a2d163a2bd28ca614fa0840a92ecbcde0d9c4962b278dd619d5bf81a9918e26`.
- 36,036,629 aggTrade records, 8,640 5m bars, 8,510,392 exact-price 5m price-level rows and 30 daily profiles in the parent feature build.

## Frozen-for-this-diagnostic rules

These rules were written after the September feature outputs had already been inspected; they are therefore not a preregistration.

- Use the previous completed UTC day's exact-trade-price 70% volume VAH/VAL/POC.
- Short: signal 5m high exceeds prior VAH by more than one 0.1 USDT tick, closes back below VAH, and close location is at or below 0.25.
- Long: signal 5m low breaches prior VAL by more than one tick, closes back above VAL, and close location is at or above 0.75.
- Delta-confirmed ablation: same price rule plus short delta-z <= -1.5 or long delta-z >= +1.5. Delta-z uses the preceding 288 completed 5m bars, minimum 96 observations, shifted one bar.
- Signal is known at 5m close; entry is next 5m open.
- Stop is beyond the signal extreme by 0.1 x Wilder ATR(14). Target is the previous day's true volume POC; skip if target distance is below 1R.
- One position at a time, 48-bar cooldown, maximum 48 bars.
- Exit at the last 5m close strictly before the next 00:00/08:00/16:00 UTC funding boundary. Funding cashflow is not applied.
- Same-bar stop/target ambiguity resolves stop-first; adverse gap-through stop fills at the open.
- Signal bar must reconcile within 0.1% for both total volume and taker-buy volume against the official 5m kline.
- Round-trip cost sensitivities: 0, 4, 7, 10 and 20 bps.

## Results

Primary assumed cost: 10 bps round trip.

| Variant | Trades | Win rate | PF | Net R | Avg R | Max DD | Max losing streak | Positive days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Price-only VA sweep/reclaim | 42 | 26.19% | 0.374 | -31.348R | -0.746R | -33.291R | 8 | 6/21 |
| VA sweep/reclaim + delta-z | 20 | 25.00% | 0.440 | -13.989R | -0.699R | -18.237R | 10 | 3/15 |

| Round-trip cost | Price-only net R | Delta-confirmed net R |
|---:|---:|---:|
| 0 bps | +0.952R | +0.637R |
| 4 bps | -11.968R | -5.213R |
| 7 bps | -21.658R | -9.601R |
| 10 bps | -31.348R | -13.989R |
| 20 bps | -63.648R | -28.614R |

At 10 bps, the price-only variant had 7 TP, 27 SL and 8 time exits; the delta-confirmed variant had 3 TP, 14 SL and 3 time exits. The POC target averaged approximately 3.5–4.5R, but stop-outs dominated. Both variants were only marginally positive before costs and clearly negative from 4 bps upward.

## 5m reconciliation forensic audit

Monthly totals match exactly, but per-bar values do not always align:

- 8,521 / 8,640 bars (98.62%) passed the <=0.1% relative-error gate for both total volume and taker-buy volume; 119 bars were excluded from signal generation.
- Total-volume mismatch: 983 bars; 417 adjacent offset pairs covered 832 of those mismatched bars (84.64%).
- Taker-buy mismatch: 489 bars; 222 adjacent offset pairs covered 444 mismatched bars (90.80%).
- Signed differences sum to zero at monthly level; the observed adjacent differences are consistent with quantity being assigned to a neighboring 5m bucket.
- Maximum per-bar relative error in the parent artifact was 2.644% for total volume and 7.939% for taker-buy volume.

Binance documents USD-M aggregate-trade streams as aggregating fills at the same price and taking side every 100 milliseconds. This is consistent with, but does not prove, the observed adjacent 5m bucket offsets; the precise cause needs a raw-trade/underlying-ID boundary audit. Reference: https://developers.binance.info/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream

## Interpretation and limitations

1. The one-month true-footprint feature reconstruction passed integrity/profile checks, but that is a data-engineering result, not evidence of an edge.
2. The event-study parent result was also exploratory: absorption had only six events per side; continuation was weak/near-flat after costs.
3. This execution diagnostic uses one month, one asset, low trade counts, and data already inspected. It has no independent development/validation/OOS split and no monthly stability estimate.
4. Funding is avoided by forced exits, not modeled as cashflow. Separate spread, slippage, market impact and user-specific fee tiers are not included.
5. Per-bar aggTrade-to-kline alignment is imperfect. The 0.1% quality gate is conservative but does not correct the source timestamps.

## Decision and next step

- Do not promote either variant; do not tune the thresholds or targets on September.
- Before a multi-month signal study, audit raw trades around several adjacent-bucket mismatch pairs using aggTrade first/last trade IDs and the corresponding raw-trade timestamps.
- Then acquire additional chronological BTC months and matching klines, retain checksums, and apply the same frozen rules. Keep October 2026-10-28 excluded unless its missing aggTrades archive is repaired or independently reconstructed. Only then consider ETH replication.
- No production, main-branch, live-alert or exchange-order changes.
