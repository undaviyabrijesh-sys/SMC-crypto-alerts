# BTC SMC 5m execution ambiguity audit — 2026-11-15

## Scope

This was a reporting/execution audit of the frozen 48-configuration BTC 1H sweep/reclaim → 15M MSS → 5M entry study. It did not change signal rules, entry timestamps, stop placement, target selection, candidate gates or promotion rules.

## Code and reproducibility

- Repository: `undaviyabrijesh-sys/SMC-crypto-alerts`
- Branch: `ai-quant-rebuild`
- Code commit: `1de95553aa477ded365aad69e5e35fa6b9302569`
- Authoritative workflow: [43708569471](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43708569471)
- Artifact: [14159213508](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43708569471/artifacts/14159213508)
- Deterministic CI: [43708569517](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43708569517) passed; pull-request CI [43708573335](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43708573335) passed.
- The script now counts a 5m bar as ambiguous only when it opens between stop and target and spans both levels. Headline execution remains stop-first. It also resolves a target crossed at the bar open before considering a later opposite wick; stop gaps remain adverse.

## Dataset

- Source: Delta Exchange India public BTCUSD traded-price 5m candles.
- Valid rows: 210,239; complete derived 15m rows: 70,079; 1h rows: 17,519; 4h rows: 4,379.
- Period: 2024-11-15 11:25 UTC to 2026-11-15 11:15 UTC.
- 5m gaps: 0; duplicates removed: 0; invalid timestamps/OHLC rows: 0; zero-volume bars: 334.
- SHA-256: `0190043a57c4174bdbb074b9a6e507533d632e30c2b85025efed5627295e5aeb`.

## Results at 12bp assumed round-trip cost

- 48 configurations tested; 12 passed the training gate; 0 passed validation; no candidate selected and no OOS evaluation.
- Best training diagnostic: 5m next-open; 0 ATR stop buffer; 1.5R target; no 4h filter; both directions; all hours.
  - Training: 97 trades, 51.55% win rate, PF 1.408, +11.340R, max drawdown -3.158R, max losing streak 5, positive active months 55.6%.
  - Validation: 23 trades, 39.13% win rate, PF 0.853, -1.232R, max drawdown -5.158R, max losing streak 6, positive active months 50.0%.
  - Validation cost sensitivity: +0.434R at 6bp (PF 1.058), -1.232R at 12bp (PF 0.853), -3.454R at 20bp (PF 0.645).
- Best validation-only diagnostic (not eligible for selection): next-open; 0.1 ATR stop buffer; 2R target; no 4h filter; both directions; all hours.
  - Training: 97 trades, PF 1.305, +8.402R.
  - Validation: 23 trades, 39.13% win rate, PF 0.917, -0.689R, max drawdown -4.592R, max losing streak 6.
  - This diagnostic does not pass the training gate and is not a candidate for promotion.

## Ambiguity findings

- Across all 48 configurations, both train and validation metrics report zero trades whose first exit bar opened between stop and target and touched both levels.
- The two retained diagnostic trade ledgers contain 240 trade records across train/validation; all have zero 5m ambiguous stop/target bars.
- Therefore, for this particular 5m OHLC sample, the target-first optimistic upper bound equals the conservative stop-first result. This does not prove the actual intrabar path; 5m candles can hide 1m ordering, and the replay has not yet been performed.
- The target-at-open precedence correction did not change the leading training/validation results above.

## Decision

The SMC model remains **experimental and rejected at validation**. The ambiguity audit does not improve the negative validation result. Do not promote, tune on the inspected validation segment, change live rules, send execution alerts or place orders.

## Next step

A separately preregistered 1m execution replay now freezes the two diagnostic configurations and will check 1m coverage, 1m-to-5m OHLC reconciliation, first-touch exits, 1m ambiguity and 6/12/20bp sensitivity. It will not evaluate OOS or select a new strategy.
