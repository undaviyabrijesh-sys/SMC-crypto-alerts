# Research methodology reset — 2026-11-14

## Why this reset is necessary

The accumulated studies show repeated failures, but that does not prove every strategy family is inherently unprofitable. It also does not prove the research framework is correctly calibrated. A code and methodology review identified several weaknesses that can create false rejections, false confidence, or ambiguous conclusions.

This reset changes the research process. It does not alter production strategies, live alerts, or the main branch.

## Findings from the code and ledger audit

1. **Small validation samples.** The fixed chronological 70/15/15 split over roughly two years leaves only about 3.6 months for validation and 3.6 months for OOS. A 20-trade minimum and monthly-consistency threshold are weak statistical evidence over such a short period. They can reject strategies whose edge is episodic, and a handful of trades can dominate validation.
2. **Large parameter grids.** Several studies test hundreds or thousands of combinations. Selecting the top 25 on training reduces direct validation search, but still creates substantial winner's-curse risk. The best validation-only diagnostic rows are descriptive only and must never be presented as candidate evidence.
3. **Fixed RR and fixed holding horizons.** Many models use fixed 1.5R/2R/3R/4R targets and short timeouts. A signal may have directional value but lose money under the selected exit rule. Entry edge and exit/position-management edge have not been separated consistently.
4. **OHLC ambiguity.** Stop-first handling is a defensible pessimistic bound, but it can materially understate results when both stop and target are touched inside a bar. Where 1m/tick data are unavailable, report pessimistic and optimistic bounds and the ambiguous-trade count; do not silently treat the pessimistic bound as the only possible execution outcome.
5. **Execution costs are too coarse.** A single assumed round-trip bps number does not distinguish maker/taker entry, exit type, spread, volatility-dependent slippage, stop-market impact, or funding at actual settlement timestamps. Cost sensitivity is useful but not a substitute for an execution model.
6. **Limited robustness reporting.** The ledger emphasizes total R, PF and month fractions, but does not consistently report expectancy confidence intervals, bootstrap uncertainty, walk-forward fold dispersion, exposure/time-in-market, trade clustering, or comparison against simple benchmarks.
7. **Validation-only leaderboard diagnostics.** These are useful for diagnosing failure, but choosing or promoting them would leak validation information. Going forward, do not describe a validation-only top row as a promising candidate. It is an audit statistic only.
8. **R is not account return.** Per-trade R assumes a risk unit but does not show compounded equity, risk sizing, capital usage, leverage, funding, or portfolio-level drawdown. Report both R metrics and a clearly specified equity simulation when a strategy is executable.

## New protocol (effective immediately)

### A. Pause giant grids

Use one preregistered economic hypothesis per experiment and a small, interpretable parameter set. First test a single baseline and a few justified variants. Do not expand a grid because the initial result is negative.

### B. Establish baselines and controls

Every strategy must be compared with:
- Buy/hold and flat/no-trade controls over the same dates.
- A simple directional benchmark (e.g. 1h EMA trend or 20-bar breakout) with identical execution/cost assumptions.
- A signal-shuffled or time-shifted placebo where appropriate.
- Long-only and short-only attribution, not just combined results.

### C. Use rolling walk-forward validation

For the next studies, use expanding or rolling chronological folds, e.g. 6-month train / 2-month validation, stepped forward by 2 months, plus one final untouched holdout. Exact windows must be frozen before running. Report each fold separately and aggregate only after all folds. Do not tune on the final holdout.

The old 70/15/15 studies remain in the ledger as historical exploratory research; do not retroactively relabel their results.

### D. Resolve execution uncertainty

Prefer 1m or finer execution data for 5m/15m signals. If only coarse OHLC is available:
- Count bars where both stop and target are touched.
- Report a pessimistic stop-first result and an optimistic target-first upper bound.
- Keep the pessimistic result as the conservative headline, but show the uncertainty interval.
- Apply adverse gap fills to stops and no favourable gap improvement to fixed targets.

### E. Separate signal quality from trade management

For each promising signal, first measure forward returns at fixed horizons (e.g. 15m, 1h, 4h, 8h) and compare with matched controls. Then test a small set of exits: fixed target, trailing stop, time exit, VWAP/structure exit, and partial take-profit. This identifies whether the entry has information before optimizing how to monetize it.

### F. Improve cost and risk accounting

Model entry and exit separately: maker/taker fees, spread, slippage, stop-market penalty, and funding only when the position crosses a verified settlement timestamp. Until actual fee tier is known, show multiple plausible cost scenarios and label them assumptions. Report R, net percentage return, exposure, turnover, equity drawdown and risk sizing separately.

### G. Statistical evidence

Report trade count, win rate, PF, mean/median R, expectancy confidence interval, bootstrap interval for net expectancy, max drawdown, losing streak, monthly and regime attribution, fold-by-fold results, and ambiguity count. Use block bootstrap or another method that respects serial dependence. A positive point estimate with a confidence interval spanning zero is not validated.

### H. Promotion standard

A strategy is not validated by one profitable split or a high PF from a small sample. It must show:
- Positive net expectancy across multiple walk-forward validation folds.
- A final untouched holdout result consistent with validation.
- Robustness under conservative costs and execution bounds.
- No single month/regime/side accounting for nearly all profits.
- Enough independent trades for uncertainty to be acceptably narrow.
- Reproducible code, data hashes, and an auditable trade ledger.

No production promotion without separate explicit approval.

## New hypotheses to test differently

1. **Session range sweep and re-entry:** define Asia range from fixed UTC hours; trade only a sweep of the range high/low followed by a close back inside, target VWAP or opposite range boundary. Test as a signal event study first, then exits. This differs from generic rolling Donchian failure.
2. **Trend pullback as a bias, not an entry:** use completed 4h/1h direction to choose side; measure 15m pullback continuation at VWAP/EMA and test forward returns before choosing exits. Compare with matched same-regime control entries.
3. **Volatility expansion continuation:** identify compression using prior-only ATR percentile, then a range expansion close; test continuation at multiple horizons and compare with placebo. Avoid a giant stop/target grid.

## Immediate next action

Do not start another large parameter matrix. First build a reusable walk-forward evaluation harness and execution-ambiguity report, then run the session-range sweep/re-entry hypothesis on BTC using the finest reliable execution data available. If 1m data is unavailable, preserve uncertainty bounds rather than inventing fills.

## Safety and scope

Research only. Stay on `ai-quant-rebuild`. Do not touch `main`, production logic, live trading, or execution alerts. No orders.
