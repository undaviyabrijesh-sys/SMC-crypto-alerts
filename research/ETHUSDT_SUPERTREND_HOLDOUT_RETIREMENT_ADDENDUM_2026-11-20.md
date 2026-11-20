# ETHUSDT Supertrend replication — holdout retirement addendum

Date: 2026-11-20

The original preregistration reserved the final 15% of the historical sample for OOS evaluation only after development and validation gates passed.

During an independent local preflight, a diagnostic split loop mistakenly materialized all three chronological segments before applying the gates. The final 15% was therefore accessed before the gate decision. Its metrics are intentionally omitted and must not be used for selection, promotion, or any OOS claim.

Corrective actions:
- The final 15% segment is now marked retired/contaminated.
- The committed replication wrapper has OOS evaluation hard-disabled for this study, regardless of development/validation results.
- The authoritative GitHub workflow will report development and validation only. It will not compute or report final-holdout performance.
- Any future confirmation must use a genuinely new period after the frozen archive end (2026-07-15 00:00 UTC exclusive), with a separate preregistration and no parameter changes.

This addendum preserves the original preregistration. It does not change the frozen indicator, entry, stop, target, holding cap, cost assumptions, funding exclusion, or development/validation gates.
