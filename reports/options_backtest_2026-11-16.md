# Preliminary BTC/ETH options backtest — 2026-11-16

## Run status

A first-pass replay was run in this session against historical Binance Spot and Options 1h candles retrieved for **2026-05-20 00:00 UTC through 2026-06-30 23:00 UTC**. The replay is a direct API-data sample calculation using the rules documented in the research engine. It is **not** a full run of the persistent worker's Python CLI, because those candles have not yet been written into the worker's persistent `/data` volume.

This is an exploratory sample, not a strategy validation.

## Dataset coverage

- BTC underlying: 1,000 hourly candles. Close moved from 76,788.83 to 58,381.99 in the sample.
- ETH underlying: 1,000 hourly candles. Close moved from 2,111.29 to 1,565.18.
- Queried option contracts all shared the **2026-12-25 expiry**. The observed signal dates therefore had approximately **177–219 days to expiry**. The research override was 7–300 DTE to include this history; this is not a weekly/near-expiry test.
- Individual contracts contained only 2–52 traded hourly bars out of 1,000 underlying bars. No-trade placeholder candles were excluded.
- Same-hour synchronized option-leg prints were rare. The tested BTC 70k/65k put-credit legs overlapped on 2 hours; BTC 80k/85k call-credit legs on 4 hours. ETH 2,000/1,800 put-credit legs overlapped on 2 hours; ETH 2,200/2,300 call-credit legs on 3 hours.
- No synchronized four-leg iron-condor entry was found in the sampled contracts.

## Common assumptions

- Timeframe: 1h; signal from a closed underlying candle.
- Option entry: next eligible traded option candle, with a maximum 1-hour delay.
- Each asset's model account starts at 10,000 USDT; risk budget 1% of current equity per trade.
- Per-side fee assumption: 5 bps.
- Per-side spread plus slippage proxy: 35 bps.
- Long premium: 30% premium stop, 50% premium target, four-hour max hold.
- Credit spreads: short option at least 3% OTM; protective wing at least 4% of spot farther OTM; 50% credit-capture target, stop at 2x entry credit, four-hour max hold.
- Credit-spread sizing uses vertical width minus received credit as the defined maximum-loss proxy. No naked short option strategy was tested.

## Long-premium results

All P&L below is model USDT, not a broker statement.

| Asset | Strategy | Trades | Win rate | Net P&L | Expectancy (R) | Gap-guard exits |
|---|---|---:|---:|---:|---:|---:|
| BTC | OPT-01 Momentum | 31 | 3.23% | -160.69 | -0.0575 | 29 |
| BTC | OPT-02 Sweep → MSS | 3 | 0.00% | -11.85 | -0.0457 | 3 |
| BTC | OPT-03 EMA Pullback | 11 | 9.09% | -17.05 | -0.0209 | 11 |
| ETH | OPT-01 Momentum | 16 | 0.00% | -88.12 | -0.0556 | 15 |
| ETH | OPT-02 Sweep → MSS | 3 | 0.00% | -17.48 | -0.0584 | 3 |
| ETH | OPT-03 EMA Pullback | 4 | 0.00% | -23.30 | -0.0584 | 4 |

The apparent BTC OPT-03 test-segment gain was only 4 trades (1 winner) and does not offset the negative full-sample result. The straddle/strangle candidates do not have enough synchronized traded call/put observations in this sample to infer an edge.

## Defined-risk option-selling results

| Asset | Strategy | Trades | Win rate | Net P&L | Expectancy (R) | Gap-guard exits |
|---|---|---:|---:|---:|---:|---:|
| BTC | OPT-06 Bull Put Credit Spread | 1 | 0.00% | -1.01 | -0.0160 | 0 |
| BTC | OPT-07 Bear Call Credit Spread | 5 | 0.00% | -9.88 | -0.0259 | 2 |
| ETH | OPT-06 Bull Put Credit Spread | 0 | — | 0.00 | — | 0 |
| ETH | OPT-07 Bear Call Credit Spread | 3 | 0.00% | -9.54 | -0.0319 | 3 |
| BTC/ETH | OPT-08 Iron Condor | 0 | — | 0.00 | — | 0 |

The seller sample contains only **9 trades in total**, with no winners. A zero-trade result is not a win; it means no valid synchronized entry was available.

## Interpretation

1. **No tested strategy is profitable or validated on this sample.** None should be promoted or used for live trading.
2. The selling strategies are defined-risk vertical spreads and an iron condor only. Naked calls/puts and naked short straddles/strangles were deliberately excluded.
3. Most long-option trades exited through the data-gap guard. The option market's sparse prints make the four-hour exit and OHLC-derived fills highly uncertain.
4. The historical sample is one long-dated expiry rather than a representative rolling chain. Historical bid/ask, order-book depth, IV/Greeks/OI series, assignment/settlement, margin and liquidation are not available in this replay.
5. The spread/slippage assumptions are proxies, not calibrated to historical quotes. Actual executable results may be worse.

## Next validation gate

The collector must build a broader, rolling contract dataset with synchronized call/put histories and denser traded candles. Then re-run from the repository CLI with the same frozen parameters, compare multiple expiries/DTE buckets, and require enough trades in both validation and untouched test periods before any optimization or promotion.
