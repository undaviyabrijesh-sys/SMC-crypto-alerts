# BTCUSDT premium-basis event study — prior output superseded

<badge>Superseded methodology version — do not use performance results</badge>

The archive reconstruction from workflow [44880219010](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44880219010) completed successfully and verified the 12-month aligned sample:

- 105,120 analysis bars (2025-11-01 through 2026-10-31).
- 52 monthly archives with SHA-256 and ZIP CRC checks.
- Three exact daily archive patches for 2026-06-29: index, mark and premium-index series.
- All 55 archive records passed the implemented row, checksum, boundary and alignment gates.

However, the first calculation version is superseded before any strategy conclusion is accepted.

Two methodology/reporting corrections were made:
1. The event z-score is relative to the preceding 30-day basis mean. Its positive/negative sign does not imply that the absolute perp/index basis is positive/negative or that the perpetual is absolutely rich/cheap.
2. The outcome now measures reduction in absolute distance from the fixed event-time prior-only 30-day mean: abs(basis_event - prior_mean_event) - abs(basis_future - prior_mean_event). This prevents a move that overshoots and ends farther from the reference from being mislabelled as reversion.
3. Split end-exclusive timestamps had a milliseconds-to-seconds conversion error in the report. The bar counts and index boundaries were correct, but the displayed end timestamps were 3 days 11 hours 15 minutes too late. A unit regression test and corrected conversion have been added.

The earlier signed-change results, confidence intervals and candidate decision are not valid for the accepted hypothesis and must not be used. Their raw run artifact is preserved in workflow 44880219010 for audit only.

**Corrected 12-month replay: pending.** No accepted event-study result or executable strategy result is currently available.
