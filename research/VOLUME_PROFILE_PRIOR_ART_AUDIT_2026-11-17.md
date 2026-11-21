# Volume-profile prior-art audit correction — 2026-11-17

The initial prior-art audit for the 2026-11-17 POC-target study was incomplete. The repository already contains [`research/orderflow_profile_backtest.py`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/blob/ai-quant-rebuild/research/orderflow_profile_backtest.py).

Its `VP_ONLY` model builds a prior-complete-UTC-day 48-bin candle-volume proxy, distributes 5m candle volume across bins touched by each candle's range, expands a contiguous 70% value area from POC, signals VAH/VAL rejection, enters next 5m open, stops beyond the rejection candle by 0.10 ATR and caps holding at 4h. It tests fixed 1.5R/2R/3R targets.

The current Delta BTC study uses the same broad entry/stop/holding family and differs mainly by using prior-day POC as the target. It must be classified as an **exit-rule variation**, not a new independent strategy family.

The existing Binance USD-M VP_ONLY 2R/10bp report shows BTC development 567 trades / PF 0.155 / -780.39R and validation 112 trades / PF 0.093 / -198.76R; ETH development 571 trades / PF 0.34 / -419.47R and validation 115 trades / PF 0.24 / -110.21R. These figures are from a different feed/implementation and are contextual rather than directly comparable. Source: [`quant_discovery/ORDERFLOW_ZONE_BACKTEST_LATEST.md`](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/blob/ai-quant-rebuild/quant_discovery/ORDERFLOW_ZONE_BACKTEST_LATEST.md).

Further proxy-only volume-profile variants should pause. A genuine follow-up requires tick/trade-level BTC and ETH data with aggressor side so that volume-at-price and delta-at-price can be calculated rather than approximated from 5m OHLCV.
