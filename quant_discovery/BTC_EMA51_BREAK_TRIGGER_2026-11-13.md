# BTC 1H/15m EMA51 pullback break-trigger study — 2026-11-13

**Classification:** Experimental only. Rejected; no live use.

## Hypothesis and exact rules

This study mechanically tests the previously discussed EMA51 setup.

- Trend context: completed 1H close below its 1H EMA51 permits shorts only; completed 1H close above EMA51 permits longs only.
- Optional filter: EMA51 slope over the prior four completed 1H bars must agree with direction.
- Short setup: a completed green 15m candle whose range intersects the 15m EMA51 band; mark that candle's low and place a sell-stop trigger at the low.
- Long setup: exact mirror using a completed red candle and its high.
- EMA-touch band: 0.10 or 0.20 of 15m ATR(14).
- Pending entry expiry: 3 or 6 subsequent 15m bars.
- Stop: signal-candle high + 0, 25 or 50 BTCUSD points for shorts; signal-candle low - buffer for longs.
- Target: 1.5R, 2R or 3R.
- Maximum holding: 32 15m bars (8 hours).
- Directions tested separately: short-only and long-only.
- Sessions: all hours or 07:00–19:00 UTC.
- 288 configurations in total.

A 15m signal is known only at its close. A stop-entry order becomes active on the next 15m bar. If the market gaps through the protective stop before entry, the pending order is cancelled. Entry gaps fill at the worse open. If stop and target are both touched in one candle, stop is assumed first; adverse stop gaps fill at the worse open; target fills at its limit price.

## Dataset and reproducibility

The local completed run used the BTCUSD 15m CSV extracted from the reproducible historical-data artifact of [pair study run 43357538018](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43357538018).

- Rows: 70,127
- Date range: 2024-11-12 15:15 UTC to 2026-11-13 02:45 UTC
- Missing 15m intervals: 0
- Duplicate timestamps: 0
- Zero-volume candles: 80
- SHA-256: `f31d3c0b9ddb13a1355ea78d569af7971f8517b4c2e5812ff82bd96ae9775e1e`
- Chronological split: 70/15/15 by candle-open row index
- Training end: 2026-04-07 23:15 UTC
- Validation end: 2026-07-26 13:00 UTC
- Every possible entry must leave the full 8-hour holding horizon inside its split; no pending order or trade crosses a split boundary.
- Primary assumed cost: 12bp round trip per single leg; diagnostic sensitivity at 6/12/20bp.
- Funding, exact contract settlement P&L, order-book spread and market impact are not modeled.

The 13 local deterministic tests passed, covering stop-entry trigger/gap handling in both directions, stop-first same-bar resolution, adverse stop gaps, target fills, completed-1H availability, future perturbation and split-boundary isolation.

## Results at 12bp assumed round-trip cost

**Selection funnel:** 288 configurations; 0 training-eligible; 0 validation passes; OOS not evaluated.

### Best training-net candidate

Configuration: 0.10 ATR touch band; 6-bar pending expiry; 50-point stop buffer; 3R target; short-only; 07:00–19:00 UTC; 1H EMA51 side + four-hour EMA slope filter.

| Metric | Training | Validation |
|---|---:|---:|
| Trades | 309 | 46 |
| Win rate | 29.13% | 26.09% |
| Profit factor | 0.662 | 0.703 |
| Net result | -100.92R | -12.09R |
| Average R/trade | -0.327R | -0.263R |
| Maximum drawdown | -106.44R | -17.11R |
| Maximum losing streak | 12 | 9 |
| Positive months | 16.7% | 25.0% |

### Best validation-PF candidate with at least 20 trades

Configuration: 0.20 ATR touch band; 3-bar pending expiry; 50-point stop buffer; 2R target; short-only; 07:00–19:00 UTC; 1H EMA51 side filter.

| Metric | Training | Validation |
|---|---:|---:|
| Trades | 348 | 53 |
| Win rate | 33.33% | 41.51% |
| Profit factor | 0.543 | 0.819 |
| Net result | -149.41R | -7.15R |
| Average R/trade | -0.429R | -0.135R |
| Maximum drawdown | -149.41R | -12.94R |
| Maximum losing streak | 15 | 6 |
| Positive months | 16.7% | 50.0% |

The exact 50-point-buffer / 2R / short-only rule family was negative across all tested tolerances, pending expiries, session choices and EMA-side/slope filters. For example, with a 0.10 ATR touch band, 50-point buffer, 2R target and no session restriction, the baseline EMA-side version produced 537 training trades at PF 0.535 and -232.40R, then 90 validation trades at PF 0.599 and -31.23R.

### Cost sensitivity

| Diagnostic candidate | Split | 6bp | 12bp | 20bp |
|---|---|---:|---:|---:|
| Best training-net | Train | -39.41R | -100.92R | -182.95R |
| Best training-net | Validation | -4.47R | -12.09R | -22.27R |
| Best validation-PF | Train | -74.42R | -149.41R | -249.41R |
| Best validation-PF | Validation | +3.31R | -7.15R | -21.10R |

The validation-only positive result at 6bp is not useful: its matching training result is deeply negative, and the result turns negative at the 12bp primary assumption.

### Monthly and regime stability

The best training-net candidate had only 3 positive training months out of 18 and 1 positive validation month out of 4. The best validation-PF candidate had 3/18 positive training months and 2/4 positive validation months.

Both diagnostic candidates generated only bear-regime short trades, and both lost materially in training and validation. There is no evidence of a stable edge.

## Decision

**Reject this EMA51 pullback-break trigger as a mechanical BTC intraday strategy. Do not evaluate OOS.**

The original 50-point stop buffer and 2R target were explicitly tested. The failure is not merely an absence of sample size: the tested variants had hundreds of trades and consistently negative training expectancy, weak profit factors and large drawdowns.

## Code and workflow

- Engine: `research/btc_ema51_break_trigger_intraday_backtest.py`
- Workflow: `.github/workflows/btc-ema51-break-trigger.yml`
- Research ledger: `research/RESEARCH_LEDGER.md`
- Local full matrix completed on the archived BTC input. GitHub Actions run [43386574210](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43386574210) independently completed the download, deterministic tests, 288-configuration matrix and summary, but its final artifact-upload step failed because the artifact name contained a literal backslash. The workflow name was corrected at commit `1f9cdec805c6395e6230c853ef7af9b59fe85399`; clean rerun [43386763734](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43386763734) was in progress at the historical-data download stage at the latest check.

No production rules, live alerts, orders or main branch were changed.
