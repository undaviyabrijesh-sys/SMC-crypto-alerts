# Binance USD-M BTCUSDT aggTrade 5m-boundary low-mismatch control

Date frozen: 2026-11-18 UTC  
Control day: 2026-09-12 UTC  
Instrument: Binance USD-M BTCUSDT  
Scope: post-hoc forensic control only; no strategy PnL or parameter selection.

## Selection rationale

The previously inspected September 2026 monthly reconciliation showed 2026-09-12 as the lowest-mismatch day in that month (6 total-volume mismatch bars and 2 taker-buy mismatch bars at the exact comparison tolerance used in the parent study). This date was selected after inspecting the month and is not random, independent validation or OOS evidence.

## Question

Apply the same raw-trades / aggTrades / 5m-klines group audit used for the 2026-09-03 stress day to a low-mismatch day. Determine whether any remaining per-bar offsets are explained by aggTrade groups whose underlying raw trade timestamps span a 5-minute boundary.

## Frozen inputs

- Official daily USD-M BTCUSDT raw trades archive and companion CHECKSUM.
- Official daily USD-M BTCUSDT aggTrades archive and companion CHECKSUM.
- Official daily USD-M BTCUSDT 5m klines archive and companion CHECKSUM.

Date-specific paths use 2026-09-12. The same script, ID-range matching, 100ms group checks, and volume/taker-buy bucket reconciliation are used without parameter changes.

## Decision rules

- Verify SHA-256 and ZIP CRC for all three archives.
- Require raw trade IDs/timestamps/price/quantity validity and complete 288-bar kline coverage.
- Report complete and incomplete day-edge aggTrade groups separately.
- Report exact raw quantity, price and buyer-maker consistency for complete aggTrade ID ranges.
- Compare raw trade timestamp buckets, aggTrade timestamp buckets and raw members reassigned to aggTrade timestamp buckets against official klines.
- Do not infer a general market-data rule from one stress day plus one selected control day. The control is corroborative forensic evidence only.
- No strategy backtest, OOS, or performance promotion is permitted from this control.

## Implementation

Reuse `research/binance_aggtrade_boundary_forensics.py`. The workflow writes only compact report/metadata/reconciliation outputs to its artifact; bulky source archives are removed after processing.
