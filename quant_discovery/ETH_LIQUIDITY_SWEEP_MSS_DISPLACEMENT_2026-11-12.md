# ETHUSD liquidity sweep + MSS + displacement with BTC 4h confirmation — 2026-11-12

<badge>REJECTED — validation failure</badge>

## Run and reproducibility

- GitHub Actions: [run 43119527053](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43119527053) — completed successfully; compile, causal BTC-context tests, 4,320-configuration matrix and artifact upload all passed.
- Artifact: [13900356463](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43119527053/artifacts/13900356463), SHA-256 `10cee05db4aac30845549dc0fe98975fee40b183cb78ab49ef7c953b7947b1a1`, expires 2026-12-11.
- Code: [backtest engine](../research/eth_liquidity_sweep_mss_displacement_intraday_backtest.py), [causality tests](../research/test_eth_liquidity_sweep_mss_displacement.py), [workflow](../.github/workflows/eth-liquidity-sweep-mss-displacement.yml).

## Data

- ETHUSD 15m: 70,079 rows, 2024-11-11 23:30 UTC to 2026-11-11 23:00 UTC, zero gaps.
- BTCUSD 15m confirmation source: 70,079 rows, same interval, zero gaps.
- ETH 1h complete bars: 17,519; BTC 4h complete bars: 4,379.
- Prepared ETH hash: `b20103d2de7d89af4f9c9472be5b64f4e6b902a596c2fecbcf912276d74dfbdf`.
- Prepared BTC hash: `cab51bb5bc23d11fc3fa5d14023ee75d1e6d0ca7b51d985412af3943171c3603`.
- Raw ETH 15m CSV SHA-256: `09a7a12cbbf1abea7fb26be24994ace754844d6128b0f75cd104fb106b14ea28`.
- Raw BTC 15m CSV SHA-256: `a21f6fb1e90c4dbabf19bae0df1a891e9549c7ce9eb89528dd3ba1fca2de348a`.

## Preregistered rules and matrix

ETH 15m execution; confirmed 1h external pivots (2/3 bars); 15m local pivots (2/3 bars); first MSS within 4/8 bars; five displacement definitions (none, directional MSS body >=0.5/0.75 ATR14, and each threshold plus close in directional outer quartile); next-15m-open entry; stop beyond full sweep excursion plus 0/0.1 ATR; 1.5R/2R/3R target; maximum hold 8h; stop-first same-candle ambiguity and adverse gap-through stop fill; one trade at a time per configuration.

HTF filters: none, completed ETH 4h EMA50/200, completed BTC 4h EMA50/200. Direction: both, long-only, short-only. Session: all hours or 07:00–19:00 UTC. Total 4,320 configurations. Assumed round-trip costs: 6/12/20bp; 12bp primary. No funding or separate spread/slippage applied.

BTC context is causal: only completed 4h bars are exposed; context expires after 6h, is invalidated across BTC 15m segment gaps, and requires the latest BTC 15m candle to be no older than 15m. Regression tests prove no 4h value is visible before close and old context stays invalid after a BTC gap until a new complete post-gap 4h bar.

Chronological split: 70% train, 15% validation, 15% reserved OOS. Train gate: >=40 trades, positive net R, PF>=1.05, max DD >=-25R. Validation gate: >=20 trades, positive net R, PF>=1.05, max DD >=-15R and >=50% positive active months. OOS is run once only after both gates pass.

## Selection outcome

- Displacement event counts: none 142; 0.5 ATR 132; 0.75 ATR 102; 0.5 ATR + outer-quartile close 95; 0.75 ATR + outer-quartile close 75.
- **139 training-eligible configurations**, all with no HTF filter; 25 shortlisted; **0 validation passes**. ETH 4h EMA and BTC 4h EMA filters each produced zero training-eligible candidates. No shortlisted candidate had positive validation net R. **OOS was not evaluated.**
- The best validation-only row was only 4 trades (+2.83R, 75% win rate, PF 3.632); this is far below the 20-trade minimum. Among validation rows with >=20 trades, the best was -3.65R over 20 trades, 40% wins, PF 0.671, max DD -4.90R.

### Top training selection-score candidate

Configuration: 1h external pivot 2; 15m local pivot 2; MSS window 4; no stop buffer; 3R target; 0.75 ATR directional MSS-body requirement; no HTF filter; both directions; 07:00–19:00 UTC.

| Metric | Train | Matching validation |
|---|---:|---:|
| Trades | 40 | 12 |
| Win rate | 55.00% | 25.00% |
| Profit factor | 1.881 | 0.148 |
| Net R | +12.30R | -7.94R |
| Average R/trade | +0.307R | -0.662R |
| Max drawdown | -3.56R | -9.01R |
| Max losing streak | 3 | 8 |
| Positive active months | 60% | 0% |
| TP / SL / TIME | 6 / 10 / 24 | 0 / 8 / 4 |

Validation monthly net R: April -0.06R, May -2.12R, June -4.53R, July -1.23R. Validation regime net R: bull -1.48R (4 trades), mixed/unavailable -0.80R (2), bear -5.67R (6).

### Cost sensitivity for this same candidate

| Round-trip cost | Train net R | Validation net R |
|---:|---:|---:|
| 6bp | +13.88R | -7.12R |
| 12bp | +12.30R | -7.94R |
| 20bp | +10.18R | -9.05R |

The result fails even at 6bp. Current public BTCUSD taker fees imply 10bp round-trip before slippage, but ETH/user-specific fee tiers were not verified; 12bp remains an explicit assumption, not a claim about the user's account.

## Decision

**Reject this mechanical ETH sweep/MSS/displacement model.** Its selected training setup lost 7.94R in validation with zero target hits, and every shortlisted configuration was negative in validation. BTC 4h confirmation did not improve the model; it reduced the candidate pool to zero training-eligible setups. Do not tune against this already-inspected validation segment and do not evaluate OOS.

This rejects only these exact causal pivot/MSS/displacement rules, thresholds, sessions, costs and execution assumptions. It does not prove that discretionary ETH SMC trading cannot work.

## Next research step

Do not add more EMA or displacement filters to this model. First complete the ETH contract-specific funding interval and post-2025-09-08 event-time funding mapping audit. Then preregister a separate funding/OI crowding-reversal hypothesis using only the documented post-change funding regime, lagged closed 1h OI, explicit funding-event snapshots, and a fresh chronological split. Keep historical funding out of P&L until the candle-to-settlement timestamp mapping is independently verified.
