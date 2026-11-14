# Delta OI unit and aggregation reconciliation — 2026-11-12

**Status:** Data mapping clarified; raw Delta OI remains a venue-specific feature, not a validated trading signal.

## Verified live field mapping

The audit used public Delta ticker, product metadata, and OI-prefixed 5m/1h candles for BTCUSD and ETHUSD.

| Field | BTCUSD | ETHUSD |
|---|---:|---:|
| Ticker oi | 1,058.938 | 19,683.22 |
| Ticker oi_value | 1,058.938 BTC | 19,683.22 ETH |
| Ticker oi_value_usd | $78,068,666 | $40,556,038 |
| Product contract_value | 0.001 BTC | 0.01 ETH |
| oi × contract_value / oi_value | 0.001 | 0.010 |
| Implied contract count from oi_value / contract_value | 1,058,938 | 1,968,322 |
| USD/base implied price vs mark | +0.0489% | +0.0464% |

The ticker's oi and oi_value are numerically identical, but product contract_value shows that oi is not the raw contract count. The generic docs description of oi as a contract count conflicts with the live payload. The historical OI candle series is aligned to base-asset OI (oi_value), not USD notional.

Ticker timestamps were returned in microseconds. The audit now normalizes timestamp units and uses the HTTP Date header; both snapshots were fresh.

## 5m-to-1h historical aggregation

Four historical windows were checked for each asset, with two complete hours per window:

- 2025-12-21 09:00 UTC
- 2026-08-19 15:00 UTC
- 2026-10-29 14:00 UTC
- 2026-11-08 21:00 UTC

All 16 complete hourly OHLC bars (8 BTC, 8 ETH) matched the aggregation of twelve 5m OI OHLC bars exactly. The extreme hourly moves are therefore present in the underlying 5m data; they are not an hourly resampling error.

Examples from BTC:
- 2025-12-21 09:00: +114.86%, followed by -52.03% in the next hour.
- 2026-08-19 15:00: -38.76%.
- 2026-10-29 14:00: -20.14%, followed by -14.74%.
- 2026-11-08 21:00: -33.86%.

## Cross-venue context

In the latest 500-hour Binance USDⓈ-M sample, BTCUSDT and ETHUSDT had zero hourly OI changes above 5%. For example, at 2026-11-08 21:00 UTC, Delta BTC OI fell 33.86%, while Binance BTC OI fell 0.109% and Binance ETH OI fell 0.001%.

This points to Delta-specific activity or Delta-feed/accounting behaviour, not a market-wide crowding event. It does not prove the Delta observations are false.

## Decision

- Treat Delta historical OI candles as base-asset OI aligned to oi_value.
- Do not treat ticker oi as raw contract count.
- Keep oi_value_usd separate as USD notional.
- Do not use raw Delta OI jumps as a market-wide BTC/ETH crowding signal.
- The prior OI-contraction strategy remains rejected. No OOS or trading performance is inferred from this data audit.

## Next experiment

Build a bounded 5m base-OI event dataset for BTCUSD and ETHUSD around large Delta-specific contractions/expansions. Pair each event with same-time Delta traded-price OHLC and Binance OI/price controls. Run a descriptive event study first; only build a trading backtest if the venue-specific events are reproducible and causal.

## Reproducibility

- Code: [oi_semantics_reconciliation.py](../research/oi_semantics_reconciliation.py)
- Research ledger: [RESEARCH_LEDGER.md](../research/RESEARCH_LEDGER.md)
- Successful CI/live audit: [run 43180579326](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43180579326)
- Artifact: [13926042971](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43180579326/artifacts/13926042971)

The run's 14 deterministic OI semantics tests, repository-wide compilation, live Delta audit, and existing CI test suite all passed. No live orders, execution alerts, or production strategy changes.


## Repeat snapshot and 1h OI event study

A second live audit at 2026-11-12 08:11:58 UTC reproduced the same field mapping. Ticker ages were 1.6s (BTC) and 1.0s (ETH); 5m/1h candle closes remained within 0.29%–0.88% of base OI, and 12/12 recent hourly closes again matched the final 5m close. The product conversion ratios remained 0.001 BTC and 0.01 ETH, confirming the same live field discrepancy in a second snapshot.

A separate descriptive event study used 17,531 hourly Delta BTC OI candles and 70,079 BTC 15m traded-price candles. Events were absolute OI close changes of at least 10%, separated by an 8-hour cooldown, with chronological 70/15/15 splits.

| Event | Split | Events | Mean 8h BTC return | Median 8h return | Positive |
|---|---|---:|---:|---:|---:|
| OI contraction | Train | 462 | +0.081% | +0.118% | 54.3% |
| OI contraction | Validation | 71 | +0.226% | +0.168% | 53.5% |
| OI contraction | OOS | 41 | +0.023% | -0.117% | 43.9% |
| OI expansion | Train | 411 | -0.038% | +0.034% | 50.9% |
| OI expansion | Validation | 40 | -0.046% | +0.013% | 50.0% |
| OI expansion | OOS | 23 | +0.110% | +0.048% | 52.2% |

A price-only matched control used the event-hour direction and training-defined quintiles of absolute price return and price range. At 8h, contraction events exceeded their matched control by +0.058% train and +0.288% validation, but underperformed by -0.095% OOS. Expansion differences were -0.036%, +0.002%, and +0.039% respectively. This does not establish a stable incremental edge.

**Decision:** keep OI contraction/expansion rejected as a trading hypothesis. The next step is a bounded 5m base-OI event dataset with same-time Delta price and Binance controls, not a parameter search or live signal.
