# BTCUSDT aggTrade 5m-boundary forensic results — 2026-11-18

## Scope and status

This is a post-hoc data-quality forensic audit, not a strategy backtest. It compares official Binance USD-M raw trades, aggTrades and 5m klines on one stress day (2026-09-03) and one selected low-mismatch control day (2026-09-12). Both dates were selected after inspecting the September monthly reconciliation; neither is independent validation or OOS evidence.

The frozen preregistrations are:
- `research/BINANCE_AGGTRADE_BOUNDARY_FORENSICS_PREREGISTRATION_2026-11-18.md`
- `research/BINANCE_AGGTRADE_BOUNDARY_CONTROL_PREREGISTRATION_2026-09-12.md`

## Results

| Metric | Stress: 2026-09-03 | Low-mismatch control: 2026-09-12 |
|---|---:|---:|
| Raw trade rows | 4,931,524 | 791,576 |
| aggTrade rows | 1,806,935 | 296,171 |
| Complete aggTrade ID ranges | 1,806,934 | 296,171 |
| Incomplete day-edge aggTrade ranges | 1 | 0 |
| Raw trades unmatched to complete aggTrade ranges | 1 | 0 |
| aggTrade groups crossing a 5m boundary | 30 | 3 |
| Total quantity in crossing groups | 18.560 BTC | 0.072 BTC |
| Raw quantity shifted from later bucket to aggTrade timestamp bucket | 15.518 BTC | 0.042 BTC |
| Crossing groups where aggTrade timestamp equals first raw trade timestamp | 30/30 | 3/3 |
| Crossing group duration | 2–100 ms | 61–86 ms |
| Complete groups matching raw quantity, price and buyer-maker side | 1,806,934/1,806,934 | 296,171/296,171 |
| Raw 5m volume / taker-buy / trade-count bars matching klines | 288/288 / 288/288 / 288/288 | 288/288 / 288/288 / 288/288 |
| aggTrade-timestamp volume bars matching klines | 235/288 | 282/288 |
| aggTrade-timestamp max relative volume error | 2.6441% | 0.02202% |
| aggTrade-timestamp max relative taker-buy error | 7.9392% | 0.03617% |
| Max absolute error: complete raw members reassigned to aggTrade timestamp vs complete aggTrade buckets (volume) | 6.68e-9 BTC | 6.14e-11 BTC |
| Same reassignment error (taker-buy) | 1.84e-9 BTC | 1.86e-11 BTC |

### Stress-day example

One crossing group contained 8.618 BTC over 44 ms:
- First raw trade: 2026-09-03 10:34:59.960 UTC
- Last raw trade: 2026-09-03 10:35:00.004 UTC
- aggTrade timestamp: 10:34:59.960 UTC (the first raw trade)
- Of the group quantity, 8.613 BTC belonged to the 10:35 bar by raw execution timestamp but was assigned to the 10:30 bucket by the aggTrade timestamp.

The resulting bucket offsets were:
- 10:30 UTC: aggTrade volume +8.613 BTC versus kline/raw trades.
- 10:35 UTC: aggTrade volume -8.613 BTC versus kline/raw trades.

### Low-mismatch control

The control day had only three boundary-crossing groups. All three were timestamped at their first underlying raw trade; the group durations were 61–86 ms. Their later-bucket quantity was shifted into the earlier aggTrade timestamp bucket. This reproduces the same mechanism on a day with much smaller observed per-bar errors.

## Interpretation

The forensic explanation is supported on both selected days:

1. Individual raw-trade timestamp buckets reconcile to official 5m klines for total base volume, taker-buy base volume and trade count.
2. Complete aggTrade first/last ID ranges match the underlying raw quantity, price and buyer-maker side.
3. For every observed group crossing a 5m boundary, the aggTrade timestamp equals the first underlying raw trade timestamp.
4. Reassigning the underlying raw trade rows to their aggTrade timestamp bucket reproduces the complete aggTrade bucket totals to floating-point tolerance.

Therefore, the per-bar mismatch is caused by the 100ms aggTrade grouping timestamp assignment when a group spans a 5m boundary. It is not a missing-volume problem: monthly/daily totals can reconcile while individual 5m bars are shifted.

This is consistent with Binance's official USD-M aggTrade description: fills at the same price and taking side are aggregated in 100ms intervals. The timestamp is a single group timestamp, not a set of per-fill timestamps.

## Consequence for the prior September VP sweep + delta diagnostic

The V1 delta-confirmed results are not reliable as a final test because:
- The 5m delta series was assigned by aggTrade timestamp rather than each underlying raw trade timestamp.
- The 0.1% signal-bar quality filter did not fix the rolling delta z-score history; preceding 288 bars could still contain shifted buckets.
- The filter excluded 119 of 8,640 bars and could change which price-action signals were eligible.

The prior price-only variant does not use 5m delta, but its signal-bar quality filter also excluded bars. Its daily profile levels were less exposed to within-day 5m bucket offsets, although a UTC-midnight group can still affect day assignment.

## Decision

- Confirm the aggTrade 5m boundary-alignment problem for the two audited dates.
- Do not use the V1 aggTrade-timestamped 5m delta as a trusted signal feature.
- Rebuild the September diagnostic using individual raw trade timestamps for both 5m delta and prior-day exact-price VP/TPO.
- Keep the September replay post-hoc and exploratory; do not promote or optimize it.
- The next confirmatory study must use additional chronological months with a frozen final holdout.

## Reproduction

- Stress workflow: [44335727144](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44335727144)
- Control workflow: [44336111703](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44336111703)
- Implementation: `research/binance_aggtrade_boundary_forensics.py`
- Stress preregistration and control preregistration are stored in `research/`.
- Artifacts contain compact reports, metadata, 288-row bucket reconciliations and all crossing-group records; raw archives were removed after checksum verification.
