# BTCUSDT USD-M premium/index-basis availability audit

**Classification: data audit only — no signal or trading backtest.**

- Monthly archive: 2026-10; daily archive: 2026-11-19; interval: 5m.
- Aligned 5m rows: 9216.

## Archive coverage

| Series | Period | Rows | Expected | Gaps | SHA-256 / ZIP CRC |
|---|---|---:|---:|---:|---|
| contract | monthly | 8928 | 8928 | 0 | 31dcc9c67516… / passed |
| contract | daily | 288 | 288 | 0 | f117faafd86b… / passed |
| index | monthly | 8928 | 8928 | 0 | c31c55be9701… / passed |
| index | daily | 288 | 288 | 0 | 1892f89eed08… / passed |
| mark | monthly | 8928 | 8928 | 0 | 78c6c5d7e789… / passed |
| mark | daily | 288 | 288 | 0 | 7bc9ee418b04… / passed |
| premium | monthly | 8928 | 8928 | 0 | 31f5c38ede86… / passed |
| premium | daily | 288 | 288 | 0 | da964179a5e9… / passed |

## Four-series timestamp alignment

- monthly: common=8928, union=8928, missing-from-any-series=0, common coverage=100.000%.
- daily: common=288, union=288, missing-from-any-series=0, common coverage=100.000%.

## REST archive cross-check

- contract: unavailable; HTTP=451; matched rows=—; exact close matches=—; max close difference=—.
- index: unavailable; HTTP=451; matched rows=—; exact close matches=—; max close difference=—.
- mark: unavailable; HTTP=451; matched rows=—; exact close matches=—; max close difference=—.
- premium: unavailable; HTTP=451; matched rows=—; exact close matches=—; max close difference=—.

## Recent direct basis endpoint

- Status: unavailable; HTTP=451; rows=—; arithmetic pass=—; documented availability: latest 30 days only.
- Error: {
  "code": 0,
  "msg": "Service unavailable from a restricted location according to 'b. Eligibility' in https://www.binance.com/en/terms. Please contact customer service if you believe you received this message in error."
}

## Derived features (not interchangeable)

- perp_index_basis_bps: min=-18.742991, p05=-6.5251767, median=-4.5480353, p95=-2.2471609, max=8.0313889
- mark_index_premium_bps: min=-9.6274664, p05=-5.942852, median=-4.3282415, p95=-2.2610849, max=3.6887218
- premium_index_native: min=-0.00175046, median=-0.000453035, max=0.00050647

Direct perp/index basis uses contract close versus index close. Mark/index premium uses mark close versus index close. Premium-index close is retained in native units and is not assumed to equal either price ratio.

## Decision

This audit establishes only availability and alignment for the tested pilot archives. A separate event study is permitted only if archive coverage and semantics are satisfactory. No predictive edge, strategy, trade PnL, fees, funding cashflow, win rate, PF, R, drawdown, or execution result is claimed.

REST HTTP/network failures are recorded as unavailable and do not invalidate a checksum-verified archive. The /futures/data/basis endpoint is a recent reference only and must not be extrapolated beyond its documented 30-day window.
