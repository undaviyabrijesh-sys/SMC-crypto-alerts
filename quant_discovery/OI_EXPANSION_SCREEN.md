# OI Expansion + Volatility Expansion Screen

**Run date:** 2026-11-05  
**Status:** REJECTED AS A TRADING EDGE — exploratory screen only. No production alert eligibility.

## Hypothesis

After an unusually large 1h move, positive open-interest expansion may distinguish directional participation from a low-participation price spike and improve continuation entries. Direction follows the completed signal-hour return. This is an independent non-SMC research hypothesis; it is not connected to the production worker.

## Data and timing

- Price: Delta BTCUSD, ETHUSD and XAUTUSD traded-price 5m OHLCV, resampled to complete 1h bars only (12 observed 5m candles required).
- OI: Delta `OI:<contract>` historical 1h candles. The screen assumes the API timestamp is the candle-open time and aligns its close to timestamp + 1h. This is an explicit timing assumption that still requires confirmation against endpoint semantics.
- OI is used only as a percentage change; raw levels are not compared across assets. Non-positive OI observations are treated as missing. No missing bars are filled.
- The archives' manifests and SHA-256 validations passed. The derivatives archive contains 758,119 candles across nine series; the OHLCV archive contains 926,209 candles across 18 symbol/timeframe files.
- BTC/ETH cover roughly 2.7 years; XAUT starts 2026-04-17, so its test history is only about 6.6 months.

## Fixed screen specification

- Signal at a completed 1h close when absolute 1h return exceeds its prior-720-hour 90th percentile and positive OI percentage change exceeds its prior-720-hour 80th or 90th percentile (minimum 168 prior observations).
- Direction follows the signal-hour return; entry is next 1h bar open.
- Stop: 1.0x or 1.5x causal 14-hour ATR. Target: 2R or 3R. Maximum hold: eight 1h bars.
- Intrabar ambiguity is resolved stop-first. One open trade per asset; no overlapping trades.
- Chronological split: first 60% train, next 20% validation, final 20% OOS. Trades crossing a split boundary are excluded. Rolling thresholds are shifted one bar and use only prior observations.
- Costs: 10 bps all-in round-trip base and 20 bps stress. These are assumptions for combined fees/spread/slippage, not observed bid/ask costs. Funding is excluded because historical funding units and settlement-event attribution remain unresolved.

## Results

Best OOS row per asset is shown only as a compact summary of the full eight-combination grid; it is **not** a selected strategy.

| Asset | Best OOS parameters | OOS trades | Win rate | Expectancy (10 bps) | PF | Max DD | Max loss streak | Trades / 30d | Expectancy (20 bps) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | OI q90, SL 1.5 ATR, TP 3R | 45 | 42.22% | -0.0313R | 0.9337 | -7.8709R | 6 | 6.59 | -0.1365R |
| ETH | OI q80, SL 1.0 ATR, TP 3R | 67 | 43.28% | +0.0493R | 1.0896 | -10.8919R | 5 | 10.04 | -0.0640R |
| XAUT | OI q90, SL 1.0 ATR, TP 3R | 14 | 71.43% | +0.2863R | 1.7499 | -3.7874R | 2 | 10.43 | -0.0305R |

### Full OOS parameter-grid ranges (all eight combinations per asset)

| Asset | Trades | Win rate | Expectancy (10 bps) | PF | Max DD | Max losing streak | Trades / 30d | Expectancy (20 bps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 45–67 | 29.85–43.48% | -0.3189 to -0.0313R | 0.5411–0.9337 | -23.7326 to -7.5739R | 6–7 | 6.59–9.82 | -0.4729 to -0.1365R |
| ETH | 42–68 | 37.21–47.69% | -0.2571 to +0.0493R | 0.5436–1.1239 | -15.2161 to -7.3901R | 5–7 | 6.30–10.19 | -0.3649 to -0.0293R |
| XAUT | 14–22 | 54.55–71.43% | -0.0100 to +0.2863R | 0.9821–1.9030 | -4.4127 to -2.5681R | 2–3 | 10.43–16.40 | -0.3153 to +0.0002R |

### Robustness interpretation

- **BTC:** all eight OOS parameter combinations are negative at 10 bps (expectancy range -0.3189R to -0.0313R); all are more negative at 20 bps.
- **ETH:** the best OOS result is only +0.0493R at 10 bps, but its train and validation expectancy are negative and it turns negative at 20 bps. OOS expectancy across the grid ranges -0.2571R to +0.0493R.
- **XAUT:** the apparent +0.2863R OOS result uses only 14 trades over approximately 40 days. The same parameter row is negative in train (-0.0444R) and validation (-0.1238R), and turns negative at 20 bps. This is a weak sample and likely regime sensitivity, not evidence of an edge.

## Decision

**Reject all three asset candidates for now.** No stable positive expectancy survives chronological train/validation/OOS consistency and the 20 bps cost stress. XAUT's short history and 14-trade OOS sample are particularly insufficient. No walk-forward promotion stage is warranted until a candidate first survives this screen with adequate samples and cost robustness.

This study is not equivalent to visual chart analysis and cannot validate or invalidate visual-AI setups. No candidate is routed into production alerts. Funding remains excluded; no historical funding P&L is inferred.

## Reproduction

Extract the verified OHLCV and derivatives archives into separate directories, then run:

```bash
python quant_discovery/oi_expansion_screen.py \
  --ohlcv-dir /path/to/ohlcv_archive \
  --derivatives-dir /path/to/derivatives_archive \
  --output oi_expansion_results.json
```

Offline tests cover complete-hour filtering, OI close-time alignment, lagged thresholds/no look-ahead, stop-first same-bar handling and higher-cost sensitivity.
