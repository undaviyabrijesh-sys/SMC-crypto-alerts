# Binance USD-M BTCUSDT raw-trade / aggTrade 5m-boundary forensic audit

Date frozen: 2026-11-18 UTC  
Target day: 2026-09-03 UTC  
Instrument: Binance USD-M BTCUSDT  
Scope: data-quality forensic audit only; no strategy backtest or parameter selection.

## Why this date

The already-inspected September 2026 monthly reconciliation showed the largest per-bar total-volume and taker-buy deviations on 2026-09-03 (2.644% and 7.939% maximum relative error respectively). This date is deliberately selected as a stress-case diagnostic, not as a random or out-of-sample sample. The analysis is post-hoc and cannot be used as independent strategy evidence.

## Frozen question

Do the 5-minute per-bar differences between Binance USD-M aggTrades and official 5m klines arise because an aggTrade group contains underlying raw trades on both sides of a 5-minute boundary, while the aggTrade record is timestamped at the final underlying trade?

Binance's official USD-M documentation says aggTrades aggregate fills at the same price and taking side every 100ms. This audit will test the explanation using the underlying raw trade IDs, prices, quantities, timestamps and buyer-maker flags rather than assume it.

## Data inputs

For 2026-09-03, download the official daily archives and companion SHA-256 CHECKSUM files:

- `data/futures/um/daily/trades/BTCUSDT/BTCUSDT-trades-2026-09-03.zip`
- `data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-09-03.zip`
- `data/futures/um/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2026-09-03.zip`

No raw market data is committed to Git or retained in the workflow artifact; only compact forensic outputs and hashes are retained.

## Frozen validation

1. Verify every ZIP SHA-256 against its companion CHECKSUM and run ZIP CRC validation.
2. Validate raw trade IDs are strictly increasing, timestamps do not regress, and prices/quantities are finite and positive.
3. Validate aggTrade IDs and underlying first/last trade-ID ranges are strictly increasing and non-overlapping.
4. For complete underlying ID ranges present in the daily raw archive, map raw trades to aggTrade ranges and compare:
   - raw quantity sum versus aggTrade quantity;
   - raw price and buyer-maker consistency;
   - first/last raw IDs versus aggTrade first/last IDs;
   - aggTrade timestamp versus final raw trade timestamp;
   - raw group duration and whether the group crosses a 5-minute boundary.
5. Exclude daily edge groups whose underlying first/last IDs fall outside the one-day raw archive from group-level proof; disclose their count.
6. Reconstruct 5-minute total volume and taker-buy volume three ways:
   - raw trades assigned to their own execution timestamps;
   - aggTrades assigned to the aggTrade timestamp;
   - complete raw group members reassigned to their enclosing aggTrade timestamp.
7. Compare all three with official 5m klines, including trade counts.
8. Report whether complete-group reassignment reproduces the aggTrade bucket totals and whether raw trade buckets reconcile to klines. A boundary explanation is supported only if the raw-to-kline and group-to-agg checks pass and the per-bar offsets are accounted for.

## Interpretation rules

- A successful forensic match is a data-engineering finding, not a trading edge.
- Failure to reconcile raw trades to klines means the cause remains unresolved; do not label it an aggTrade boundary issue.
- If the first/last daily edge group is incomplete, report and exclude it rather than silently accepting partial membership.
- Do not alter or retune the September sweep/reclaim strategy using these findings.
- No OOS or performance claim is produced by this audit.

## Code and execution

- Implementation: `research/binance_aggtrade_boundary_forensics.py`
- Workflow: `.github/workflows/binance-aggtrade-boundary-forensics.yml`
- Required deterministic self-tests: UTC 5m bucketing, boundary-crossing reassignment, price/side/quantity group matching, taker-side interpretation and checksum/header aliases.
