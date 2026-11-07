# EXP-003 — Online strategy selection and meta-learning

**Status:** research-only implementation on ai-quant-rebuild. Runs after EXP-002 in the existing historical archive workflow. No performance conclusion is claimed until that run completes and its outputs are inspected.

## Source adaptation

The NYU Stern / Glucksman paper by Niko Lahanis, Alice Liu and Zhengyuan Zhou (May 2025) compares Follow-the-Winner, Follow-the-Loser, Pattern Matching and Meta-Learning approaches on NASDAQ-100 minute data from 1998–2010. Its equity-universe results are not transferable to BTC, ETH or XAUT perpetuals. Quantified Strategies is used as a hypothesis catalogue for momentum, mean reversion, Bollinger/squeeze, exhaustion, oscillator and seasonal ideas—not as a vetted source of executable crypto edges.

## EXP-003 design

Input is only the pre-existing EXP-002 final out-of-sample shadow-trade table. Four fixed selectors are compared:
- Follow-the-Winner: exponentially weighted prior net-R, shrunk for small samples.
- Follow-the-Loser: mirrored prior payoff, retained as a contrarian/control comparison.
- Pattern Matching: prior outcomes for the exact asset, timeframe, trend and volatility context.
- Meta-Ensemble: fixed weighted percentiles of winner, pattern and clipped-return online-Hedge-style scores.

Each selector chooses at most one existing candidate per asset. No setup is created, opposite directions are not blended and nothing is routed to alerts. Three prior expert observations or three exact-context matches are required. Non-positive evidence means no trade.

## Causality and cost controls

EXP-002 timestamps denote candle opens. A trade outcome is visible only at exit candle close: exit timestamp plus timeframe duration. The selector is prequential: only already-closed shadow outcomes update its history. Every independent EXP-002 stream is treated as a full-information shadow expert, including unselected counterfactual trades; a live evaluation would require a parallel shadow ledger.

Each selector is re-run at 10/20/40 bps round-trip costs plus a 1 bp/8h adverse carry stress. Carry is not verified realized funding. Five chronological slices are reported with prior history carried forward only. They are not independent training folds.

Outputs include summary, walk-forward, selected-trade and decision CSVs plus a source-hash manifest. Metrics include sample size, win rate, net expectancy, profit factor, max drawdown, consecutive losing portfolio exit events, trade frequency, holding time and exit type counts.

## Limitations and decision gate

Historical spread, depth and executable market impact are unavailable; archived funding semantics remain unresolved. Positive results are exploratory only. Require an untouched future dataset, robustness across cost levels, folds and regimes, and execution-cost evidence before considering promotion. No EXP-003 result can change APPROVED_STRATEGIES, production alerts, paper positions or live trading.
