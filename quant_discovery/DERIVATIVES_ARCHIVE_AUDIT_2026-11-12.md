# BTC/ETH derivatives archive audit — 2026-11-12

## Provenance and verification

- Source workflow: [run 43118448037](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43118448037), artifact ID `13898484807`, artifact name `salty-quant-derivatives-2y-btc-eth-43118448037`.
- Requested window: 2024-11-11 11:16:03 UTC through 2026-11-11 23:16:03 UTC (exclusive).
- The workflow's download step completed and uploaded all six CSVs plus `manifest.json` and `coverage.csv`. The job failed only in the final manifest verifier because the expected-key comprehension referenced an undefined `details` variable (`NameError`). No download error occurred.
- The verifier was corrected in commit [83600a2](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/commit/83600a2a731b9e3bf96f84b15f412a989a325cc8), but the queued retry was cancelled by later branch concurrency. The artifact was therefore independently audited offline rather than claiming the workflow itself passed.
- Artifact ZIP SHA-256 independently recomputed and matched GitHub's digest: `65285eda876836c5372f5860014c029e7e0830af0238ef6b06e8dc36e2c4079f`.
- All six expected dataset keys are present. Every CSV row count matches its manifest count and every CSV SHA-256 matches its manifest value. Total: **490,818 candles**. No rows were fabricated, no gaps were filled, and raw funding values were not scaled.

## Dataset coverage

| Dataset | Rows | First candle UTC | Last candle open UTC | Requested coverage estimate | Observed coverage | Gaps | Largest gap |
|---|---:|---|---|---:|---:|---:|---:|
| BTC funding 1h | 17,495 | 2024-11-11 16:00 | 2026-11-11 22:00 | 99.7890% | 99.8174% | 8 | 5h |
| BTC mark 5m | 210,383 | 2024-11-11 11:20 | 2026-11-11 23:10 | 99.9995% | 100% | 0 | — |
| BTC OI 1h | 17,531 | 2024-11-11 12:00 | 2026-11-11 22:00 | 99.9943% | 100% | 0 | — |
| ETH funding 1h | 17,495 | 2024-11-11 16:00 | 2026-11-11 22:00 | 99.7890% | 99.8174% | 8 | 5h |
| ETH mark 5m | 210,383 | 2024-11-11 11:20 | 2026-11-11 23:10 | 99.9995% | 100% | 0 | — |
| ETH OI 1h | 17,531 | 2024-11-11 12:00 | 2026-11-11 22:00 | 99.9943% | 100% | 0 | — |

The funding gaps account for 32 missing hourly observations per contract. They must remain missing; any position replay must not interpolate them. Mark and OI streams have no internal timestamp gaps in the observed spans.

## Dataset hashes

| Dataset | SHA-256 |
|---|---|
| BTC funding 1h | `5348f3da6e86bd1f0f12293bc86f9d2bfa8b9bd28c8b6099e73c8fa9568154d7` |
| BTC mark 5m | `aa959fda51a577c88611b40e790170547ac50e09ab421ab550f8d21d3793e7b3` |
| BTC OI 1h | `ae6b8ba594a9fd27fa1139601396aac2b4cf62f72b4679f5f7fea4394a215758` |
| ETH funding 1h | `f048d6fb6440429eb94c993072a5826cc13e148a4d96beb5a4db91a1ec9ac143` |
| ETH mark 5m | `8cc2d5d0caa713774932d957dfa7897a1791914df635dbbb76d8f5fe780c38ff` |
| ETH OI 1h | `7c8fe703afb875ec1c229283f532012c97cfcd7f435ab21dce90f1b08ace92f8` |

## Funding-series diagnostics

The raw 1h `FUNDING:` candles are repeated hourly values, not hourly cashflows:

- BTC: 17,495 rows; 1,432 negative closes; min -0.08008859, median 0.01, max +0.07886045.
- ETH: 17,495 rows; 1,636 negative closes; min -0.02503412, median 0.01, max +0.05759389.
- BTC value changes occur at 00:00, 08:00 or 16:00 UTC throughout this sample.
- ETH value changes occur at those same boundaries except one isolated 2024-11-29 09:00 UTC observation.
- After 2025-09-08, the observed BTC and ETH change points align with 00:00/08:00/16:00 UTC. This matches Delta's current documented 8-hour funding schedule.

Delta's current guide explicitly says the 8-hour method became effective at 5:30pm IST on 2025-09-08; before that it used minute-by-minute funding exchanges. Treat pre-2025-09-08 funding as a separate methodology regime and exclude it from any current 8-hour event replay. The post-change cadence matches the documented 00:00/08:00/16:00 UTC schedule, but this is still a cadence/shape observation, not proof of the historical candle-to-realization mapping. Do not sum repeated hourly values. Do not apply funding to a trade until an event-level settlement cross-check and event-time position exposure are implemented.

## Current public contract/cost context

On 2026-11-12, public BTCUSD product metadata reported:

- `rate_exchange_interval=28800` and `expiry_interval=28800` (8 hours).
- Taker commission `0.0005` (5bp per side) and maker commission `0.0002` (2bp per side).
- Contract value `0.001 BTC`; tick size `0.5 USD`; funding method `mark_price`.

Delta's current perpetual guide says funding snapshots are taken at 05:30, 13:30 and 21:30 IST (00:00, 08:00 and 16:00 UTC); positions must be open at the snapshot to pay/receive. Positive funding means longs pay shorts; negative funding means shorts pay longs. The guide gives the payment as current position value multiplied by the rate and illustrates 0.01% per 8h. It also notes that some contracts can have 4/2/1-hour intervals, so BTC's metadata must not be copied to ETH/XAUT without checking their product specs.

The public taker/taker BTC fee implies 10bp round trip before slippage. The research baseline of 12bp can be interpreted as 10bp taker fees plus a 2bp spread/slippage stress. This is not the user's verified account/VIP fee tier. Limit-entry/market-stop strategies should eventually use side-specific maker/taker costs.

## Research decision and next checks

- The archive is usable for **lagged OI features** after applying gap masks and verifying the exact OI candle timestamp semantics. OI must be known only after its candle closes.
- Mark prices are retained separately for valuation/liquidation diagnostics; they are not executable traded-price fills.
- Funding is **not yet enabled for P&L attribution**. Confirm ETH product interval; cross-check at least one historical BTC/ETH funding event against an actual realized settlement record or an exchange-provided event history; then add event-time unit/sign/gap regression tests.
- Keep funding and OI as separate inputs. Do not assume the 1h funding series represents an hourly charge; it appears to carry an 8-hour rate repeated across hourly candles.
- No strategy was run or promoted as part of this data audit. No production rules, alerts or live trading changed.

## Official references

- [BTCUSD product metadata](https://api.india.delta.exchange/v2/products/BTCUSD)
- [Delta perpetual funding guide](https://guides.delta.exchange/delta-exchange-india-user-guide/derivatives-guide/docs)
- [Delta historical candles API](https://docs.delta.exchange/)
