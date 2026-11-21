# BTCUSDT September 2026 true trade-level footprint feature build — preregistration

**Frozen:** 2026-11-18 UTC  
**Branch:** `ai-quant-rebuild`  
**Input:** the exact Binance USD-M BTCUSDT September 2026 aggTrades and 5m kline archives that passed the prior data-integrity pilot.  
**Purpose:** deterministic feature reconstruction and data-quality validation only; no trading signal or strategy PnL is tested.

## Frozen definitions

- Use each aggTrade's exact recorded price and base quantity; do not spread candle volume over a candle high-low range.
- Binance buyer-maker=true means the buyer is maker and the seller is taker: classify quantity as aggressive sell. buyer-maker=false means aggressive buy.
- Use UTC 5-minute bar open time: floor aggregate-trade timestamp to a 300,000 ms boundary.
- A price level is the exact aggTrade price value. Do not round prices to a coarser grid or infer diagonal imbalance without a separately verified historical tick size.
- For each (5m bar, price) pair, calculate total quantity, taker-buy quantity, taker-sell quantity, signed delta (buy minus sell), aggregate-trade record count and share of that bar's total volume.
- Build 30-minute TPO occupancy: for each UTC day and exact price, count the number of distinct 30-minute periods in which at least one aggTrade occurred at that price. This is explicitly 30m time-at-price occupancy, not a claim about exchange order-book depth.
- Build prior-day-usable daily profiles by exact price: sum volume, taker buy, taker sell and delta across all trades in the UTC day; count 30m TPO periods at each price.
- Calculate daily volume POC and 70% value area (VAH/VAL) by starting at the highest-volume price and expanding to the adjacent price level with greater volume until >=70% of daily volume is included. If adjacent volumes tie, choose the lower price first. Apply the same rule to the 30m TPO count profile.
- Daily profile outputs are timestamped at the UTC day they describe; a later strategy must shift them to the next day before using them as prior-day context.

## Required validation

1. Re-download the exact monthly aggTrades and 5m kline ZIPs and verify official SHA-256 CHECKSUMs and ZIP CRCs.
2. Verify aggregate IDs strictly increase, timestamps are non-decreasing and within September, prices/quantities are finite and positive, underlying trade ID ranges are ordered, and buyer-maker is boolean.
3. Reconcile 5m total volume and taker-buy volume to the official klines within the previously frozen 0.10% aggregate tolerance and retain per-bar errors.
4. Build 5m price-level rows and require no duplicate (bar, price) keys after final aggregation.
5. Require the sum of price-level total/buy/sell quantities per 5m bar to match the aggTrade 5m totals within 1e-10 relative error; delta must equal buy minus sell.
6. Require every TPO count to be an integer from 1 to 48 for September (48 half-hour periods/day); daily volume and TPO profiles must have 30 UTC days.
7. Recalculate daily volume and TPO POC/VAH/VAL from the persisted per-price table and verify the value-area cumulative share is >=70% and <100% unless one price level alone accounts for >=70%.
8. Retain raw ZIPs and CHECKSUMs, 5m price-level data, daily volume/TPO per-price profiles, daily profile summary, bar-level delta summary, metadata and a Markdown report as the Actions artifact. Do not commit raw or derived market data to Git.

## Interpretation and limitations

- This is exact trade-price/aggressor-side aggregation of Binance aggTrades. It is a genuine trade-level volume-at-price/delta dataset, unlike the previous OHLCV candle-volume allocation proxy.
- aggTrades are already Binance's aggregate-trade records, not every individual fill and not order-book queue/depth. The buyer-maker flag gives taker side, not passive queue position.
- One month is only a feature-pipeline pilot. It is not enough for strategy inference, parameter selection, validation or OOS.
- No strategy, entry, stop, target, cost, funding, slippage or PnL is evaluated.
- No coarser tick-size imbalances are calculated until the historical tick size is independently verified.
- If any validation fails, preserve the artifact and do not use the features for strategy research.

## Next step

Only after this build passes, preregister a multi-month BTC/ETH true-footprint event study using prior-day VP/TPO and price-level delta features. Keep the final chronological holdout untouched and compare against the failed candle-proxy baseline without reusing its validation as a new OOS period.