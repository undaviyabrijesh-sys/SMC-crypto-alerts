# BTC prior-UTC-day candle-volume profile proxy rejection → POC — preregistration (2026-11-17)

## Status

Preregistered next candidate only. No historical result exists yet. Research-only; no production changes or execution alerts.

## Prior-art audit

The `ai-quant-rebuild` research directory was searched for `value area`, `volume profile`, `point of control`, `market profile` and `POC`; no existing value-area/POC implementation was found. Existing VWAP, prior-day range break/retest, support/resistance rejection and squeeze-breakout studies are related but do not use a prior-day volume-at-price proxy and POC target.

## Hypothesis

A rejection of the prior UTC day's high-volume value boundary, followed by a return inside value, may mean-revert toward the prior day's point of control (POC). This is a hypothesis about a **candle-volume profile proxy**, not true exchange volume-at-price.

## Data

- Instrument: Delta BTCUSD perpetual traded-price 5m OHLCV.
- Source: existing archived 5m dataset used by the PDRT study, artifact [14221154137](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43857702736/artifacts/14221154137).
- Use complete UTC days only: exactly 288 consecutive 5m bars with no gap; incomplete days produce no profile.
- Chronological 70/15/15 development/validation/untouched OOS split, aligned to UTC 4h boundaries. OOS is not loaded into feature construction and is not evaluated unless all frozen development and validation gates pass.
- Validate duplicate timestamps, malformed OHLC, missing bars, zero-volume bars and profile days before running.

## Prior-day profile construction (fixed primary)

1. For each completed prior UTC day, create 48 equal-width price bins between that day's low and high.
2. For each 5m candle, distribute its reported candle volume equally across every bin intersected by that candle's `[low, high]` range. If `high == low`, allocate the full candle volume to the containing bin.
3. POC is the centre of the bin with the highest allocated volume; ties resolve to the lower-price bin.
4. Starting at POC, expand a contiguous value area until at least 70% of the allocated volume is included. At each step, add the higher-volume adjacent bin; ties resolve lower. VAH is the upper edge and VAL the lower edge of the included bins.
5. Freeze the prior-day POC/VAH/VAL for the entire next UTC day. Do not use any current-day candle volume to update the levels.

This allocation is only an OHLCV approximation. It cannot reproduce actual trade-by-price distribution and must never be labelled a true exchange POC/volume profile.

## Signal and entry rules

Use Wilder ATR(14) on completed 5m candles, shifted one bar.

- Short VAH rejection: current 5m high reaches at least `VAH + 0.05 * prior_ATR`, then closes below VAH and at/below its candle midpoint.
- Long VAL rejection: current 5m low reaches at least `VAL - 0.05 * prior_ATR`, then closes above VAL and at/above its candle midpoint.
- Enter at the next 5m open only if the open remains back inside the value area and POC remains a favourable target (POC below short entry / above long entry).
- Require POC reward distance to be at least 1.0 initial risk; otherwise skip the POC-target trade.
- At most one long and one short signal per UTC day; one global position at a time per target configuration.

## Stops, targets and exits

- Stop: beyond the rejection candle extreme by `0.10 * prior_ATR`.
- Primary target: prior-day POC.
- Diagnostics: fixed 1.5R, 2R and 3R targets using the same entry and stop.
- Maximum hold: four hours.
- Close at the last completed 5m close strictly before the next UTC 00:00/08:00/16:00 funding boundary. Funding cashflows are excluded; positions must not cross settlement.
- Same-bar stop/target: stop first. Stop gap-through fills at the worse opening price; target gaps fill at target. Missing-bar paths are unresolved and excluded from performance selection.

## Costs and metrics

- Round-trip cost sensitivities: 4, 7, 10 and 20 bps; 10 bps primary. Apply fees to entry and exit notionals. Actual user fee tier is unverified.
- No separate spread, slippage or market-impact model in the primary run; disclose this limitation.
- Report candidates, executed trades, long/short counts, win rate, PF, gross/net R, max drawdown in R, maximum losing streak, TP/SL/time exits, active positive months, monthly results, 4h regime attribution and cost sensitivity.
- R is not applicable to the POC forward-event diagnostic if a separate event study is reported; trade metrics must use the explicit stop/target simulation.

## Frozen acceptance gate

The POC-target primary must have at least 50 development trades and 20 validation trades, positive net R and PF >=1.05 in both, maximum trade-sequence drawdown no worse than -20R development/-10R validation, and at least 50% positive active months in each. The 2R diagnostic must not materially contradict the POC result. If either sample is underpowered or a gate fails, reject/hold and do not inspect OOS or tune validation.

## Implementation checks

Before market results, pass deterministic tests for complete 288-bar UTC days, profile bin allocation and tie-breaking, 70% contiguous value-area expansion, prior-day-only profile availability, no-current-day-volume perturbation, next-open entry, one-signal-per-side/day, stop-first/gap handling, funding-safe exit, missing-bar handling and split isolation.

## Known limitations

- 5m OHLCV candle volume is spread uniformly across each candle's price range; actual intrabar volume distribution is unknown.
- The profile is an approximation and may be materially different from tick-level volume-at-price.
- Funding is excluded by closing before settlement; spread/slippage/market impact are not separately modeled.
- The experiment is not approved for live signals, production rules or orders.


## Post-run prior-art correction (2026-11-17)

The initial prior-art audit above was incomplete. The repository already contains `research/orderflow_profile_backtest.py`, which implements the same broad 48-bin prior-UTC-day candle-volume proxy, 70% value area, VAH/VAL rejection, 0.05 ATR penetration, next-5m-open entry, rejection-extreme stop +0.10 ATR and 4h cap. Its `VP_ONLY` model tests fixed 1.5R/2R/3R exits. The new Delta study therefore tests a **POC-target exit variation**, not an independent strategy family.

The existing Binance USD-M VP_ONLY results are in `quant_discovery/ORDERFLOW_ZONE_BACKTEST_LATEST.md`. They are strongly negative for BTC and ETH at the 2R/10bp primary comparison. This prior art was missed in the first audit and is now explicitly incorporated into the research ledger. The frozen POC-target rules were not changed after the run.
