# Derivatives Archive Integrity and Funding Semantics Audit — 2026-11-06

## Scope and reproducibility

This is a data-integrity and schema audit, not a strategy backtest and not evidence of a trading edge.

- Source: GitHub Actions artifact from [run 41955898516](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/41955898516), artifact ID `13383865992`.
- Artifact name: `salty-quant-derivatives-3y-41955898516`.
- Downloaded for this audit on 2026-11-06; GitHub reported `expired=false` and expiry `2026-11-19T02:37:57Z`.
- ZIP SHA-256 independently recomputed: `f16d0bc18eddcce7637c9643d9176590c8bb55fe9de6be1da9c717bdf7949a27`.
- `archive_validation.json`: status `passed`, 9 expected/actual datasets, 758,119 total candles, no collector errors.
- All nine CSV row counts and SHA-256 values independently match `manifest.json`.
- Source venue/API: Delta Exchange India `/v2/history/candles`; raw API values are retained without scaling.

## Dataset coverage

| Dataset | Rows | First UTC | Last UTC | Observed coverage / gaps |
|---|---:|---|---|---|
| BTC funding 1h | 25,170 | 2023-12-18 13:00 | 2026-11-05 01:00 | 99.6398%; 13 gaps; max 8h |
| BTC mark 5m | 303,136 | 2023-12-18 13:10 | 2026-11-05 02:25 | 100%; no gaps |
| BTC OI 1h | 24,961 | 2023-12-29 13:00 | 2026-11-05 01:00 | 99.8560%; 1 gap; max 37h |
| ETH funding 1h | 24,002 | 2024-02-05 12:00 | 2026-11-05 01:00 | 99.6512%; 12 gaps; max 8h |
| ETH mark 5m | 289,038 | 2024-02-05 12:00 | 2026-11-05 02:25 | 100%; no gaps |
| ETH OI 1h | 24,066 | 2024-02-06 08:00 | 2026-11-05 01:00 | 100%; no gaps |
| XAUT funding 1h | 4,829 | 2026-04-17 12:00 | 2026-11-05 01:00 | 99.8140%; 3 gaps; max 4h |
| XAUT mark 5m | 58,077 | 2026-04-17 10:45 | 2026-11-05 02:25 | 100%; no gaps |
| XAUT OI 1h | 4,840 | 2026-04-17 10:00 | 2026-11-05 01:00 | 100%; no timestamp gaps |

XAUT begins only in April 2026 and is not a three-year sample. BTC/ETH funding and BTC OI contain gaps; any event replay must preserve those gaps and reject incomplete holding windows.

## Raw funding-series diagnostics

The following statistics use each CSV's `close` column exactly as stored; no unit conversion is applied.

| Series | Rows | Min | Median | 99th percentile | Max | Negative rows |
|---|---:|---:|---:|---:|---:|---:|
| BTC funding 1h | 25,170 | -0.26877229 | 0.01000000 | 0.03183017 | 0.49706960 | 1,513 |
| ETH funding 1h | 24,002 | -0.25852825 | 0.01000000 | 0.03319741 | 0.95000000 | 1,760 |
| XAUT funding 1h | 4,829 | 0.00500000 | 0.00500000 | 0.00500000 | 0.005268365 | 0 |

These are raw values, not cashflow. The BTC/ETH negative observations are retained; do not clamp them to zero. XAUT's short sample and nearly constant series need additional validation before any regime inference.

## Funding semantics: unresolved before P&L attribution

Official Delta references:
- [Historical OHLC candles API](https://docs.delta.exchange/): identifies `FUNDING:${symbol}`, `MARK:${symbol}` and `OI:${symbol}` symbol prefixes for `/v2/history/candles`, but the generic OHLC response schema does not state the funding candle's unit or settlement meaning.
- [Funding-rate WebSocket channel](https://docs.delta.exchange/): sample payload includes `fr: 0.01`, `fi: 28800` and `nfr` (next funding realization timestamp).
- [Delta India perpetual-contract guide](https://guides.delta.exchange/delta-exchange-india-user-guide/derivatives-guide/docs): describes funding as an 8-hour rate for the illustrated contract, gives interest-rate example 0.01%/8h, and explains the funding payment formula.
- [Funding mechanism update](https://deltaexchange.freshdesk.com/support/solutions/articles/80001014551-summary-of-changes-made-to-funding-mechanism-for-perpetual-contracts): describes the funding-rate formula and 0.01%/8h interest-rate setting.

The references suggest the displayed `0.01` convention is percent-denominated rather than a decimal fraction, but they do not by themselves prove that every historical `FUNDING:` candle's OHLC values use the same scale or establish the exact event-time semantics for each archived contract. Do not multiply position notional by these raw hourly closes, sum them hourly, or divide by 100 in production/research code until this is cross-validated against contract metadata, `fi`, `nfr` and an independently observed realized funding record.

Funding may accrue at a finer cadence than the hourly archive. A defensible funding-aware replay must establish:
1. Contract-specific funding interval and next-realization timestamps.
2. The exact unit/scale and sign convention of historical funding candles.
3. Which rate applies to each funding accrual/realization interval.
4. Position notional basis (mark/index/contract value) and exposure at each event.
5. Treatment of missing funding observations and contract changes.

Until then, funding remains explicitly unavailable for realized P&L attribution. Keep the existing adverse-carry stress assumption labelled as a stress scenario, not measured funding.

## Research implications

- Mark-price series are continuous within their observed spans and can support mark-based valuation experiments, but they are not executable fills.
- The archive contains no order-book depth or executable spread/market-impact history. Keep spread/slippage as explicit stress scenarios.
- Do not infer liquidity from OI or funding alone; they are positioning/carry context.
- Do not backfill funding/OI gaps, silently set unknown costs to zero, or claim funding-adjusted profitability.
- This audit does not alter EXP-001 or OI-expansion decisions. All previously rejected candidates remain rejected and `APPROVED_STRATEGIES` remains empty.

## Next research steps

1. Retrieve contract metadata and confirm per-contract funding interval/units.
2. Cross-check historical funding-candle values against a current funding-rate sample and a known realized funding event without exposing credentials.
3. Implement event-time funding attribution only after the above checks; add unit, sign, negative-rate, missing-event and boundary regression tests.
4. Re-run chronological train/validation/OOS and walk-forward screens with mark-price valuation, explicit spread/slippage stress, and validated funding.
5. Preserve the raw archive and manifest in durable storage before the GitHub artifact expiry; this audit file records hashes but does not embed the 60 MB of CSV data.
