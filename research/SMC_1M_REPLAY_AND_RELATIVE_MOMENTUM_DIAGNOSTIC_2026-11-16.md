# BTC research audit — 2026-11-16

Branch: `ai-quant-rebuild`  
Scope: research-only; no production, alert or order changes.

## 1. SMC 1-minute execution replay — reconciliation completed

Authoritative workflow: [43728760236](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43728760236), artifact 14166719558.

### Data integrity

- Native BTCUSD 5m traded-price data: 210,240 rows, 2024-11-15 15:15 UTC to 2026-11-15 15:10 UTC, zero 5m gaps; SHA-256 `6d2e29c38008af117741f26e17f475866dc8b14557effd16c37372bc1e836643`.
- BTCUSD 1m traded-price data: 1,051,199 valid rows from 1,051,200 source rows, 1,959 zero-volume rows, no duplicates or invalid OHLC rows, zero missing-minute gaps, 100% observed-minute coverage; SHA-256 `8d805932ea35405cfa10faf96f6920f4c87e344da494a48534bc9148069fe1b2`.
- 210,239 complete 1m-derived 5m bars were compared with 210,239 native 5m bars. Exact OHLC agreement was 99.98240098%; 37 bars (0.0175995%) differed. The largest absolute difference was $939 in the open at 2025-08-22 15:05 UTC; high, low and close matched on that bar.
- One distinct mismatched bar fell inside two candidate trade records (the same market trade evaluated under two stop/target candidates). Only the open differed. Both possible opens remained between the applicable stop and target; the trade outcome was unaffected.

### Trade replay

- 240 candidate trade records across the two frozen candidates: 240/240 resolved using 1m bars.
- 240/240 outcome labels matched the original 5m replay.
- Zero exit-price differences, zero gross-R differences, zero ambiguous 1m stop/target bars and zero entry-open mismatches above 0.01%.
- The prior update incorrectly described a 28-minute 1m data gap. The authoritative corrected artifact reports zero missing-minute gaps; that earlier gap statement is withdrawn.

The 1m replay therefore confirms that finer exit sequencing does not rescue the tested SMC setup. It does not prove the entire 1m and 5m feeds are identical; the 37 OHLC discrepancies remain a feed-reconciliation issue.

### Frozen candidate performance at 12 bps assumed round-trip cost

| Sample | Trades | Win rate | PF | Net R | Max DD | Longest loss streak |
|---|---:|---:|---:|---:|---:|---:|
| Development | 97 | 51.55% | 1.408 | +11.340R | -3.158R | 5 |
| Validation | 23 | 39.13% | 0.853 | -1.232R | -5.158R | 6 |

Validation sensitivity: +0.434R at 6 bps, -1.232R at 12 bps and -3.454R at 20 bps. The separately inspected 2R diagnostic lost -0.689R in validation at 12 bps. The strategy remains rejected; untouched OOS was not evaluated.

## 2. BTC/ETH intraday relative-momentum diagnostic

Frozen source study: [workflow 43752078487](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43752078487), artifact 14176194941. The diagnostic below does not change the tested rules.

- Data: 70,127 aligned 15m candles per asset, 2024-11-13 23:30 UTC to 2026-11-14 11:00 UTC; no missing common timestamps.
- 36 configurations were tested. At 12 bps, zero configurations had positive net return in development and zero in validation. No OOS was authorised.
- Least-bad development configuration: 4h relative-strength lookback, 0.50% spread threshold, 4h hold, equal-dollar pair (long stronger / short weaker): 1,121 trades, 35.86% win rate, PF 0.636, net -61.58%, max DD -62.52%, 15-loss streak.
- Same frozen configuration in validation: 156 trades, 28.21% win rate, PF 0.384, net -15.10%, max DD -15.34%, 9-loss streak.

### Leg contribution diagnostic

For the frozen pair configuration, before costs:

| Per-trade mean contribution | Development | Validation |
|---|---:|---:|
| Long leg contribution | +2.08 bps | -3.81 bps |
| Short leg contribution | +1.53 bps | +5.36 bps |
| Pair gross return | +3.61 bps | +1.55 bps |

At 12 bps, the pair's mean gross edge is smaller than assumed round-trip cost in both periods. Even at 6 bps, validation net return is -6.77%. The long leg also reverses from positive development contribution to negative validation contribution. This is a cost-insufficient and unstable effect, not a candidate for further parameter tuning.

Decision: reject this relative-momentum family as tested.

## 3. Next research step

The next candidate is the preregistered BTC 5m EMT-inspired exhaustion/rejection/confirmation event study. Its decision thresholds are frozen in [the gate addendum](BTC_EMT_EXHAUSTION_MEAN_REVERSION_GATES_2026-11-16.md). It must be implemented and tested as a matched event study before any stop/target grid. No EMT performance result is claimed in this report.

All findings remain experimental. No strategy was promoted; `APPROVED_STRATEGIES`, `main`, live alerts and exchange orders remain untouched.
