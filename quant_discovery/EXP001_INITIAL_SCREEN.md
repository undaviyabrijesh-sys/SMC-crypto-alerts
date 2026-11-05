# EXP-001 — Initial multi-strategy OHLCV screen

**Run date:** 2026-11-05  
**Status:** REJECTED AS AN EDGE — exploratory results only; nothing is promoted to production alerts.

## Archive and data quality

The verified archive is available in the ChatGPT Library as salty_quant_historical_ohlcv_3y_verified.zip (14.6 MB compressed; about 54 MB extracted). It is not committed to Git. SHA-256:

07db78359920ceec6331a8f96642406543516cb12a78a1ca90099f90eb6bb9d5

- Delta Exchange India public historical traded-price OHLCV: BTCUSD, ETHUSD and XAUTUSD perpetuals; 5m, 15m, 1h, 4h, 1d and 1w.
- 18 symbol/timeframe files, **926,209 candles**. archive_validation.json reports passed; chronology, uniqueness, finite/positive OHLC, OHLC consistency, nonnegative volume and SHA-256 checks passed. Forming candles were removed; missing candles were not filled.
- Actual availability is not three full years for every instrument: BTC begins 2023-12-29, ETH 2024-02-06, and XAUTUSD only 2026-04-17 (about 6.6 months). XAUTUSD is Delta Tether Gold perpetual, not spot XAUUSD.
- Requested-range coverage estimates: BTC roughly 93.5–95.1%, ETH 91.1–91.5%, XAU 18.4–18.5%. Within observed spans, most files are 100%; notable gaps include BTC 5m (5 gaps; largest 911,100s), BTC 15m (2; 311,400s), BTC 1h (1; 136,800s), ETH 5m (2; 164,400s), and XAU 5m (1; 600s).
- The archive contains no historical funding, mark/index, bid/ask spread, order-book depth or executable fills.

## Experiment protocol

Reproduce with:

    python quant_discovery/initial_screen.py --data-dir historical_data

The script first checks the 18-file manifest, row counts and SHA-256 hashes. It writes five result tables under quant_discovery/results/.

- Markets: BTC, ETH, XAU. Research entry timeframes: 15m and 1h, with closed 1h/4h context respectively.
- Fixed candidate families: liquidity sweep/reclaim, higher-timeframe trend pullback, Donchian breakout, Bollinger/RSI2 mean reversion, and ATR expansion breakout.
- Signal is formed at a fully closed bar; entry is next bar open. Higher-timeframe indicators are attached only after that candle closes. No future bars are used to form a signal.
- Stops are wick/ATR-based; first target is 2R; max holding time is 24 hours. Same-bar SL/TP ambiguity resolves SL-first. A data gap exits at the first observed post-gap open. Trades that cannot fit inside a split's time-stop window are skipped rather than force-closed at a split boundary. One position per strategy stream at a time.
- Chronological split: first 60% train, next 20% validation, final 20% untouched OOS. Five sequential expanding walk-forward test blocks cover 50–60%, 60–70%, 70–80%, 80–90%, and 90–100%.
- Baseline costs are **10 bps round-trip** as an explicit combined fee/spread/slippage scenario, plus **1 bp per 8 hours** of adverse funding stress. This is not measured historical funding or a verified fee tier. Cost sensitivity is 5/10/20/40 bps. Stop-distance scale is 0.8/1.0/1.2 and target is 1.5R/2R/2.5R.

## Main OOS findings

At 10 bps round-trip plus the funding stress, **all 30 asset × timeframe × strategy combinations had negative OOS net expectancy**. The least-negative result was BTC 1h mean reversion at -0.0149R, PF 0.978. No candidate passed.

| Market / TF | Candidate | OOS trades | Win rate | Net expectancy | PF | Max DD | Max loss streak | Trades/month |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| BTC 1h | Mean reversion | 176 | 39.77% | -0.0149R | 0.978 | -18.078R | 7 | 25.76 |
| ETH 15m | Volatility expansion | 214 | 37.85% | -0.0785R | 0.894 | -43.408R | 9 | 32.48 |
| BTC 1h | Donchian breakout | 105 | 37.14% | -0.0840R | 0.873 | -14.261R | 14 | 15.37 |
| ETH 1h | Donchian breakout | 86 | 36.05% | -0.1180R | 0.819 | -13.798R | 8 | 13.06 |
| XAU 1h | Sweep/reclaim | 43 | 37.21% | -0.5101R | 0.529 | -23.678R | 6 | 32.48 |

The 270 OOS stop/target combinations (30 base combinations × 9 settings) were also negative at the 10 bps baseline; the best was still -0.0066R. The five expanding walk-forward blocks had mean expectancy across the 30 cells of -0.403R, -0.289R, -0.410R, -0.602R and -0.450R respectively. A few individual windows were positive, but they did not persist into the final holdout.

At the 5 bps cost scenario, BTC 1h mean reversion (+0.0649R, PF 1.105) and ETH 15m volatility expansion (+0.0199R, PF 1.029) turned slightly positive. Both were negative at 10 bps; this sensitivity means the apparent result depends too heavily on optimistic execution costs.

## Follow-up hypothesis — not an edge

ETH 15m volatility expansion in the 1h downtrend regime showed +0.0946R OOS (113 trades, PF 1.140, max DD -25.603R, max loss streak 7). Its chronological regime-filtered expectancy was -0.0052R in train (349 trades), +0.1223R in validation (153), and +0.0946R in OOS (113). However, it was discovered through post-hoc regime segmentation, flips to -0.1111R at 20 bps costs, and the stop/target grid is mixed. Treat it as a hypothesis to test on new data, not a validated edge or production candidate.

## Decision and next work

- **Reject all five baseline families for production promotion.** Do not change visual AI thresholds or route any research candidate to Discord.
- Continue the independent research branch with actual historical funding/mark data, and validated spread/slippage proxies. Do not treat unavailable costs as zero.
- Pre-register the ETH 15m volatility-expansion/downtrend hypothesis, test it on additional untouched windows and other instruments, and compare against visual AI decisions. Include regime-conditioned sample size, expectancy, PF, drawdown and loss streaks.
- Gold needs substantially more history before meaningful long-horizon claims. The current XAUTUSD archive supports only a short exploratory window.
- This is a deterministic OHLCV screen, not a backtest of live visual-AI alerts. No live worker, production chart image, OpenAI call, Discord delivery, broker fill or order was exercised. No order was placed.


## Reproducibility correction — 2026-11-05

A final-boundary audit found an off-by-one in `simulate()`: the exclusive split end was clamped to `len(x)-1`, omitting the last fully closed candle and skipping trades whose 24-hour holding window ended on that candle. The clamp is corrected to `min(end, len(x))`, with a regression test proving that the final closed bar can resolve a trade. Entry timing, signal definitions, stops, targets, costs and split boundaries are unchanged.

The full 18-file archive was re-run after this correction. All **30/30 OOS asset × timeframe × strategy cells remain negative** at the 10 bps round-trip scenario plus 1 bp/8h adverse carry stress. Only one OOS cell changed: XAU 15m mean-reversion gained one completed trade (116 → 117) and expectancy moved from -1.3875R to -1.3611R. The least-negative cell remains BTC 1h mean-reversion (176 trades, 39.77% net win rate, -0.0149R expectancy, PF 0.978, -18.078R max drawdown, 7 consecutive losses). The worst cell remains XAU 15m trend-pullback (168 trades, 20.83% net win rate, -1.6886R expectancy, PF 0.137, -284.499R max drawdown, 27 consecutive losses).

**Decision unchanged:** reject every tested family as a production edge. These fixed-rule results are not a test of visual-AI DNS decisions. The 1 bp/8h funding component remains an adverse stress assumption, not historical funding attribution; Delta funding is exchanged at discrete contract-specific funding snapshots, which require event-time mapping before use.
