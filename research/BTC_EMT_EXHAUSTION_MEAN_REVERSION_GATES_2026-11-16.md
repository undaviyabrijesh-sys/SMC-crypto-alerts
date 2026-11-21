# BTC EMT-inspired exhaustion event study — frozen decision-gate addendum

Date: 2026-11-16 UTC
Branch: ai-quant-rebuild
Parent preregistration: research/BTC_EMT_EXHAUSTION_MEAN_REVERSION_PREREGISTRATION_2026-11-16.md

This addendum freezes the first-stage decision thresholds before the historical market run. It does not alter the event definition or authorize parameter tuning.

## Sample and matching

- Split by chronological 5m row index: 70% development, 15% validation, final 15% untouched and not evaluated in this stage.
- A forward horizon must finish strictly inside its own sample; bars across gaps or sample boundaries are excluded.
- Accepted event entries use one global position at a time and an 8-hour cooldown across both directions.
- Controls are non-event 5m entry timestamps. Their contrarian direction is the opposite of the sign of the prior 12-bar return.
- Match 1:1 without replacement by exact UTC date, direction, completed 4h EMA50/EMA200 regime and 3-hour UTC time bucket. Exclude controls within 30 minutes of any confirmed event entry. Nearest timestamp wins; ties use the earlier control timestamp.
- Paired confidence intervals use a 2,000-replicate bootstrap clustered by UTC date, fixed seed 20261116.

## Frozen gate at 12 bps round-trip assumed cost

At least one of the two predeclared horizons (1h or 4h) must satisfy every condition in both development and validation:

- At least 100 development events and 30 validation events.
- At least 50 matched development pairs and 20 matched validation pairs.
- Mean event forward return after assumed 12 bps round-trip cost is positive.
- Mean paired event-minus-control lift is positive.
- The 95% day-cluster bootstrap lower confidence bound for paired lift is strictly above zero.
- At least 50% of active event months have positive summed net forward return.

If no horizon passes both chronological gates, reject or rethink this event definition. Do not tune the validation period and do not inspect the final 15% outcomes.

## Interpretation limits

This is a price-return event study, not a stop-defined trading system. R is not applicable. Forward-return metrics are not a deployable equity curve. Fees are flat assumptions; actual fee tier, spread, impact and funding cashflows are not verified. Funding is excluded. Even a gate pass only authorizes a separate, frozen stop/target execution study; it does not validate or promote a live strategy.

No production, main-branch, alert or order changes.
