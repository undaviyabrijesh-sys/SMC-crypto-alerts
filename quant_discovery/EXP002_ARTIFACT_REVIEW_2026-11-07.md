# EXP-002 result artifact review — 2026-11-07

## Provenance

- GitHub historical archive workflow: [run 42340120427](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42340120427), completed successfully.
- Research-result artifact: `salty-quant-strategy-research-42340120427`, artifact ID `13561148256`; downloaded and inspected on 2026-11-07.
- Source outputs: `exp001/oos_summary.csv`, `exp002/exp002_oos_summary.csv`, `exp002/exp002_oos_trades.csv`, `exp002/exp002_split_and_cost_summary.csv`, and `exp002/exp002_walk_forward_summary.csv`.
- EXP-002 contains 42 OOS asset × timeframe × strategy cells (7 additional hypotheses × BTC/ETH/XAUT × 15m/1h), and 8,191 shadow trades in its OOS trade table.
- Baseline costs are 10 bps round trip plus the EXP-001 1 bp per 8h adverse carry stress. Cost stress comparisons are 20 and 40 bps round trip. These are assumptions, not measured fills, historical bid/ask or realized funding cashflows.

## EXP-001 baseline

All 30 OOS asset × timeframe × family cells were negative at baseline costs. The least-negative row in this exact artifact was BTC 1h mean reversion: 177 trades, win rate 39.55%, net expectancy -0.0205R, PF 0.969, max drawdown -18.078R, seven consecutive losses. This artifact's figures supersede earlier handoff snippets that cite a 176-trade variant.

## EXP-002 expanded screen

Four of 42 OOS cells were slightly positive at 10 bps; all four became negative at 20 and 40 bps. None demonstrated robust cost tolerance.

| Cell | OOS n | Win rate | Net expectancy | PF | Max DD | Longest loss streak | Train expectancy | Validation expectancy | OOS at 20 bps | OOS at 40 bps | Positive chronological test windows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC 1h EMA crossover | 44 | 43.18% | +0.0658R | 1.098 | -11.644R | 10 | -0.3300R | -0.3060R | -0.1287R | -0.5177R | 1/5 |
| ETH 1h Bollinger squeeze breakout | 48 | 41.67% | +0.0516R | 1.075 | -7.931R | 6 | +0.0484R | +0.4324R | -0.1323R | -0.5001R | 3/5 |
| ETH 1h stochastic trend pullback | 182 | 42.86% | +0.0500R | 1.080 | -21.661R | 9 | -0.1650R | -0.1566R | -0.0781R | -0.3342R | 1/5 |
| ETH 1h ADX/DMI trend | 125 | 41.60% | +0.0191R | 1.029 | -12.665R | 6 | -0.1038R | -0.2390R | -0.1326R | -0.4358R | 2/5 |

## Decision

- Reject all EXP-001 and EXP-002 candidates for promotion. The four positive EXP-002 baseline rows are small/fragile and cost-sensitive; train/validation results are negative for three of four, and only the ETH squeeze candidate was positive in three of five sequential test windows.
- ETH 1h Bollinger squeeze may be retained as a **new hypothesis for future confirmation only**, not as an edge. Any fresh hypothesis must be frozen before access to another untouched chronological dataset.
- No post-hoc parameter or regime search on this same OOS set is allowed to rescue these rows. Re-run candidates on new untouched windows and broader cost assumptions before reconsideration.
- No change to production strategy allowlist or alerts. `APPROVED_STRATEGIES` remains empty.

## EXP-003 next evaluation

EXP-003 was added after this artifact was generated. The newer archive workflow has been extended to generate a fresh EXP-001/002/003 result artifact in one reproducible run. Inspect the new run before making any claim about selector performance. EXP-003's online selectors are research-only and are tested against EXP-002 shadow trades, not a live trading ledger.
