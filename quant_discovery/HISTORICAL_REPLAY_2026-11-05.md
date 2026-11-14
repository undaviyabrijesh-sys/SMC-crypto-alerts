# Salty Quant — Historical Replay & Strategy Decision

**Run date:** 5 November 2026  
**Repository:** `undaviyabrijesh-sys/SMC-crypto-alerts`  
**Branch:** `ai-quant-rebuild`  
**Mode:** deterministic, AI-free, paper-only

## Decision

**Do not activate execution alerts for any of the six strategies.** The current rules did not demonstrate a robust, cost-tolerant out-of-sample edge. `quant_supervisor.APPROVED_STRATEGIES` must remain empty. This is a completed validation decision, not a profitability claim.

At the lowest tested non-zero cost proxy (5 bps round trip), the single-position-per-symbol ensemble is negative in the untouched test segment for BTC, ETH and XAUT. All four sequential walk-forward windows are also negative for all three markets at 5 bps.

## Data integrity and coverage

The archive contains **926,209 closed OHLCV candles across 18 files** (BTC, ETH and XAUT; 5m, 15m, 1h, 4h, 1d and 1w). Every CSV's SHA-256, row count, UTC timestamp ordering, uniqueness and required OHLCV fields were verified against the coverage manifest. No missing bars were synthesized or forward-filled.

| Market | Available history | 5m candles | 5m observed coverage | 5m gaps / largest gap |
|---|---|---:|---:|---:|
| BTCUSD | 29 Dec 2023 – 5 Nov 2026 | 294,933 | 98.3248% | 5 / 911,100 sec |
| ETHUSD | 6 Feb 2024 – 5 Nov 2026 | 288,228 | 99.8085% | 2 / 164,400 sec |
| XAUTUSD | 17 Apr 2026 – 5 Nov 2026 | 58,045 | 99.9983% | 1 / 600 sec |

**XAUT is not a three-year dataset:** it contains about 6.6 months and 29 weekly candles. BTC and ETH also begin later than the archive's requested start because their observed history begins later.

## Replay methodology

- All six strategy rules were frozen; no holdout parameter tuning was performed.
- The replay evaluates every newly closed 5m candle, matching `quant_worker.py`; higher-timeframe context is the latest fully closed candle available at that event.
- Candidate decision is at the signal candle close. Fill is the **next 5m candle open**; candidates are rejected if actual fill geometry fails the 2R minimum.
- If TP and SL are both touched in the same 5m candle, SL is counted first. Adverse gap-through stops exit at the bar open.
- Maximum hold is 48 hours. TIME is assigned only if all expected 5m candles exist. A gap before confirmed exit leaves a trade unresolved rather than inventing an outcome. No trades were censored in this archive replay.
- Standalone runs isolate each strategy. The ensemble uses the supervisor's ranking/conflict rules and allows one open position per symbol.
- Chronological split: 60% train / 20% validation / 20% test. Validation and test use a 48-hour start embargo; trades exiting beyond a split boundary are excluded. Four expanding-context 10%-of-history OOS windows also use a 48-hour embargo and exclude boundary-crossing trades. Rules are frozen; no fold refit occurs.
- Cost sensitivities: 0, 5, 10, 20 and 40 bps round-trip notional proxies. Historical spread/depth, actual fee tier and slippage were not available. Funding was excluded because settlement-event timestamp/unit attribution was not verified. These are scenarios, **not actual Delta fees or measured slippage**.
- Results are in R units, not INR P&L. No leverage, position sizing, funding or liquidation is modeled.

## Candidate-engine parity

The vectorized replay was compared with the branch's `quant_strategies.generate_candidates()` on **18 trade-bearing events per asset (54 checks)** using the same rolling OHLCV row caps as `data.py`. All checks passed: candidate IDs, direction, rule-quality score, signal entry, stop and target matched. This is sampled parity, not exhaustive proof for every candle.

## Ensemble — untouched test segment, 5 bps cost proxy

| Market | Trades | Gross expectancy (0 bps) | Gross PF | Net expectancy (5 bps) | Net PF (5 bps) | Net expectancy (10 bps) | Max DD (5 bps) | Longest loss streak (5 bps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 676 | -0.0474R | 0.9327 | -0.2527R | 0.7007 | -0.4581R | 172.28R | 14 |
| ETH | 637 | -0.0394R | 0.9438 | -0.1821R | 0.7734 | -0.3247R | 126.22R | 16 |
| XAUT | 128 | +0.2801R | 1.4656 | -0.3916R | 0.6222 | -1.0633R | 65.98R | 20 |

XAUT's positive gross result is short-history-dependent and is erased by the 5 bps proxy; it is not an approval candidate.

## Walk-forward — ensemble at 5 bps round-trip proxy

| Market | WF1 | WF2 | WF3 | WF4 |
|---|---:|---:|---:|---:|
| BTC | -0.2296R (363 trades) | -0.0758R (322) | -0.1861R (322) | -0.2867R (346) |
| ETH | -0.0463R (308) | -0.1128R (326) | -0.2050R (300) | -0.1693R (326) |
| XAUT | -0.2091R (17) | -0.5373R (52) | -0.1394R (58) | -0.3875R (65) |

All 12 ensemble folds are negative at 5 bps. XAUT folds also have insufficient history for a durable conclusion.

## Strategy-level test findings at 5 bps

- **BTC:** all six standalone strategies were negative. Least negative: MOMENTUM_CONTINUATION at -0.1611R (62 trades), still with PF below 1.
- **ETH:** all six were negative. LIQUIDITY_SWEEP_REVERSAL was -0.1123R (505 trades), PF 0.8559.
- **XAUT:** isolated positives had very small samples (BREAKOUT_RETEST 16 trades, MOMENTUM_CONTINUATION 6, VOLATILITY_EXPANSION 11). They fail sample-size/history/fold stability requirements; overall ensemble and all four 5 bps folds were negative.

## Operating state

- All six strategy IDs remain `RESEARCH_ONLY`; no new execution alert is enabled for them.
- Exact branch head `77eb892aa9fd4a33ccf909e80dffc07c82ce536f` passed deterministic quant CI run `42064655438`.
- PR #1 remains open and draft; `main` is untouched. Branch schedule is not enabled, no deployment occurred, and no live orders were placed.
- Discord webhook delivery was not tested by this historical replay.
- The replay source, five focused unit tests and full raw result package are included in the accompanying research bundle. The branch tracks this decision report and a compact CSV summary.

## Next research direction

Do not loosen thresholds or cherry-pick positive slices. Treat the current six rules as rejected for deployment. Define a new hypothesis as a new frozen version, then test it under the same data, cost and OOS discipline. Verify actual fee tiers and measured spreads/slippage, expand XAUT history, and complete parameter-neighbourhood, regime and bootstrap reviews before any future promotion.
