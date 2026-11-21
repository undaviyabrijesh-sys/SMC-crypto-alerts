# BTCUSD 15m support/resistance rejection — completed diagnostic

**Workflow:** [43491328896](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43491328896), success on ai-quant-rebuild at code commit c008379e74518c472d904615ea014a75826d77e9. Artifact [14068778457](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43491328896/artifacts/14068778457).

## Data and methodology

- Delta BTCUSD 15m OHLC, 70,079 rows, 2024-11-13 19:30 UTC to 2026-11-13 19:00 UTC.
- Zero missing 15m intervals; SHA-256 0b03ee0d34fba7b84b522d85ff4a57d6716f05c9f48f4228dee2ddfb9397d8b0.
- 1,152 configurations: prior completed UTC-day high/low or confirmed 4H pivots; sweep/reclaim or near-reject; tolerance 0/0.1 ATR; immediate or next-bar-break confirmation; 0/0.1 ATR stop buffer; 1.5R/2R/3R target; no filter or EMA50/200 filter; both/long-only/short-only; all hours or 07–19 UTC.
- Next 15m open, 8h max hold, one position/config, stop-first same-bar ambiguity and adverse gap-stop fills. Primary cost 12 bps round trip; sensitivities 6/12/20 bps. Funding excluded; separate spread/market impact unmodeled.
- Chronological 70/15/15. Train gate: >=40 trades, PF>=1.05, positive net R, DD>=-25R, >=50% positive months. Validation gate: >=20 trades, PF>=1.05, positive net R, DD>=-15R, >=50% positive months. OOS only after both gates.

## Gate outcome

- Configurations: 1,152.
- Train-eligible: 0.
- Shortlisted: 0.
- Validation passes: 0.
- OOS: not evaluated.

An independent calculation over the 1,152-row matrix confirmed zero train configurations met the full gate. There were 85 configurations with positive train net R, but none met all trade-count, PF, drawdown and monthly-stability requirements.

## Diagnostic examples (not candidates)

**Best training-ranked row:** confirmed 4H pivot, sweep/reclaim, 0.1 ATR tolerance, signal-close entry, no stop buffer, 3R target, EMA50/200 filter, short-only, 07–19 UTC.

| Split | Trades | Win rate | PF | Net R | Max DD | Losing streak |
|---|---:|---:|---:|---:|---:|---:|
| Train | 14 | 50.00% | 1.624 | +5.557R | -4.632R | 2 |
| Validation | 3 | 33.33% | 0.954 | -0.133R | -1.682R | 1 |

The train sample is below the 40-trade minimum; validation has only three trades.

**Best validation-ranked row with at least 20 validation trades:** prior-day sweep/reclaim, 0.1 ATR tolerance, signal-close entry, 0.1 ATR stop buffer, 3R target, no HTF filter, long-only, 07–19 UTC.

| Split | Trades | Win rate | PF | Net R | Max DD | Losing streak |
|---|---:|---:|---:|---:|---:|---:|
| Train | 228 | 28.95% | 0.570 | -95.977R | -101.887R | 17 |
| Validation | 51 | 41.18% | 1.202 | +8.220R | -8.815R | 3 |

This is validation-only strength against severely negative training results; it fails the training gate.

## Cost sensitivity

- Best-train-ranked configuration: train +7.642R at 6 bps, +5.557R at 12 bps, +2.779R at 20 bps, but only 14 train trades and 3 validation trades; validation turns negative at 12/20 bps.
- Best-validation-ranked configuration: validation +19.115R at 6 bps, +8.220R at 12 bps, -6.307R at 20 bps; matching training is -95.977R at 12 bps.

## Independent audit and decision

Trade-ledger recalculation reproduced the four diagnostic rows above exactly. No configuration passed the train gate, so no OOS was accessed. Reject this support/resistance matrix under the tested definitions and costs; do not tune against the validation-only winner. This is not evidence that all discretionary support/resistance methods fail.

Limitations: Delta BTCUSD OHLC only; assumed fee, no spread/market-impact model; funding excluded; 07–19 UTC session ignores DST. No ETH replication and no production changes.
