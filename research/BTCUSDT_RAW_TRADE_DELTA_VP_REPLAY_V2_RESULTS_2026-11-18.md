# BTCUSDT September 2026 raw-trade delta/VP replay V2 — completed

**Workflow:** [44337782359](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44337782359), completed successfully on ai-quant-rebuild at commit 38e74226c42bdf29d6b9f3b5cea4360baff187fa. Artifact: [14443580063](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44337782359/artifacts/14443580063).

## Data integrity

- 30/30 daily Binance USD-M BTCUSDT raw-trade archives downloaded and verified.
- 96,456,037 raw trade records; 4,267,354.779 BTC total quantity.
- Taker-buy 2,112,553.238 BTC; taker-sell 2,154,801.541 BTC; net delta -42,248.303 BTC.
- All 8,640 five-minute bars exactly reconciled to official Binance klines for total volume, taker-buy volume and trade count (relative tolerance 1e-8; maximum relative errors 2.34e-12 volume and 1.53e-12 taker-buy).

## Results at 10 bps round-trip cost

| Variant | Trades | Win rate | PF | Net R | Max DD | Losing streak |
|---|---:|---:|---:|---:|---:|---:|
| Price-only | 43 | 25.58% | 0.361 | -33.135R | -35.078R | 9 |
| Raw-delta confirmed | 21 | 23.81% | 0.413 | -15.667R | -19.916R | 11 |

At zero cost, price-only was +1.135R (PF 1.042) and delta-confirmed +0.820R (PF 1.058). At 4 bps they fell to -12.573R and -5.775R. At 20 bps: -67.406R and -32.155R.

The corrected raw-timestamp results are close to, and slightly worse than, the prior aggTrade-bucket results. The bucket-alignment defect is real, but fixing it did not reveal a profitable edge in this one-month setup. The delta filter reduces trade count but does not rescue the strategy.

## Limitations and decision

This is one post-hoc September month, already inspected before correction; it is not development/validation/OOS evidence. Funding cashflow, spread and market impact are not modeled; positions are flattened before funding boundaries. Do not tune September. Reject this specific VP sweep/reclaim execution definition under the tested assumptions. Keep genuine tick-level order-flow data for future hypotheses, but do not assume the entire feature family is disproven.
