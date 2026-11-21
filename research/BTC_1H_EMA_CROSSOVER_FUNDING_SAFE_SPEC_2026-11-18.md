# BTC 1H EMA crossover continuation — run specification

**Research date:** 2026-11-18  
**Instrument:** Delta Exchange India BTCUSD perpetual  
**Branch:** \`ai-quant-rebuild\`  
**Status:** Exploratory, completed; no configuration passed the frozen development/validation gate.

## Research question

Does a completed 1-hour fast/slow EMA crossover provide continuation information distinct from the previously tested EMA pullback and EMA51 candle-break systems?

A repository audit on 2026-11-18 found no prior EMA-crossover implementation or ledger entry. Existing EMA work is predominantly pullback/reclaim or candle-break entry logic, not a moving-average cross entry.

## Rules encoded in the executable

- Signal timeframe: complete UTC-aligned 1-hour bars, aggregated from exactly 12 contiguous 5-minute source bars.
- EMA pairs: 9/21, 20/50 and 50/200; both bullish and bearish crosses.
- Signal: on a completed 1-hour bar, fast EMA crosses above/below slow EMA; enter at the next 1-hour bar open.
- Stop: 1.5x or 2.5x Wilder ATR(14), measured on the signal bar and anchored from its close.
- Target: fixed 2R or 3R from actual next-open entry and initial stop distance.
- Higher-timeframe filter: none, or latest fully completed 4-hour close above its 4-hour EMA200 for longs / below for shorts. 4-hour bars require four contiguous completed 1-hour bars and are right-labelled; incomplete/current 4-hour values are not used.
- Positioning: one open trade per configuration; no overlapping positions; both directions retained.
- Funding-safe execution window: only the post-mechanism-transition period beginning 2025-09-08 12:00 UTC is evaluated. Entries are accepted only when at least one complete 1-hour bar can close strictly before the next 00:00/08:00/16:00 UTC funding boundary. If stop/target is not hit, exit at the last 1-hour close strictly before that boundary. No position remains open at a funding snapshot.
- Final evaluation data ends before the 2026-11-14 00:00 UTC funding boundary, the last settlement timestamp covered by the archive. The following incomplete funding block is excluded.
- Execution: same-bar stop wins if both stop and target are touched; adverse stop gap fills at the worse open; favourable target gap is capped at target; no trade crosses a raw data gap or split boundary.
- Costs: assumed round-trip 4/7/10/20 bps of entry notional; 10 bps is primary. Net R = gross R - (cost_bps/10,000 × entry_price / initial_stop_risk).

## Matrix

3 EMA pairs × 2 ATR stop multiples × 2 targets × 2 HTF filter states = **24 configurations**. The matrix was finite and fixed before the market simulation. This file is an after-run archival specification, not a timestamped GitHub preregistration; the executable contains the exact rules used.

## Data and partitions

- 5-minute source: \`data/btc_5m_source.csv\`, 210,239 rows, 2024-11-16 11:30 UTC to 2026-11-16 11:20 UTC.
- Complete 1-hour bars: 17,519 across the source archive.
- Evaluation period: 2025-09-08 12:00 UTC through 2026-11-13 23:00 UTC; 10,356 1-hour bars.
- Chronological 70/15/15 row split. Exact boundaries are in \`results/metadata.json\`.
- The final 15% was reserved and not evaluated because no configuration passed both development and validation.

## Funding and costs

The 1-hour Delta funding archive is included. It has five post-transition 5-hour gaps in the hourly observation series, but all expected post-transition 8-hour settlement timestamps in the evaluated period are present. The raw rate units and exact rate-to-settlement mapping remain unresolved, so no funding cashflow is applied. Instead, the test avoids funding snapshots by closing every position before the next settlement. This is a funding-avoidance execution convention, not a full funding PnL model.

4/7/10/20 bps are assumed flat round-trip cost sensitivities, not an authenticated user fee tier. Separate spread, slippage and market impact are not modeled.

## Promotion gate at 10 bps

At least 50 development trades and 20 validation trades; PF > 1.10 and net R > 0 in both; at least 50% positive active months in both; development max drawdown no worse than -20R and validation no worse than -10R. OOS is not run unless a configuration passes all gates.

## Integrity

Ten deterministic test groups passed, including complete-bar aggregation, 1H/4H future-perturbation invariance, stop-first ambiguity, adverse stop gaps, target-gap caps and funding-boundary clock logic. A separate trade-ledger audit recomputed 1,344 metric fields across 192 summary rows with zero differences. No overlapping positions, funding-boundary violations or split-boundary trades were found.
