# BTC/ETH train-only cointegration diagnostic — 20 November 2026

## Decision

**No full-training cointegration evidence under the preregistered specification.** The I(1) precondition passes, but the full-train Engle–Granger p-value does not survive the five-test Holm correction, and none of the four chronological blocks is significant after adjustment. This does not establish a stationary tradable spread and does not reverse the previously rejected pair mean-reversion matrix.

## Reproducibility

- Successful workflow: [44767639023](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44767639023)
- Artifact: [14645822140](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/44767639023/artifacts/14645822140)
- Artifact ZIP SHA-256: 0375c84a337b9821397452e020833ae99352ef746ab08695fc46b0dbae2ad975
- A preceding calculation completed but its artifact upload failed due a literal backslash in the artifact name; the workflow was corrected and the complete train-only job rerun successfully.
- Deterministic tests passed: Holm adjustment, exact block coverage, synthetic cointegrated and independent random walks, and future-perturbation invariance of the reused rolling beta features.

## Dataset and boundary

- Delta Exchange India BTCUSD and ETHUSD public traded-price OHLCV, 15-minute UTC bars.
- Start inclusive: 2025-09-08 12:00 UTC.
- Training end exclusive: 2026-07-12 04:45 UTC.
- BTC: 29,443 rows, zero gaps, SHA-256 06461a1f2b12a8dac139625856a8aa12aade5be1d89e919a42e59d9af444dd8b.
- ETH: 29,443 rows, zero gaps, SHA-256 1b9226331b96d9aa3c647f0fdf7e3c72f9040dd37b5c240376982388643895b9.
- Aligned rows: 29,443; zero gaps and duplicates.
- This is the exact prior-study 70% chronological training boundary. Validation and OOS data were neither downloaded nor evaluated.

## I(1) precondition

ADF uses a constant and AIC autolag.

| Series | Transform | ADF statistic | p-value |
|---|---|---:|---:|
| BTC | Log level | -1.163964 | 0.688902 |
| ETH | Log level | -1.314647 | 0.622445 |
| BTC | First difference of log level | -66.113001 | <1e-12 |
| ETH | First difference of log level | -76.778353 | <1e-12 |

The preregistered I(1) precondition passes: both log levels fail to reject a unit root at 5%, while both first differences reject.

## Frozen Engle–Granger test family

One regression orientation only: log(ETH) on a constant plus log(BTC), no deterministic trend, AIC autolag. The five p-values (full train plus four contiguous blocks) are adjusted together with Holm–Bonferroni.

| Sample | N | Statistic | Raw p | Holm p | 5% significant |
|---|---:|---:|---:|---:|---|
| Full train | 29,443 | -3.207389 | 0.068701 | 0.274803 | No |
| Block 1 | 7,361 | -2.377029 | 0.335810 | 0.989496 | No |
| Block 2 | 7,361 | -3.756825 | 0.015461 | 0.077305 | No |
| Block 3 | 7,361 | -2.389525 | 0.329832 | 0.989496 | No |
| Block 4 | 7,360 | -2.374530 | 0.337011 | 0.989496 | No |

Full-train critical values: 1% -3.896812; 5% -3.336338; 10% -3.044594. The full-train raw p-value is below 10% but not 5%; after the preregistered family correction it is not significant. Block 2's raw p-value is low, but its adjusted p-value is 0.077305. Zero of four blocks are significant after adjustment.

The preregistered persistence criterion required the full-train adjusted p-value below 0.05 and at least three of four adjusted blocks below 0.05. It fails.

## Descriptive lagged rolling-beta stability

These values reuse the existing pair-study one-bar-lagged rolling OLS feature implementation. They are descriptive, not additional hypothesis tests.

| Lookback | N | Median beta | P05 | P95 | IQR | Min | Max | Positive beta | In 0.25–4.0 | Median return corr | Min return corr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 days | 28,483 | 1.273677 | 0.760710 | 1.896137 | 0.433412 | 0.345736 | 2.535377 | 100% | 100% | 0.886522 | 0.710668 |
| 30 days | 26,563 | 1.238853 | 0.603473 | 1.666483 | 0.318475 | 0.072486 | 1.831094 | 100% | 97.869% | 0.888456 | 0.751989 |

The rolling return correlation is high, but correlation and a positive rolling hedge ratio do not establish a stationary spread. The formal train-only cointegration evidence is not present under this fixed test family.

## Interpretation and limits

- This is a statistical diagnostic, not a trading backtest. No trades, PnL, win rate, profit factor, drawdown, funding or execution costs are applicable.
- No validation or OOS rows were downloaded or evaluated.
- The result does not establish a tradable edge and cannot reverse the rejected 576-configuration pair mean-reversion study.
- Delta historical funding mechanics remain unresolved; this no-position diagnostic does not solve that separate issue.
- Runtime: Python 3.11.18, NumPy 2.3.5, pandas 2.2.3, SciPy 1.17.0, statsmodels 0.14.6.

## Next step

Close the current BTC/ETH pair-mean-reversion premise. Before another strategy test, audit the remaining BTC single-asset research backlog and data availability, then preregister one genuinely distinct hypothesis. Do not tune the inspected pair train sample or access its reserved validation/OOS periods.
