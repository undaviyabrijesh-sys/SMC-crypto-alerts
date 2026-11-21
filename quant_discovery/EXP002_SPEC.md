# EXP-002 — Expanded fixed-hypothesis strategy screen

**Status:** implementation and synthetic contract tests added on `ai-quant-rebuild`. Historical results have **not** been run yet. No strategy is approved or connected to execution alerts.

## Purpose

Expand the five fixed baseline families screened in EXP-001 with seven additional, materially distinct OHLCV hypotheses. All candidates are fixed before looking at the final holdout. The purpose is discovery and falsification, not maximizing the number of profitable backtest rows.

## Markets and bars

- Delta Exchange India public traded-price OHLCV archive.
- BTC, ETH and XAUT (Tether Gold perpetual; not spot XAUUSD).
- 15-minute signals with only closed 1-hour context; 1-hour signals with only closed 4-hour context.
- Closed higher-timeframe values become visible only after their source candle has closed.
- Indicators and recursive state are reset at timestamp gaps. No candle interpolation or forward-fill is used.

## Seven added hypotheses

| ID | Fixed rule |
|---|---|
| `ema_crossover` | EMA20/EMA50 cross in the already-closed higher-timeframe EMA50/EMA200 direction. |
| `adx_dmi_trend` | +DI/-DI cross with ADX(14) at least 20, aligned with the already-closed higher-timeframe trend. |
| `macd_momentum` | MACD(12,26,9) histogram crosses zero in the already-closed higher-timeframe trend direction. |
| `bollinger_squeeze_breakout` | A prior 10-bar Bollinger-width squeeze, followed by a 20-bar range and Bollinger-band breakout with volume above 1.2 times its 20-bar mean. |
| `utc_daily_vwap_reclaim` | A close crosses the UTC-day anchored VWAP with volume above 1.2 times its 20-bar mean and higher-timeframe trend alignment. |
| `stochastic_trend_pullback` | Stochastic(14,3) K/D cross back out of oversold (<35) or overbought (>65) in the higher-timeframe trend direction. |
| `supertrend_flip` | Supertrend(14,3) direction flips in agreement with the higher-timeframe EMA trend. |

The seven rules are hypotheses, not claims that the indicators or patterns predict returns. The fixed rules and code version must be retained with every result.

## Replay assumptions

- Signal exists only after the signal bar closes; entry is the next contiguous bar open.
- Stop distance is 1.2 × signal-bar ATR(14); target is 2.0R; maximum holding time is 24 hours.
- One simultaneous position per asset/strategy/timeframe stream.
- Same-bar stop and target ambiguity is resolved stop-first.
- A missing bar cancels a pending entry or exits an open position at the first observed post-gap open.
- The shared replay harness applies adverse slippage, fees, and an additional 1 bp per 8 hours carry stress. That carry component is a stress assumption, **not measured historical funding**.
- Cost sensitivity is reported at 10, 20 and 40 bps round trip. These are stress cases, not a verified Delta fee schedule.
- Chronological split: first 60% train, next 20% validation, final 20% untouched OOS. Five sequential 10%-sized test windows from 50–60%, 60–70%, 70–80%, 80–90% and 90–100% are reported separately.
- Regime-conditioned results are descriptive only. They are not post-hoc rules eligible for promotion.

## Required output

The runner writes:
- `exp002_manifest.json`: source commit, source archive hash, fixed hypotheses and assumptions.
- `exp002_oos_summary.csv`: OOS metrics by asset, timeframe and hypothesis.
- `exp002_split_and_cost_summary.csv`: train/validation/OOS and cost-stress metrics.
- `exp002_oos_regime_summary.csv`: descriptive trend and volatility regime partitions.
- `exp002_walk_forward_summary.csv`: sequential test-window metrics.
- `exp002_oos_trades.csv`: individual OOS trades and outcomes.

Metrics include trade count, win rate, net expectancy in R, profit factor, maximum drawdown in R, longest losing streak, trade frequency, mean holding time and TP/SL/TIME/GAP counts.

## Promotion policy

A positive OOS expectancy alone is not enough. A future candidate must have adequate samples, positive net expectancy and PF > 1 after realistic cost stress, non-fragile parameter neighbourhoods, and repeatable sequential/walk-forward behaviour. It must also survive data-quality, market-regime and independent validation review. Any subgroup discovered after looking at OOS is a new hypothesis and needs a fresh untouched test.

`quant_supervisor.APPROVED_STRATEGIES` remains empty. EXP-002 never updates it, never creates a Discord execution alert, never submits exchange orders, and cannot promote a candidate automatically.

## Run

After the 18-dataset three-year archive is downloaded and passes hash/row-count validation:

```bash
python quant_discovery/expanded_screen.py --data-dir historical_data --output-dir quant_discovery/results/exp002
```

The archive is not committed to Git. The manual historical-archive workflow retains the source archive and experiment result tables as GitHub Actions artifacts for 14 days.
