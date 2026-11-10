# Salty Quant Research Ledger

Last updated: 2026-11-10 (UTC)

This ledger records reproducible experiments only. "Completed" means the workflow actually finished and outputs were inspected. No experiment here changes live signals or production rules.

## BTCUSD — CRT

### CRT v1 (exploratory)
- Code: `research/crt_backtest.py`
- Workflows: [original run](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42771498847), [reversed-direction run](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42773447746)
- Dataset: Delta Exchange India BTCUSD, 15m execution candles; approximately 2024-11-10 to 2026-11-10; 70,079 15m rows; 0 missing 15m intervals in the inspected run.
- Rules: completed 1H/4H/1D reference candle; following reference window; sweep of range edge and 15m close back inside; next 15m open entry; stop at sweep extreme with optional 0.1 reference ATR buffer; 1.5R/2R/3R or opposite range edge; original and reverse directions.
- Cost: assumed 12bp round trip; not verified against the user's Delta fee tier. No funding.
- Execution: same-bar SL/TP resolved as SL first.
- Selected reported results (exploratory only): best 1D original setup was 516 trades, PF 0.776, net -87.16R; best 4H original was 2,914 trades, PF 0.473, net -1,201.51R; best 1H original was 9,088 trades, PF 0.199, net -6,456.24R. Reversed variants were also negative.
- Limitations: simple sweep/reclaim rather than full CRT/MSS; overlapping positions allowed; ATR approximated from rolling high-low; no chronological OOS validation; cost estimate only. These figures are not a definitive test of discretionary CRT.

### CRT v2 (chronological validation; simplified proxy)
- Code: `research/crt_backtest_v2.py`
- Workflow: [run 42773741203](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42773741203)
- Dataset: same Delta BTCUSD 15m history, 70,079 rows, no 15m gaps in inspected run; 70/30 chronological split at 2026-04-05 07:00 UTC.
- Rules: 1H/4H/1D reference ranges; sweep/reclaim; reclaim or candle-break MSS proxy; 1.5R/2R/3R; all hours or broad UTC 07:00–21:00 session proxy; one trade at a time per exact configuration; next 15m open entry; time exit at end of next reference window.
- Cost/execution: assumed 12bp round trip; no funding; same-bar SL first.
- Best inspected OOS configuration: daily reference + MSS candle-break proxy + 2R + broad London/NY UTC session proxy; 70 trades, 35.71% profitable, PF 0.661, net -18.217R, average -0.2602R, max DD -19.568R. All reported OOS configurations were negative.
- Limitations: MSS is not a true swing-structure model; session proxy ignores DST; no funding; no full intrabar sequencing. Negative result applies only to this mechanical proxy and assumptions.

### CRT v3 (expanded matrix)
- Code: `research/crt_backtest_v3.py`
- Workflow: [run 42774456358](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42774456358)
- Matrix: 1H/4H/daily/weekly references; reclaim, displacement, MSS, MSS-retest and MSS-FVG proxies; 1.5R/2R/3R/4R/opposite-range targets; buffered/unbuffered stops; original/reversed direction; all hours or broad UTC session.
- Cost/execution: assumed 12bp round trip; no funding; SL first on same 15m candle; chronological 70/30 split.
- Status: workflow has remained in progress in the latest status check; no final figures or artifact inspected yet.
- Audit cautions: MSS and FVG are mechanical proxies, not discretionary CRT; session ignores DST; variants run independently; exits are bounded to the next reference window, which gives different maximum holding horizons across reference timeframes. Treat outputs as exploratory until runtime and methodology audit are complete.

## BTCUSD — Fibonacci retracement (experimental)

### Initial run (superseded; do not use as final evidence)
- Code revision: initial `research/fibo_backtest.py`; workflow [run 42777665691](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42777665691).
- Rules intended: 1H confirmed pivots with 3 bars left/right; retracement entry at 0.50, 0.618 or 0.50–0.618 zone; rejection, engulfing or previous-candle break confirmation; swing or 0.786 stop; 1.272/1.618 extension or 2R target; 15m execution.
- Cost: assumed 12bp round trip; no funding; SL first on same candle; 7-day max holding period; chronological 70/30 split.
- Status: still in progress at latest check. The initial code had a stale-leg validity issue and a time-exit calculation issue. Do not use its eventual results as final evidence.

### Corrected run
- Corrected code commit: `5c5933b725cf1f226ed91c2af4c441ac1ddb6c9c`
- Initial corrected workflow: [run 42781365500](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781365500); final drawdown-corrected workflow: [run 42781653275](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781653275)
- Corrections: require contiguous 1H pivot windows; reject ambiguous same-bar high/low pivots; expire a Fibonacci leg when the next pivot is confirmed; bound time-exit price/time to the 7-day holding window; add max losing streak and monthly breakdown outputs.
- Status: both corrected runs were still in progress at the latest check; no results inspected yet.
- Remaining limitations: 12bp is assumed rather than fee-tier verified; no funding; no spread/slippage model beyond the flat cost; 1H pivots are a mechanical swing definition; no discretionary trend filter. The final 30% is OOS and must not be tuned against.

## Next queued research family

### Supertrend 15m BTCUSD baseline
- Hypothesis: 15m Supertrend flips with ATR(7) × 2.5 may define a trend-following entry with the Supertrend line as initial stop and 2R target.
- Variants to compare: Supertrend source = HL2 versus EMA(50); optional 1H EMA(50) direction filter; fixed initial Supertrend stop.
- Entry: after a confirmed 15m direction flip, enter next 15m open. If entry is already beyond the stop, skip.
- Execution: one position at a time per configuration; SL first if stop and target touch in the same candle; assume 12bp round-trip cost; no funding in baseline; chronological 70/30 split; report trade count, profitable %, PF, net R, max DD, losing streak and monthly stability.
- Code: `research/supertrend_backtest.py`; workflow: [fixed implementation run 42781648124](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781648124). A prior pre-fix run 42781598401 is superseded.
- Implementation: ATR(7) Wilder RMA × 2.5; source HL2 or 15m EMA50; optional completed-1H EMA50 direction filter; next-open entry after confirmed direction flip; fixed stop at signal-candle Supertrend line; 2R target; 7-day max hold; 12bp assumed round-trip cost; SL-first and adverse gap-through stop fill; chronological 70/30 split; monthly and losing-streak metrics.
- Status: fixed implementation is running; no results inspected yet. Keep separate from CRT and Fibonacci experiments.

## Research standards
- No lookahead: pivot levels become available only after right-side confirmation bars close; signal candle closes before next-open entry.
- No survivorship bias: BTCUSD single instrument for these experiments; future multi-asset studies must define an as-of universe.
- No production or live rule changes; do not merge to `main`; no orders or execution alerts.
- A negative or weak result rejects only the tested mechanical definition and assumptions, not the broad discretionary concept.
