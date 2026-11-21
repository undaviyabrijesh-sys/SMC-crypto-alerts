# Binance BTCUSDT EMA20/50 — clustered uncertainty audit

- Source: workflow artifact 44451403028, member trades_dev_val.csv.
- Trade-ledger SHA-256: b73ee6016deb161defe0bdbdeb183fdbc515fa3443185d6967c5bede45bd2910.
- 50,000 bootstrap resamples per cluster unit; net R after 10 bps; day/week/month blocks preserve trades within each sampled cluster.

## Point estimates

| Split | Trades | Active days | Active weeks | Active months | Net R | Mean R | PF | Top 3 winners / positive R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Development | 94 | 75 | 39 | 11 | -2.27 | -0.024 | 0.933 | 25.54% |
| Validation | 24 | 21 | 10 | 3 | +8.57 | +0.357 | 2.953 | 57.78% |

## Mean net R per trade — 95% cluster bootstrap intervals

| Split | Day | Week | Month |
|---|---:|---:|---:|
| Development | [-0.1935, +0.1647] | [-0.1719, +0.1380] | [-0.1723, +0.1788] |
| Validation | [-0.0295, +0.8277] | [+0.0664, +0.7762] | [-0.0446, +0.5958] |

Validation bootstrap probability of positive mean: day 96.34%, week 99.47%, month 96.35%. The monthly interval crosses zero and there are only three active validation months. The three largest validation winners contribute 57.78% of positive R.

Development probability of positive mean is only 37.82%–39.00%; all three intervals cross zero. Development PF intervals also cross 1. These diagnostics are descriptive; they do not remove selection bias or establish an edge.
