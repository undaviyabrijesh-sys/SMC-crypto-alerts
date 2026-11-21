# Order-flow V2 holdout exposure amendment — 2026-11-17

The V1 BTC/ETH order-flow report already displayed metrics for the final 15% partition. That means the same calendar-date OOS partition is **not a fresh untouched holdout** for the corrected V2 implementation, even though V2 changes only implementation details to match the frozen specification.

Rules for interpreting V2:
- Development and validation results may be used only to determine whether the original V1 conclusions were implementation-sensitive; do not tune thresholds, stops, targets, or filters from this replay.
- The final 15% may be reported only as a previously exposed descriptive diagnostic. Do not call it an untouched OOS test, use it for model selection, or claim independent out-of-sample confirmation.
- Any future confirmatory test requires a new, prospectively frozen date window that has not been inspected, or genuinely independent new data collected after this amendment.
- This amendment does not alter the signal hypothesis or execution rules.

The V2 summary generator was amended to label the final partition as previously exposed and not a fresh holdout.
