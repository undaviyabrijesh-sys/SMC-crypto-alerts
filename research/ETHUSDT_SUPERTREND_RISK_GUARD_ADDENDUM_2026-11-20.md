# ETHUSDT Supertrend replication — inherited simulator risk guard addendum

Date: 2026-11-20

Code inspection of the reused BTC Supertrend simulator confirmed an existing execution guard: skip any signal with non-positive initial stop risk or initial stop distance greater than 5% of entry price. This guard is inherited from the existing simulator; it is not a new parameter search or an ETH-specific optimization.

The wrapper now records all signals rejected by this guard in risk_guard_excluded_signals.csv and includes the count in summary.json. The frozen ETH baseline remains unchanged otherwise. The local preflight had three such exclusions among the 500 funding-safe signals.

This addendum clarifies an inherited source-engine rule omitted from the original preregistration prose. It does not alter the indicator, signal, stop, target, 4h maximum hold, funding-boundary exclusion, costs, or development/validation gates.
