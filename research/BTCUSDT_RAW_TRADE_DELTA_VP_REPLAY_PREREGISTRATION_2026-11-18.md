# BTCUSDT September 2026 raw-trade VP/delta correction — frozen replay specification

Frozen: 2026-11-18 UTC  
Instrument: Binance USD-M BTCUSDT perpetual  
Data period: 2026-09-01 00:00 UTC through 2026-10-01 00:00 UTC (exclusive)  
Status: post-hoc data-source correction of the already inspected September V1 diagnostic; not independent validation or OOS.

## Motivation

The V1 VP sweep/reclaim diagnostic used Binance USD-M aggTrades timestamped into 5m bars. A raw-trade forensic audit on 2026-09-03 and a low-mismatch control on 2026-09-12 showed that complete aggTrade groups can contain raw trades on both sides of a 5m boundary, while the aggTrade timestamp equals the first constituent raw-trade timestamp for every observed crossing group. Assigning the whole group to that timestamp bucket creates adjacent-bar offsets.

This replay replaces only the underlying data reconstruction with individual raw trades assigned by their own execution timestamps. The strategy rules and thresholds are frozen to V1. No parameter tuning is allowed.

## Data inputs

- 30 official Binance USD-M daily BTCUSDT raw-trades archives for 2026-09-01 through 2026-09-30, each with its companion SHA-256 CHECKSUM.
- Official monthly BTCUSDT 5m kline archive for 2026-09, with companion CHECKSUM.
- Raw trades are parsed as trade ID, price, quantity, quote quantity, timestamp and buyer-maker flag.
- Buyer-maker=false is interpreted as taker buy; true as taker sell.
- Price must remain on the previously validated 0.1 USDT tick grid.
- Raw ZIPs are processed one day at a time, checksum/CRC verified, then removed. No raw archive is committed or retained in the output artifact.

## Corrected feature construction

1. Assign each individual raw trade to UTC 5m bar floor(timestamp_ms / 300000) * 300000.
2. Per bar compute total base volume, taker-buy base volume, taker-sell base volume, signed delta (buy minus sell), and raw trade count.
3. Build each UTC day's exact-price volume profile directly from raw trades.
4. Build the 70% volume VAH/VAL/POC using the same POC expansion and lower-price tie-break used by the previous feature study.
5. Build 30m TPO counts from distinct UTC 30m periods per exact price; retain the same 70% POC-expansion rule for TPO summary.
6. Compute delta fraction = signed delta / total volume. Delta z-score uses the preceding 288 completed 5m bars, minimum 96 observations, rolling standard deviation ddof=0, and a one-bar shift.

## Mandatory data-quality gate

Before strategy replay, all 8,640 5m bars must reconcile to the official klines:
- raw total base volume within 1e-8 relative/absolute tolerance;
- raw taker-buy base volume within 1e-8 relative/absolute tolerance;
- raw trade count exactly equal.

Any failure aborts the strategy replay. Report all 30 daily archive hashes, row counts and per-bar reconciliation maxima.

## Frozen strategy rules (unchanged from V1)

- Prior completed UTC day exact raw-trade-price 70% volume VAH/VAL/POC.
- Short: signal high > prior VAH + 0.1; close < prior VAH; close location <= 0.25.
- Long: signal low < prior VAL - 0.1; close > prior VAL; close location >= 0.75.
- Delta-confirmed ablation: short raw delta z <= -1.5; long raw delta z >= +1.5.
- Signal is known only after the 5m candle closes; entry at next 5m open.
- Stop beyond signal extreme by 0.1 Wilder ATR14.
- Target previous completed day's volume POC; skip if target distance is less than 1R.
- One position at a time; global 48-bar cooldown; maximum 48 bars held.
- Exit at last 5m close before the next 00:00/08:00/16:00 UTC funding boundary. Funding cashflow is not modeled.
- Same-bar stop first; adverse gap-through stop fills at the open.
- Round-trip costs: 0, 4, 7, 10 and 20 bps.

## Required outputs

- Raw 5m delta bars and official-kline reconciliation.
- Daily raw-trade VP/TPO summaries.
- Trade ledger and summary for price-only and delta-confirmed variants at all five cost assumptions.
- At 10 bps, report trades, win rate, PF, net R, average R, max drawdown, losing streak, positive/active days, and long/short attribution.
- Compare V2 to the already verified V1 aggTrade-based September diagnostic without retuning.

## Interpretation and decision rules

- September 2026 was already inspected; the corrected replay is a forensic correction, not a fresh sample.
- No train/validation/OOS split is claimed from this one-month dataset.
- Do not optimize thresholds, targets, stops or sides from these results.
- If raw-trade delta still loses at 10 bps, keep the strategy rejected; if it improves, treat it as a hypothesis requiring multiple new chronological months and a frozen future holdout.
- Funding cashflow, spread, slippage, market impact and leverage are not modeled; positions are forced flat before funding.
- No production rule, live alert or exchange order may be changed by this study.

## Implementation

- `research/btcusdt_raw_trade_delta_rebuild_v2.py`
- Reuses checksum/ZIP validation and raw-trade parser from `research/binance_aggtrade_boundary_forensics.py`.
- Workflow: `.github/workflows/btcusdt-raw-trade-delta-v2.yml`
