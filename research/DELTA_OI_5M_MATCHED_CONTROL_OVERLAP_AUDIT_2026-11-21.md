# Delta BTC/ETH 5m OI event-study matched-control overlap correction

Date: 2026-11-21 UTC  
Parent event-study workflow: [44768774326](https://github.com/undaviyabrishesh-sys/SMC-crypto-alerts/actions/runs/44768774326)

## Why a rerun is required

The original descriptive event study selected the nearest non-event control within +/-24 hours, matched on split, 5m price direction, prior-24h regime and training-defined absolute-price-return decile. It prevented reusing the exact same control timestamp, but did not prevent overlapping 4h outcome windows.

An independent audit of the completed artifact found:
- BTC: 2,753 pairs; 89.03% of controls were within four hours of the paired event.
- ETH: 2,965 pairs; 89.61% of controls were within four hours of the paired event.

Because both event and control forward outcomes are measured from their respective timestamps over four hours, these pairs frequently shared the same underlying price path. The original paired-lift estimates are superseded.

## Frozen corrected matching rule

Keep the original event definition and all event data unchanged:
- Delta BTCUSD and ETHUSD OI-prefixed 5m candles plus traded-price 5m candles.
- Main event: absolute 5m OI close-to-close change >=5%, 60-minute cooldown.
- Event time is 5m candle close availability.
- Outcomes remain 15m, 1h and 4h forward traded-price changes.
- Chronological 70/15/15 split and split-safe four-hour horizons.
- Matching strata remain same split, same current 5m price direction, same prior-24h regime and same training-defined absolute-return decile.
- Nearest eligible control remains within +/-24 hours; controls are not reused.

New non-overlap constraints:
1. A control timestamp must be at least 4h05 from every main-event timestamp. This ensures its four-hour forward-return window does not overlap any main-event four-hour outcome window, with one 5m bar of separation.
2. Selected control timestamps must be at least 4h05 apart from one another, preventing selected control forward windows from overlapping.
3. If no control satisfies all constraints, leave that event unmatched; do not relax the guard.

## Uncertainty reporting

For each asset, split and horizon, calculate a 5,000-replicate UTC event-day cluster bootstrap interval for the mean paired event-minus-control return. Report pair count, event-day count, mean/median lift, event-beats-control fraction and 95% interval. These intervals are descriptive, not p-values and not multiplicity-adjusted across the full threshold/cooldown screen.

## Interpretation limits

This remains a descriptive event study, not an executable trading strategy. It does not produce win rate, PF, net R, trading drawdown or losing streak. No costs or funding cashflows are applied. Matched controls can retain unobserved confounding, and event observations themselves can have overlapping forward windows; UTC event-day clustering is used to reflect intraday dependence.

Delta OI is venue-specific base-asset OI per the earlier unit reconciliation. Binance USD-M OI cross-venue verification was unavailable in the parent run because the public OI endpoint returned HTTP 451 from the GitHub runner. Do not interpret Delta-specific OI changes as market-wide positioning.

No threshold changes, parameter optimisation, validation selection or strategy promotion are allowed in this correction.
