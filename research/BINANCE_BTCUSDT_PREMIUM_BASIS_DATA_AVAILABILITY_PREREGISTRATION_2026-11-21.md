# BTCUSDT USD-M premium/index-basis data availability audit — preregistration 2026-11-21

## Purpose and scope

Prior-art review of research/ and quant_discovery/ found no existing historical Binance USD-M premium-index/index-price/mark-price basis dataset or event study. Existing funding-sentiment work uses funding-rate observations, not the premium-index kline series. The completed Delta OI event study is closed and will not be retuned.

This is a data availability and semantic reconciliation audit only, not a predictive event study or trading backtest. No strategy thresholds, entries, stops, targets, or PnL will be tested.

## Authoritative source definitions

- Contract price: USD-M /fapi/v1/klines and matching public archive klines.
- Index price: /fapi/v1/indexPriceKlines / indexPriceKlines archive.
- Mark price: /fapi/v1/markPriceKlines / markPriceKlines archive.
- Premium index: /fapi/v1/premiumIndexKlines / premiumIndexKlines archive.
- Independent recent basis reference: /futures/data/basis, pair=BTCUSDT, contractType=PERPETUAL, period=5m. Official documentation states this endpoint only exposes the latest 30 days; it cannot supply a two-year historical series.

Important distinction: the premium-index kline is a separate series from direct contract-price/index-price basis and from mark-price/index-price premium. Do not equate them. Compute separately:
- last-traded perp/index basis bps = 10,000 × (contract close / index close − 1);
- mark/index premium bps = 10,000 × (mark close / index close − 1);
- premium-index close in its native decimal units.

## Frozen pilot window

- Symbol: BTCUSDT USD-M perpetual.
- Interval: 5m.
- Monthly archive: 2026-10.
- Daily archive: 2026-11-19 (daily archive should be available on the following UTC day).
- Series: contract klines, indexPriceKlines, markPriceKlines, premiumIndexKlines.
- Each archive must be downloaded with its sibling .CHECKSUM; verify SHA-256 and ZIP CRC before parsing.
- Expected complete-bar counts: 8,928 for October 2026 and 288 for 19 November 2026 per series. Report gaps/duplicates rather than filling or interpolating.
- Compare common open timestamps across all four series.
- Where Binance REST is reachable, compare each daily archive to its corresponding REST kline endpoint. A 451/network restriction is recorded as unavailable, not treated as evidence that the archive is missing.
- Query the recent /futures/data/basis endpoint for up to 500 5m observations. Verify basis = futuresPrice − indexPrice and basisRate = basis / indexPrice within numeric tolerance. Record that this endpoint is limited to the latest 30 days.

## Acceptance criteria for proceeding to a separate event study

All four historical archive types must be retrievable for both pilot periods, checksums and CRCs must pass, schemas/timestamps must validate, and the four series must align sufficiently to quantify coverage. The direct basis endpoint must pass its internal arithmetic check if reachable. If it is unavailable, the archive-derived basis can still be studied, but the API cross-check is marked unavailable.

A later event study requires a separate preregistration. No signal definition or threshold is selected in this audit.

## Reproducibility

Implementation: research/binance_btcusdt_premium_basis_availability_audit.py
Workflow: .github/workflows/binance-btcusdt-premium-basis-availability-audit.yml
Outputs: manifest JSON, archive/REST coverage CSV, aligned 5m feature sample CSV, and report Markdown under quant_discovery/.

No main-branch, production, alert, paper-trade, or exchange-order changes are permitted.
