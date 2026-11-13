# BTC 1H/15m EMA51 pullback-break trigger study — 2026-11-13

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
- Total: 288 configurations.

A 15m signal is known only at its close. A stop-entry order becomes active on the next 15m bar. If the market gaps through the protective stop before entry, the pending order is cancelled. Entry gaps fill at the worse open. If stop and target are both touched in one candle, stop is assumed first; adverse stop gaps fill at the worse open; target fills at its limit price.

## Dataset and reproducibility

**Verified GitHub Actions run:** [43386763734](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43386763734) — all workflow steps succeeded, including deterministic tests, historical download, full matrix, summary and artifact upload.

- Rows: 70,127 BTCUSD 15m candles
- Date range: 2024-11-12 19:45 UTC to 2026-11-13 07:15 UTC
- Missing 15m intervals: 0
- Zero-volume candles: 80
- SHA-256: `12d7d7c6d29d98d8a20e58e79301ab713aaf7005c32633d7bf6b2ceefa55fd25`
- Chronological split: 70/15/15 by candle-open row index
- Training end: 2026-04-08 03:45 UTC
- Validation end: 2026-07-26 17:30 UTC
- Every possible entry must leave the full 8-hour holding horizon inside its split; no pending order or trade crosses a split boundary.
- Primary assumed cost: 12bp round trip per single leg; diagnostic sensitivity at 6/12/20bp.
- Funding, exact contract settlement P&L, order-book spread and market impact are not modeled.

The workflow passed 13 deterministic tests covering stop-entry trigger/gap handling in both directions, stop-first same-bar resolution, adverse stop gaps, target fills, completed-1H availability, future perturbation and split-boundary isolation.

[Download/inspect the retained GitHub artifact](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43386763734/artifacts/14018582805).

## Results at 12bp assumed round-trip cost

**Selection funnel:** 288 configurations; 0 training-eligible; 0 validation passes; OOS not evaluated.

### Best training-net candidate

Configuration: 0.10 ATR touch band; 6-bar pending expiry; 50-point stop buffer; 3R target; short-only; 07:00–19:00 UTC; 1H EMA51 side filter.

| Metric | Training | Validation |
|---|---:|---:|
| Trades | 331 | 55 |
| Win rate | 29.61% | 23.64% |
| Profit factor | 0.678 | 0.599 |
| Net result | -101.08R | -20.85R |
| Average R/trade | -0.305R | -0.379R |
| Maximum drawdown | -111.72R | -24.29R |
| Maximum losing streak | 13 | 8 |
| Positive months | 27.8% (5/18) | 0% (0/4) |

### Best validation-PF candidate with at least 20 trades

Configuration: 0.20 ATR touch band; 3-bar pending expiry; 50-point stop buffer; 2R target; short-only; 07:00–19:00 UTC; 1H EMA51 side filter.

| Metric | Training | Validation |
|---|---:|---:|
| Trades | 348 | 54 |
| Win rate | 33.62% | 40.74% |
| Profit factor | 0.551 | 0.788 |
| Net result | -146.41R | -8.72R |
| Average R/trade | -0.421R | -0.162R |
| Maximum drawdown | -148.14R | -12.94R |
| Maximum losing streak | 15 | 6 |
| Positive months | 16.7% (3/18) | 50% (2/4) |

The exact 50-point-buffer / 2R / short-only family was negative across the tested tolerances, pending expiries, session choices and EMA-side/slope filters. The best validation-PF member still lost -146.41R in training and -8.72R in validation.

### Cost sensitivity

| Diagnostic candidate | Split | 6bp | 12bp | 20bp |
|---|---|---:|---:|---:|
| Best training-net | Train | -35.90R | -101.08R | -187.98R |
| Best training-net | Validation | -11.95R | -20.85R | -32.71R |
| Best validation-PF | Train | -71.42R | -146.41R | -246.41R |
| Best validation-PF | Validation | +2.02R | -8.72R | -23.05R |

The validation-only gain at 6bp is not useful: its matching training result is deeply negative, and it turns negative at the 12bp primary assumption.

### Monthly and regime stability

The best training-net candidate had 5 positive training months out of 18 and zero positive validation months out of four. The best validation-PF candidate had 3/18 positive training months and 2/4 positive validation months.

Both diagnostic candidates generated only bear-regime short trades, and both lost materially in training and validation. There is no evidence of a stable edge.

## Decision

**Reject this EMA51 pullback-break trigger as a mechanical BTC intraday strategy. Do not evaluate OOS.**

The original 50-point stop buffer and 2R target were explicitly tested. The failure is not merely an absence of sample size: the tested variants had hundreds of trades and consistently negative training expectancy, weak profit factors and large drawdowns.

## Code and workflow

- Engine: `research/btc_ema51_break_trigger_intraday_backtest.py`
- Workflow: `.github/workflows/btc-ema51-break-trigger.yml`
- Research ledger: `research/RESEARCH_LEDGER.md`
- Verified workflow: [run 43386763734](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43386763734)
- Artifact: [14018582805](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43386763734/artifacts/14018582805)

The earlier workflow attempt's artifact-name error was corrected; the clean rerun above completed successfully.

No production rules, live alerts, orders or main branch were changed.
