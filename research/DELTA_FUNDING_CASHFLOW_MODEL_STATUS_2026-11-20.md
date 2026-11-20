# Delta BTCUSD/ETHUSD funding cashflow model status — 2026-11-20

## Decision

**Funding cashflow remains unmodeled in Delta strategy PnL.** The official documentation now makes the mechanism transition clearer, but the historical rate-to-settlement mapping, pre-transition per-minute allocation, and payment-price basis are not yet fully reconciled. Do not apply a single two-year funding formula to BTCUSD or ETHUSD.

## Documented mechanism timeline

### 2024-05-03 mechanism notice

Delta's 3 May 2024 notice says:
- Funding-rate computation changed to an 8-hour TWAP-based formula.
- The rate became fixed within each 8-hour block.
- Funding continued to be exchanged between longs and shorts every minute.
- The notice gives a 0.01%/8h interest-rate example and a 0.1%/8h cap for most contracts at that time.

Official source: https://global.delta.exchange/support/solutions/articles/80001014551/

The notice does **not** specify the exact per-minute cashflow allocation formula. Dividing an 8-hour rate by 480 minutes is a plausible mathematical inference, not a documented or independently verified rule. It must remain a diagnostic hypothesis and must not be applied to historical strategy PnL.

### 2025-09-08 mechanism transition

Delta's current India perpetual-contract guide says the new method became effective at 5:30pm IST on 8 September 2025 (12:00 UTC):
- Open positions are snapshotted at the funding exchange.
- Funding is exchanged once per 8-hour settlement at 00:00, 08:00 and 16:00 UTC for the standard schedule.
- If a position is not in the snapshot, it does not pay or receive funding.
- Payment is current position value multiplied by funding rate.
- The guide defines current position value using the underlying index price.
- It notes that some contracts can use 4/2/1-hour intervals.

Official source: https://guides.delta.exchange/delta-exchange-india-user-guide/derivatives-guide/docs.md

## Historical archive evidence already inspected

Source artifact: [Delta funding semantics audit, workflow 43671994620](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43671994620), artifact [14145011170](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43671994620/artifacts/14145011170).

- BTC and ETH each contain 17,531 hourly funding observations from 2024-11-14 16:00 UTC to 2026-11-15 02:00 UTC, with eight 5-hour gaps.
- Funding OHLC is flat within each hourly observation.
- BTC has 2,191 complete 8-hour blocks, all flat.
- ETH has 2,190 of 2,191 complete blocks flat; one pre-transition off-grid change at 2024-11-29 09:00 UTC remains flagged.
- Observed rate updates align with 00:00/08:00/16:00 UTC, plus the 2025-09-08 12:00 UTC transition update.
- Raw rate values have median absolute value 0.01. The guide's examples use 0.01% (which would be 0.0001 as a decimal rate), but the historical candle schema does not declare the unit explicitly.

## Remaining blockers

1. **Pre-transition minute cashflow:** 2024-05-03 through 2025-09-08 used minute-by-minute exchange while the 8-hour rate was held flat. The exact per-minute allocation, valuation timestamp and rounding are not documented in the inspected sources.
2. **Post-transition rate-to-settlement alignment:** hourly FUNDING candles are flat within blocks and change at boundaries, but the historical candle does not contain the WebSocket next-funding-realization field. The rate at the boundary versus the immediately preceding block must be reconciled before selecting the charge for a settlement.
3. **Price basis:** the current India guide describes position value using underlying index price, while current product metadata exposes funding_method=mark_price. This may describe rate construction rather than payment notional, but that interpretation has not been verified.
4. **Historical interval changes:** the guide allows 4/2/1-hour intervals for some contracts. A hard-coded 8-hour schedule must not be applied universally without contract-specific history.
5. **Realized cashflow validation:** no independent historical position/cashflow ledger is available in this research run to reconcile a reconstructed payment amount.

## Safe interim policy

- Mark Delta perpetual backtests as funding_unmodeled until the applicable period and contract semantics are verified.
- Do not silently subtract a guessed 8-hour rate or a guessed rate/480 per-minute amount.
- If a post-transition diagnostic is produced, report both candidate rate alignments and index-vs-mark valuation as separate sensitivities; do not label either as authoritative PnL.
- Keep the Binance ETHUSDT actual funding cashflow audit separate: Binance supplies event-level fundingTime, fundingRate and markPrice, and that model must not be copied onto Delta contracts.
- No strategy validation gate may pass solely on funding-excluded PnL when funding exposure is material.

## Next verification step

Use the archived Delta FUNDING:BTCUSD / FUNDING:ETHUSD series together with 1-minute MARK and underlying INDEX candles around settlement boundaries. Reconcile:
- the last pre-boundary funding observation versus the boundary-hour observation;
- the current WebSocket fr/nfr semantics;
- the guide's index-price payment basis versus product metadata;
- the pre-transition 1/480 diagnostic against any independently available realized-cashflow example.

If the evidence still cannot identify a unique mapping, retain explicit lower/upper funding bounds and leave funding out of the authoritative net-PnL result.

## No production changes

This is a research-methodology status note only. No strategy rules, live alerts, production code or main branch were changed.
