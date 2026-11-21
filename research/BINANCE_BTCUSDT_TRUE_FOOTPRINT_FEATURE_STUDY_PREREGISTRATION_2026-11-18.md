# BTCUSDT true footprint feature pilot — frozen specification

Date: 2026-11-18 UTC  
Branch: ai-quant-rebuild  
Status: exploratory data/feature study only; not a strategy validation or promotion test.

## Data
- Binance USD-M BTCUSDT September 2026 official monthly aggTrades ZIP.
- Source archive SHA-256: 252e92894886c2f752744656e4f1d7a278a75e1456aa32442451b07ee9703b80.
- 36,036,629 aggregate-trade rows; prior pilot verified ZIP CRC, CSV schema, aggregate-ID ordering/uniqueness, timestamps and month bounds.
- Buyer-maker=true means taker sell; false means taker buy.
- Matching official 5m kline archive SHA-256: 3a2d163a2bd28ca614fa0840a92ecbcde0d9c4962b278dd619d5bf81a9918e26.
- This is one month only. It cannot establish generalization, chronological train/validation/OOS performance, or a tradable edge.

## Exact reconstruction
- Preserve the exact aggTrade price; for this month validate every price lies on a 0.1 USDT grid, store price as integer tenths of a USDT.
- Assign each aggTrade to UTC 5m bucket floor(transact_time_ms / 300000) * 300000.
- At each (5m bucket, exact price tick), sum base quantity separately for taker buys and taker sells; also count aggregate-trade records.
- Per-bar price-level volume = buy + sell; delta = buy - sell.
- Require unique (bucket, price_tick) output rows and exact reconciliation of total volume and taker-buy volume to official 5m klines within 0.10%; report per-bar median/p95/max discrepancies.
- Build each bar's POC as the price tick with maximum volume (ties choose lower price). Build contiguous 70% value area by expanding one tick at a time from POC, choosing the side with higher next-level volume (ties choose lower price).
- Diagonal buy imbalance at price p: buy_qty(p) >= 3 * sell_qty(p - 0.1) and buy_qty(p) >= 0.10 BTC. Diagonal sell imbalance at p: sell_qty(p) >= 3 * buy_qty(p + 0.1) and sell_qty(p) >= 0.10 BTC. A stacked imbalance is at least 3 consecutive price ticks flagged on the same side.

## Exploratory event definitions (fixed before inspecting derived feature outputs)
1. Absorption proxy:
   - Compute delta_fraction=(taker_buy_qty - taker_sell_qty)/total_qty per 5m bar.
   - delta_z uses the preceding 288 completed 5m bars only: rolling mean/std shifted one bar; require at least 96 prior observations.
   - Short event: delta_z >= +2.0 and close location <= 0.25.
   - Long event: delta_z <= -2.0 and close location >= 0.75.
2. Footprint continuation proxy:
   - Long event: at least 3 consecutive diagonal buy-imbalance price levels and close location >= 0.75.
   - Short event: at least 3 consecutive diagonal sell-imbalance price levels and close location <= 0.25.
3. For each event family, enforce a global 48-bar (4h) cooldown between selected events, regardless of direction.
4. Signal is known only after the 5m candle closes; enter at the next 5m open.
5. Descriptive forward horizons: 12 bars (1h) and 48 bars (4h), exit at the corresponding horizon close.
6. Descriptive transaction-cost deduction: 10 bps round trip. No stop, target, funding, spread, slippage, market impact or leverage model is included.
7. Report event count, directional win rate, descriptive return PF, mean/median net bps, event-sequence drawdown and maximum losing streak. These are event-study diagnostics, not R-multiple strategy metrics.
8. Use 10,000 day-cluster bootstrap resamples for mean-return confidence intervals. One month and a small number of UTC days are not adequate for promotion.

## Decision rules
- A successful price-level reconstruction is a data-engineering pass only.
- No parameter search, threshold tuning, best-side selection or OOS claim is permitted from this one-month pilot.
- Any positive event statistic is hypothesis-generating only. Before strategy testing, acquire multiple chronological months, validate each archive/checksum, resolve documented missing dates, and freeze a separate execution specification.
- Keep this research isolated from production/live rules. No execution alerts or orders.
