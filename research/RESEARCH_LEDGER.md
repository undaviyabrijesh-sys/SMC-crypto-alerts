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
- First full-matrix run [42774456358](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42774456358) hit the 60-minute job limit and was cancelled before summary output; its artifact contained only the raw 15m data file. The initial implementation repeatedly built full-length boolean masks for each reference window/configuration, causing excessive runtime.
- Optimized code commit: `9e77270c1478185efdaad136e9f93c834737ea0e`; it precomputes positional reference-window slices and adds initial-equity drawdown, max losing streak and monthly outputs. Completed rerun: [42781880648](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781880648).
- Audit cautions: MSS and FVG are mechanical proxies, not discretionary CRT; session ignores DST; variants run independently; stop distances above 5% of entry are skipped; exits are bounded to the next reference window, which gives different maximum holding horizons across reference timeframes. Treat outputs as exploratory until runtime and methodology audit are complete.

## BTCUSD — Fibonacci retracement (experimental)

### Initial run (superseded; do not use as final evidence)
- Code revision: initial `research/fibo_backtest.py`; workflow [run 42777665691](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42777665691).
- Rules intended: 1H confirmed pivots with 3 bars left/right; retracement entry at 0.50, 0.618 or 0.50–0.618 zone; rejection, engulfing or previous-candle break confirmation; swing or 0.786 stop; 1.272/1.618 extension or 2R target; 15m execution.
- Cost: assumed 12bp round trip; no funding; SL first on same candle; 7-day max holding period; chronological 70/30 split.
- Status: superseded. It had a stale-leg validity issue, a time-exit calculation issue and an incorrect drawdown baseline. Do not use its outputs.

### Corrected run
- Corrected code commit: `5c5933b725cf1f226ed91c2af4c441ac1ddb6c9c`
- Initial corrected workflow: [run 42781365500](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781365500); final drawdown-corrected workflow: [run 42781653275](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781653275)
- Corrections: require contiguous 1H pivot windows; reject ambiguous same-bar high/low pivots; expire a Fibonacci leg when the next pivot is confirmed; bound time-exit price/time to the 7-day holding window; add max losing streak and monthly breakdown outputs.
- Completed corrected pivot/leg/time-exit run [42781365500](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781365500); the final drawdown-corrected rerun [42781653275](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781653275) also completed successfully and reproduced the metrics with the initial-equity drawdown baseline fixed. Dataset: 70,079 15m rows, 0 gaps, 2024-11-10 08:30 UTC to 2026-11-10 08:00 UTC; 3,450 confirmed 1H pivots; 2,736 candidate swing legs; OOS split 2026-04-05 08:15 UTC.
- All 108 OOS configurations were negative after assumed costs. Best was long, 0.50 retracement, break-previous-candle confirmation, swing-extreme stop, 1.618 extension target: 172 trades, 43.02% profitable, PF 0.977, net -1.35R, average -0.008R, correctly recalculated max DD -18.17R, max losing streak 8; outcomes 20 TP / 31 SL / 121 time exits. The 2R target version had 174 trades, PF 0.892 and net -6.20R.
- The same best candidate was much worse in training: 345 trades, PF 0.404, net -83.08R, average -0.241R, max DD -83.60R, losing streak 10. Its OOS near-breakeven result is not a stable edge. Monthly OOS net R was Apr +2.30, May -0.40, Jun -6.82, Jul -0.03, Aug -4.50, Sep +2.11, Oct +1.08, Nov +4.91 (only 7 trades). More than 70% of OOS trades timed out; do not promote.
- Final run [42781653275](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781653275) completed successfully; corrected drawdown matches the independent trade-file calculation.
- Additional rule detail: trades with stop distance greater than 5% of entry price are skipped. A trade also ends when its Fibonacci leg expires at the next confirmed pivot, even if the 7-day cap has not elapsed; therefore many TIME exits are leg-expiry exits.
- Remaining limitations: 12bp is assumed rather than fee-tier verified; no funding; no spread/slippage model beyond the flat cost; 1H pivots are a mechanical swing definition; no discretionary trend filter. The final 30% is OOS and must not be tuned against.

## BTCUSD — Supertrend (experimental)

### Supertrend 15m BTCUSD baseline (completed; rejected)
- Hypothesis: 15m Supertrend flips with ATR(7) × 2.5 may define a trend-following entry with the Supertrend line as initial stop and 2R target.
- Variants to compare: Supertrend source = HL2 versus EMA(50); optional 1H EMA(50) direction filter; fixed initial Supertrend stop.
- Entry: after a confirmed 15m direction flip, enter next 15m open. If entry is already beyond the stop, skip.
- Execution: one position at a time per configuration; SL first if stop and target touch in the same candle; assume 12bp round-trip cost; no funding in baseline; chronological 70/30 split; report trade count, profitable %, PF, net R, max DD, losing streak and monthly stability.
- Code: `research/supertrend_backtest.py`; workflow: [fixed implementation run 42781648124](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781648124). A prior pre-fix run 42781598401 is superseded.
- Implementation: ATR(7) Wilder RMA × 2.5; source HL2 or 15m EMA50; optional completed-1H EMA50 direction filter; next-open entry after confirmed direction flip; fixed stop at signal-candle Supertrend line; 2R target; skip stop distances above 5% of entry; 7-day max hold; 12bp assumed round-trip cost; SL-first and adverse gap-through stop fill; chronological 70/30 split; monthly and losing-streak metrics.
- Verified OOS result from fixed run [42781648124](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781648124): 70,079 15m bars, 0 gaps, 2024-11-10 08:30 UTC to 2026-11-10 08:00 UTC; OOS split 2026-04-05 08:15 UTC. Best OOS was EMA50 source/no 1H filter: 114 trades, 35.96% profitable, PF 0.938, net -4.99R, avg -0.044R, max DD -16.09R, max losing streak 9. EMA50 + 1H EMA50 filter: 103 trades, PF 0.827, net -13.45R, max DD -18.59R, streak 7. HL2/no filter: 234 trades, PF 0.645, net -69.17R, max DD -75.00R, streak 11. HL2 + 1H filter: 201 trades, PF 0.516, net -86.68R, max DD -86.68R, streak 14.
- Monthly stability was poor: EMA50/no-filter was positive in Jul (+11.73R), Sep (+2.40R), Oct (+1.10R), and Nov (+1.84R on one trade), but negative in Apr, May, Jun and Aug. The isolated July result does not offset the overall negative OOS result.
- Direction audit from trade-level artifact: EMA50 source/no-filter long-only was +4.67R OOS across 45 trades (PF 1.161, DD -6.52R, losing streak 6), but the same long-only variant was -12.52R in training across 121 trades (PF 0.859). The short side was negative in both periods. This is an OOS-only subgroup that fails chronological consistency and must not be promoted.
- Conclusion: none of the four pre-specified aggregate configurations showed a positive OOS edge after assumed 12bp round-trip costs. The isolated long-side OOS gain is inconsistent with training. Do not promote to validated/live. Keep separate from CRT and Fibonacci experiments.

## Next queued research family

### Donchian breakout BTCUSD baseline
- Hypothesis: a close beyond a prior rolling high/low may capture directional expansion better than a reactive Supertrend flip.
- Initial rules to preregister: 15m close breaks prior 20-bar or 55-bar Donchian boundary (boundaries shifted one bar); enter next 15m open; stop at prior 10-bar opposite extreme or 1.5 ATR; 2R/3R target; optional completed-1H EMA50 direction filter; one position at a time; 7-day max hold.
- Execution assumptions: same-bar SL first; adverse gap-through stop fill; 12bp round-trip cost; no funding in baseline; chronological 70/30 split; monthly and losing-streak reporting.
- Status: planned only; not yet run. Freeze OOS rules before execution.

## Research standards
- No lookahead: pivot levels become available only after right-side confirmation bars close; signal candle closes before next-open entry.
- No survivorship bias: BTCUSD single instrument for these experiments; future multi-asset studies must define an as-of universe.
- No production or live rule changes; do not merge to `main`; no orders or execution alerts.
- A negative or weak result rejects only the tested mechanical definition and assumptions, not the broad discretionary concept.


## BTCUSD — Donchian breakout (new experiment; run triggered)

- Hypothesis: a close outside a prior 20- or 55-bar Donchian channel may capture directional expansion more cleanly than a reactive indicator flip.
- Rules: 15m close above/below the prior channel (rolling extrema shifted one bar); enter next 15m open. Fixed initial stop is either prior 10-bar opposite extreme or 1.5 × Wilder ATR(14) from entry. Fixed target 2R or 3R. Optional completed-1H EMA50 direction filter.
- Execution: one position at a time per exact configuration; 7-day maximum hold; skip trades without a full holding horizon before each sample boundary; SL first on same 15m candle; adverse gap-through stop fill; 12bp assumed round-trip cost; no funding or separate spread/slippage model; reject stops >5% of entry.
- Matrix: 2 channel lengths × 2 stop types × 2 targets × 2 filters = 16 configurations, chronological 70/30 split, monthly breakdown, PF, net R, drawdown and max losing streak.
- Code: `research/donchian_backtest.py`; workflow: `.github/workflows/donchian-backtest.yml`; branch `ai-quant-rebuild`; initial commit `998c792b8566842f7aa93d90d0d844b45007c8ef`; workflow commit `2393fa1fd235a30bb9f57203f14c48539af8a172`.
- Completed workflow: [42785378165](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42785378165). Experimental only; no production/live changes.
- Audit note: this is a simple mechanical breakout baseline, not a complete Turtle system; no pyramiding, portfolio-level exposure, funding or dynamic trailing stop is modelled.


## Completion audit — CRT v3 and Donchian (2026-11-10)

### CRT v3 final audit
- The optimized full-matrix workflow [42781880648](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42781880648) completed successfully and uploaded the full trade, summary and monthly artifacts. Dataset: 70,079 BTCUSD 15m rows, 0 gaps, 2024-11-10 08:30 UTC to 2026-11-10 08:00 UTC; 70/30 split at 2026-04-05 08:15 UTC. Matrix: 1,520 configurations (760 per sample); 12bp assumed round-trip cost; no funding or separate spread/slippage model.
- The highest OOS row was daily-reference MSS-retest, reversed direction, 4R target, 0.1 ATR buffer, London/NY UTC proxy: 49 trades, 44.90% profitable, PF 1.878, +17.55R, DD -5.55R, losing streak 4. Its matching training result was 112 trades, PF 0.746, -19.18R. It fails chronological consistency.
- The highest training row was weekly MSS-retest, reversed, 4R, all hours: 14 trades, PF 3.076, +17.37R; its OOS result was 13 trades, PF 0.915, -1.09R. It also fails.
- A more balanced daily MSS-FVG proxy, reversed direction, 4R, 0.1 ATR buffer, London/NY UTC proxy produced +7.61R/PF 1.176 on 107 training trades and +9.05R/PF 1.500 on 50 OOS trades (46.00% profitable, DD -2.78R, losing streak 6). However, it had 73 training and 36 OOS TIME exits; only 8/17 training months and 5/8 OOS months were positive, with July 2026 (+6.60R) the dominant OOS month. It is a research lead only, not a validated edge: the matrix contains 1,520 comparisons, so post-hoc selection is a major multiple-testing risk.
- CRT v3 is a mechanical proxy, not discretionary CRT. Its stop fills are at the stop price on a hit and do not model adverse gap-through; this is an additional optimistic limitation. MSS/FVG are simplified candle rules; session is fixed UTC and ignores DST; no funding.

### Donchian final audit
- Completed workflow: [42785378165](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42785378165). Dataset: 70,079 BTCUSD 15m rows, 0 gaps, 2024-11-10 09:00 UTC to 2026-11-10 08:30 UTC; OOS split 2026-04-05 08:45 UTC. Sixteen configurations; 12bp assumed round-trip cost; no funding or separate spread/slippage model.
- Best OOS row: 20-bar Donchian, prior-10-bar stop, 2R target, no EMA filter: 127 trades, 40.94% profitable, PF 1.094, +7.67R, DD -13.40R, losing streak 7. The matching training period was 424 trades, PF 0.781, -70.21R. The only positive OOS row is therefore not stable across the chronological split.
- OOS monthly net R for that row: Apr -1.65, May +0.26, Jun -3.31, Jul +2.67, Aug +2.76, Sep -2.54, Oct +9.47. The aggregate OOS gain is concentrated in October; reject as unvalidated.
- Stop handling is SL-first with adverse gap-through fills. The 1.5 ATR stop variants traded excessively and suffered very large losses; do not optimize around them.

## BTCUSD — Liquidity sweep reversal (completed; rejected)
- Hypothesis: a confirmed 1H swing high/low that is wicked through and reclaimed on 15m may identify a liquidity sweep reversal.
- Exact causal rules: strict 3-left/3-right 1H pivots; pivot level becomes active only after the third right-hand 1H bar closes; latest confirmed high and low only; each level is consumed once by a sweep or breakout invalidation. Sweep = 15m wick beyond the level and close back inside. Test immediate next-open entry versus waiting up to four 15m bars for a close beyond the sweep candle in the reversal direction; for delayed confirmation, reject if the sweep extreme is retaken before entry.
- Matrix: sweep threshold 0/0.1 × confirmation reclaim/break-sweep × stop buffer 0/0.1 ATR(15m) × target 1.5R/2R/3R × no filter/EMA50-aligned completed-1H filter × all hours/UTC 07:00–22:00 = 96 configurations. One position at a time per configuration; 48h max hold; 70/30 chronological split.
- Execution: next 15m open; stop beyond sweep wick plus optional ATR buffer; same-bar SL/TP resolves SL first; adverse gap-through stop fill; reject stop distances >5%; skip trades crossing sample boundaries or a 15m data gap. Cost 12bp assumed round-trip; no funding or separate spread/slippage model.
- Code: `research/liquidity_sweep_backtest.py` (latest code commit `697064a99d49ffd10112b6059c0a71c6bb5ec749`); workflow: `.github/workflows/liquidity-sweep-backtest.yml` (commit `92a539cd16db605709ce39df062991ae12ac8d84`); branch `ai-quant-rebuild`.
- Completed workflow: [42789356031](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42789356031); artifact ID 13750911922. The workflow completed successfully and its trade, summary and monthly CSVs were inspected. Exploratory only; no production changes.


### Liquidity sweep result
- Data: 70,079 BTCUSD 15m rows, 0 gaps, 2024-11-10 09:30 UTC to 2026-11-10 09:00 UTC; 17,519 complete 1H bars; OOS split 2026-04-05 09:15 UTC. The exact 15m CSV SHA-256 is recorded in `liquidity_sweep_methodology.json`.
- All 96 OOS configurations were negative after the assumed 12bp round-trip cost; none had PF above 1. The least-bad OOS row was 0.1 ATR sweep threshold, immediate reclaim, no stop buffer, 3R target, EMA50-aligned filter, London/NY UTC proxy: 24 trades, 33.33% profitable, PF 0.735, -7.12R, DD -8.02R, losing streak 4 (8 TP / 16 SL).
- The best training row was 0.1 ATR sweep threshold, break-sweep confirmation, 0.1 ATR stop buffer, 3R, EMA50-aligned, London/NY proxy: 35 trades, PF 1.199, +5.50R. Its matching OOS result was 21 trades, PF 0.465, -10.97R, DD -10.97R, losing streak 5. This is a clear train/OOS failure.
- Best OOS row was positive in only 3 of 8 OOS months (one of those months had a single trade); monthly returns were concentrated and unstable. Reject this exact mechanical pivot-sweep model. This does not reject discretionary liquidity-sweep/SMC trading generally.
- Limitations: 1H 3/3 pivots and latest-level-only logic are mechanical; fixed UTC session ignores DST; no funding or separate spread/slippage model; 12bp is assumed, not fee-tier verified. OOS matrix comparisons still create selection risk even though no OOS row was positive.

## Next BTC research family — intraday market-structure break / retest continuation (scope revised 2026-11-10)

- User clarified that the research objective is intraday trading. The prior swing-style framing is superseded; do not run a 48h swing-hold study as the next experiment.
- Hypothesis: an intraday 15m close beyond a causally confirmed 1H swing high/low may produce a continuation edge, particularly after a controlled retest and reclaim.
- Intraday constraints: 15m execution; 1H structure context only; strict maximum holding time of 8 hours; force-close any open position at the 8h horizon; no positions carried beyond that horizon. Test UTC session buckets separately (00:00–06:59, 07:00–12:59, 13:00–18:59, 19:00–23:59) as well as all-hours. Crypto is 24/7, so these are research buckets, not claims about exchange sessions.
- Causal structure: strict confirmed 1H 3/3 and 5/5 pivots; a pivot becomes usable only after its right-side confirmation bars close. Use latest eligible swing high/low; no future pivot knowledge.
- Entries: compare next-15m-open entry after a close beyond the confirmed level against a retest/reclaim entry within eight 15m bars. Cancel a pending retest if the level is decisively reclaimed against the breakout direction or the setup expires.
- Risk variations: stop at breakout-candle opposite extreme or 1.0/1.5 × 15m ATR(14); targets 1.5R/2R/3R; optional completed-1H EMA50 alignment. One position at a time per configuration.
- Execution: SL first when stop and target touch within the same 15m candle; adverse gap-through stop fill; 12bp assumed round-trip cost; no funding or separate spread/slippage model (state this limitation); reject stops >5% of entry; skip data-gap-crossing and sample-boundary trades.
- Evaluation: chronological 70/15/15 train/validation/OOS split (not the earlier 70/30 split), with rules and candidate selection frozen before OOS evaluation. Report trade count, profitable rate, PF, net R, max drawdown, losing streak, monthly results, and UTC-bucket stability. Apply a minimum sample-size warning; do not promote a tiny-sample winner.
- Keep this intraday study experimental. No live/production rule changes, no merge to main, no orders or execution alerts.


## BTCUSD — intraday market-structure break / retest (run in progress)

- Scope: user clarified intraday only. This replaces the prior 48h swing-hold framing for the next study.
- Hypothesis: a 15m close through a causally confirmed 1H swing level may continue intraday; a retest/reclaim may improve entry quality.
- Data: Delta Exchange India BTCUSD 15m, fetched fresh at execution; two-year API lookback, incomplete current candle discarded; script records exact row count, UTC range, gaps and CSV SHA-256.
- Structure: strict 1H pivot high/low with symmetric 3/3 or 5/5 bars; level is usable only after the right-side confirmation hour closes. First 15m close through latest confirmed level creates a BOS event.
- Entry matrix: next-open breakout vs first retest/reclaim within eight 15m bars; cancel retest if close crosses back through the broken level.
- Risk matrix: breakout-candle opposite extreme, 1.0× 15m Wilder ATR(14), or 1.5× ATR; targets 1.5R/2R/3R; no filter vs completed-1H EMA50 alignment; all hours vs UTC buckets 00–07, 07–13, 13–19, 19–24.
- Intraday controls: one position at a time per configuration; maximum 8h / 32 15m bars; force close at horizon; no sample-boundary or data-gap-crossing trades; reject stop distances >5%.
- Costs/execution: assumed 12bp round trip deducted as entry × 0.0012 / initial risk; fee tier not verified; no funding or separate spread/slippage model; same-bar stop/target ambiguity resolves stop first; adverse gap-through stop fill.
- Evaluation: chronological 70% train / 15% validation / 15% OOS. Train screen: >=40 trades, positive net R, PF>=1.05, max DD>=-25R; shortlist top 25 by net_R/abs(maxDD). Validation screen: >=20 trades, positive net R, PF>=1.05, max DD>=-15R, positive in >=50% of active months. Select one by validation net_R/abs(maxDD); evaluate OOS once for that selected configuration only. If no candidate passes, OOS is not evaluated.
- Code: `research/intraday_mss_backtest.py`; workflow: `.github/workflows/intraday-mss-backtest.yml`; branch `ai-quant-rebuild`; workflow commit `1622b51f14ed78b70cb9f363dade0c0f1c77d1b4`; script commit `27053cef89c4aec41ea381df98721b936ba741ad`.
- Workflow run: [42797973294](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42797973294) — running at ledger entry time. Do not quote performance until run completes and artifacts are inspected.
- Limitations: single BTCUSD instrument; UTC buckets are time-of-day buckets, not exchange sessions; mechanical BOS/retest definition; funding omitted; assumed 12bp cost not fee-tier verified. Experimental only; no production changes or orders.


### Intraday market-structure break / retest result — completed, rejected (2026-11-10)

- Workflow [42798099082](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42798099082) completed successfully; full artifact ID 13754712382 was downloaded and the train/validation CSVs inspected. Repository CI [42798099329](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42798099329) also passed, including compileall and the existing test suite.
- Data: 70,079 BTCUSD 15m bars, 17,519 complete 1H bars, 0 gaps; 2024-11-10 10:30 UTC through 2026-11-10 10:00 UTC; SHA-256 `ae1a7df4dfcec9ab2f25f2b8a76b27b94c225a58f1970293e4179074045ebc97`. Train/validation split timestamps: 2026-04-05 10:15 UTC and 2026-07-23 22:15 UTC; OOS would start at the latter.
- Matrix: 360 configurations. Ten met the training screen; all ten failed validation. The best training configuration (5/5 pivots, retest, 1.5 ATR stop, 3R, no EMA filter, 07:00–13:00 UTC) made +15.53R/PF 1.321 on 61 training trades, but its validation was -9.32R/PF 0.224 on 11 trades. The EMA-filtered sibling made +14.53R/PF 1.370 on 51 training trades, then -8.16R/PF 0.248 on 10 validation trades.
- Best validation-only row (5/5 breakout, 1.5 ATR stop, 2R, 1H EMA50 filter, 13:00–19:00 UTC) made +4.02R/PF 1.127 on 49 validation trades, but the matching training segment was -74.86R/PF 0.576 on 208 trades, DD -80.51R and 11-loss streak. This is not a valid candidate.
- No configuration passed the pre-registered train-to-validation selection funnel; **OOS was deliberately not evaluated**. No OOS return, win rate or drawdown should be claimed. Reject this exact mechanical BOS/retest setup for now; this does not reject all discretionary market-structure methods.
- Execution assumptions: 8h maximum hold, one position at a time/configuration, 12bp assumed round-trip cost, no funding or separate spread/slippage model, SL-first same-bar ambiguity, adverse gap-through stop fills, 5% maximum stop-distance cap.
- Follow-up code hardening: gap validation now checks the entire interval from breakout candle through the full holding horizon (commit `097baa99237da09890bffa2afa5cc68a86b2f275`). The completed dataset had zero gaps, so this defensive change does not alter the reported run; it is included for future datasets.

## Next queued intraday BTC family — EMA pullback continuation

- Hypothesis: when completed 1H trend is established, a 15m pullback to a short EMA followed by directional rejection may offer a cleaner intraday continuation entry than raw BOS/retest.
- Trend: completed 1H close above/below EMA50, with EMA50 slope compared to four completed 1H bars earlier; long-only above/rising and short-only below/falling.
- Pullback levels: 15m EMA20 or EMA50; candle must trade within 0.15 × 15m ATR(14) of the EMA and close back on the trend side.
- Confirmation variants: close beyond prior 15m candle high/low, or bullish/bearish engulfing body. Entry next 15m open after confirmation.
- Risk matrix: signal-candle swing extreme vs 1.0×/1.5× ATR(14) stop; 1.5R/2R/3R targets; maximum 8h holding; force-close at horizon; one position at a time.
- Evaluation: chronological 70/15/15 train/validation/OOS; choose using training and validation only, evaluate OOS once for the selected candidate; report monthly, long/short and UTC-bucket performance.
- Costs and execution: carry forward the 12bp assumed round-trip cost, SL-first, adverse gap-through stop fill, skip gap-crossing/boundary trades and >5% stops; no funding/separate spread model unless historical data is successfully obtained.
- Keep experimental and separate from production. No orders, execution alerts or main-branch changes.


## BTCUSD — intraday EMA pullback continuation (new experiment; run triggered)

- Hypothesis: a 15m pullback to EMA20/EMA50 followed by directional rejection may continue in the direction of a completed 1H EMA50 trend.
- Data: Delta Exchange India BTCUSD 15m via the existing `crt_backtest.fetch("15m")` downloader; two-year lookback, incomplete current candle discarded. Script writes row count, UTC date range, gaps, largest gap, complete 1H bar count and CSV SHA-256.
- Trend filters: completed 1H close above/below EMA50; compare (1) price side only, (2) EMA50 slope versus four completed 1H bars earlier, (3) slope plus EMA200 alignment. Completed 1H data only; no unfinished-hour lookahead.
- Pullback: 15m low (long) or high (short) within 0.15 × 15m ATR(14) of EMA20 or EMA50; signal candle closes back on trend side.
- Confirmation: close beyond previous 15m candle high/low, or strict bullish/bearish body engulfing. Entry at next 15m open.
- Risk matrix: signal-candle low/high, 1.0 × ATR(14), or 1.5 × ATR(14) stop; 1.5R/2R/3R targets; all hours or UTC 00–07, 07–13, 13–19, 19–24. 540 total configurations; both directions are evaluated and reported separately.
- Intraday controls: one position at a time/configuration; maximum 8h (32 15m bars), forced close at horizon; no sample-boundary or gap-crossing trades; reject stops >5% of entry.
- Execution/costs: SL first on same-bar ambiguity; adverse gap-through stop fill; 12bp assumed round-trip cost; no funding or separate spread/slippage model; fee tier not verified.
- Evaluation: chronological 70/15/15 train/validation/OOS. Train screen >=40 trades, positive net R, PF>=1.05, DD no worse than -25R; top 25 by net_R/abs(maxDD). Validation screen >=20 trades, positive net R, PF>=1.05, DD no worse than -15R, positive in >=50% active months. Evaluate OOS once for the single validation-selected configuration only; if none passes, OOS is not evaluated.
- Code: `research/ema_pullback_intraday_backtest.py`; workflow `.github/workflows/ema-pullback-intraday-backtest.yml`; branch `ai-quant-rebuild`; workflow commit `21488e06efba32d08bffcc1f7a45a6da8dc1b488`; script commit `f37c1cb78827f762a59f9196a9fd8a89840200f9`.
- Status: workflow auto-triggered by script push; awaiting completion and artifact inspection. Do not quote results until completed logs/artifacts are verified.
- Limitations: single BTCUSD instrument; UTC buckets are time-of-day buckets, not exchange sessions; mechanical EMA touch/engulfing definitions; assumed costs; no funding, separate spread model, or portfolio leverage/correlation model. Experimental only; no production changes, orders or alerts.


### Intraday EMA pullback result — completed, rejected (2026-11-10)

- Workflow [42805417259](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42805417259) completed successfully; artifact ID 13758322093 was downloaded and both summary CSVs were inspected. Repository CI [42805417161](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42805417161) passed.
- Data: 70,079 BTCUSD 15m bars, 17,519 complete 1H bars, zero 15m gaps; 2024-11-10 11:15 UTC through 2026-11-10 10:45 UTC. Train/validation boundaries: 2026-04-05 11:00 UTC and 2026-07-23 23:00 UTC; OOS would begin at the latter. Dataset SHA-256: `8bc0dd27dfdd32b30fc5dda31f95cb63785e0759388ec5ba4f33fcfe9bfcd8a0`.
- Matrix: 540 configurations (EMA20/EMA50 pullback; previous-bar-break/engulfing; three 1H EMA trend filters; three stops; three targets; five UTC buckets). Nine passed the training screen and all nine were shortlisted; zero passed validation.
- Best training row: EMA50 pullback, engulfing, 1H EMA50 price-side filter, 1.5 ATR stop, 3R target, 13:00–19:00 UTC: 69 trades, 43.48% profitable, PF 1.359, +16.49R, max DD -6.59R, losing streak 4. Its matching validation row: 14 trades, 42.86% profitable, PF 1.082, +0.86R, DD -5.37R, streak 3. It fails the pre-registered minimum 20 validation trades.
- Another train-positive configuration (EMA50 engulfing, EMA50 slope + EMA200 filter, 1.5 ATR stop, 3R, 13:00–19:00 UTC) made +14.67R/PF 1.433 on 53 train trades, but only 11 validation trades (+2.21R/PF 1.280), also below the sample threshold.
- Best validation-only row: EMA20 pullback, previous-bar-break, EMA50 slope + EMA200 filter, 1.5 ATR stop, 3R, 07:00–13:00 UTC: 44 validation trades, 45.45% profitable, PF 1.542, +17.66R, DD -6.77R, losing streak 5, positive in all active validation months. Its matching training segment had 199 trades, PF 0.712, -53.98R, DD -58.19R and a 14-loss streak. This is a strong train/validation regime inconsistency, not a candidate.
- **No configuration passed the pre-registered train-to-validation funnel; OOS was deliberately not evaluated.** Do not report OOS performance or promote this mechanical EMA pullback model.
- Execution/cost assumptions: 8h max hold; one position at a time/config; 12bp assumed round-trip; no funding or separate spread/slippage model; SL-first same-bar resolution; adverse gap-through stop fill; >5% stop distances and gap/boundary-crossing trades skipped.
- Next step: stop broad EMA parameter search for now. Test a structurally distinct intraday support/resistance rejection model with levels formed from confirmed prior-day and completed 4H swing ranges, strict causal availability, rejection/close confirmation, structural/ATR stops and 1.5R/2R/3R targets. Keep the same 8h cap, 70/15/15 funnel and OOS embargo.


## Intraday market-structure break/retest — corrected verification run (2026-11-10)

- Corrected verification workflow [42798388761](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42798388761) completed successfully on branch `ai-quant-rebuild`; artifact ID 13755382983.
- Data: 70,079 BTCUSD 15m candles, 17,519 complete 1H candles, zero 15m gaps; 2024-11-10 10:30 UTC to 2026-11-10 10:00 UTC. Dataset SHA-256 `ae1a7df4dfcec9ab2f25f2b8a76b27b94c225a58f1970293e4179074045ebc97`. Chronological boundaries: train ends 2026-04-05 10:15 UTC; validation ends 2026-07-23 22:15 UTC.
- Matrix: 360 configurations. Ten passed the training screen and were shortlisted; zero passed the preregistered validation screen. **OOS was not evaluated.** This confirms no candidate qualified for OOS; do not promote the mechanical BOS/retest model.
- The rerun includes the defensive gap-window check; no data gaps were present, so the correction did not change this dataset's coverage result.

## BTCUSD — intraday support/resistance rejection (new experiment; running)

- Hypothesis: rejection of a fully known prior-day high/low or causally confirmed 4H swing level, followed by a 15m reclaim or break of the rejection candle, may provide an intraday mean-reversion edge.
- Levels: previous completed UTC-day high/low (not current-day developing extremes); strict 4H 2/2 and 3/3 swing pivots, available only after all right-side confirmation bars close. Each level is consumed once by rejection or invalidation; pivot levels are replaced by newer confirmed pivots. Delayed confirmation is cancelled if the level is invalidated or replaced before confirmation.
- Signal: sweep/penetration through level by 0 or 0.1 × 15m ATR(14), then close back inside. Compare immediate reclaim entry with a close beyond the rejection candle extreme within four 15m bars. Enter next 15m open; prior-day-level entries must occur before that level expires at the next UTC day.
- Matrix: 3 level families × 2 penetration thresholds × 2 confirmations × 3 stops (rejection wick + 0.1 ATR, 1 ATR, 1.5 ATR) × 3 targets (1.5R/2R/3R) × 2 completed-1H EMA50 filters × 5 UTC time buckets = 1,080 configurations.
- Execution/evaluation: one position at a time/config; maximum 8h/32 15m bars; forced time exit; 70/15/15 chronological split; training screen >=40 trades, positive net R, PF>=1.05, drawdown >=-25R; shortlist top 25; validation screen >=20 trades, positive net R, PF>=1.05, drawdown >=-15R, positive in >=50% active months; OOS only for one validation-selected candidate. Same-bar SL first, adverse gap-through stop fill, skip >5% stops and gap/boundary-crossing trades.
- Costs/limitations: assumed 12bp round-trip; actual fee tier unverified; no funding or separate spread/slippage model. UTC buckets are time-of-day bins, not exchange sessions. Single BTCUSD instrument.
- Code: `research/sr_rejection_intraday_backtest.py`; workflow `.github/workflows/sr-rejection-intraday-backtest.yml`; branch `ai-quant-rebuild`. Script commit `df3a7854dc83368ae320edcba9140f7ecce96616`; workflow commit `030c2047d32470d5778d6346bd9f99d7bbec9a6a`; daily-level expiry guard commit `193ab6973f495846eebb940a1ed0c8f070b892ad`.
- Workflow [42814582640](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42814582640) was triggered; await completion and inspect logs/artifacts before reporting performance.
- Experimental only: no production changes, no orders or execution alerts, no `main` branch changes.


### Intraday market-structure verification — detailed artifact audit

- The corrected run's artifact (13755382983) was downloaded and both train/validation summary CSVs inspected.
- Best training candidate: 5/5 pivot retest, 1.5 ATR stop, 3R target, no EMA filter, 07:00–13:00 UTC: 61 trades, 40.98% profitable, PF 1.321, +15.53R, DD -10.46R, losing streak 8. Matching validation: 11 trades, 18.18% profitable, PF 0.224, -9.32R, DD -9.32R, losing streak 4.
- Best validation-only row: 5/5 pivot breakout, 1.5 ATR stop, 2R target, EMA50 filter, 13:00–19:00 UTC: 49 trades, 46.94% profitable, PF 1.127, +4.02R, DD -10.53R, streak 5. Its matching training period: 208 trades, PF 0.576, -74.86R, DD -80.51R, streak 11. No train/validation-consistent candidate; OOS correctly not evaluated.

### Intraday support/resistance rejection — completed, rejected (2026-11-10)

- Workflow [42814582640](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42814582640) completed successfully; artifact ID 13763168703. Script compiled and 1,080 configurations executed.
- Data: 70,079 BTCUSD 15m bars, 17,519 complete 1H, 4,379 complete 4H, 729 complete daily bars; zero 15m gaps; 2024-11-10 12:30 UTC to 2026-11-10 12:00 UTC. Dataset SHA-256 `3a78948aa55d5b693983aa3cf5625f277d13af2b3e5906080180d9a59a60c67d`. Train ends 2026-04-05 12:15 UTC; validation ends 2026-07-24 00:15 UTC.
- Twelve configurations passed the train screen and were shortlisted; **zero passed validation; OOS was not evaluated**.
- Best training row: prior-day high/low, 0.1 ATR penetration, reclaim, 1.5 ATR stop, 2R target, no EMA filter, 19:00–24:00 UTC: 45 trades, 55.56% profitable, PF 1.436, +10.25R, DD -8.37R, losing streak 3, positive in 66.7% of active months. Matching validation: only 9 trades, 55.56% profitable, PF 1.426, +2.07R, DD -1.48R, streak 1; below the 20-trade minimum.
- Best validation-only row: prior-day level, break-rejection confirmation, 1 ATR stop, 3R target, no filter, 13:00–19:00 UTC: 9 trades, 55.56% profitable, PF 2.281, +6.98R, DD -2.66R, streak 2; matching training was 43 trades, PF 0.551, -19.41R, DD -25.36R, streak 16. This is not a valid candidate.
- 4H-pivot variants had very small samples (3–5 trades in top rows). Do not interpret them as evidence of edge. Reject this exact mechanical model; this does not disprove discretionary support/resistance trading.
- Costs and limitations remain 12bp assumed round trip; no funding or separate spread/slippage model; UTC time buckets; single BTCUSD instrument; 8h max hold; SL-first and adverse gap-through stop fills.
- OOS was deliberately left untouched because no candidate passed validation.


## Next BTC intraday family — UTC-anchored VWAP deviation reversion (running)

- Hypothesis: after a statistically meaningful intraday extension beyond a daily VWAP deviation band, a 15m close reclaiming the band may capture reversion toward VWAP.
- Data: Delta BTCUSD 15m candles; exchange-reported candle volume is used as a weighting proxy. This is not a consolidated market-wide VWAP. Require a valid, positive volume series; record zero-volume bars, total volume, date coverage, gaps and CSV SHA-256.
- VWAP: reset cumulative typical-price × volume and volume at 00:00 UTC. Compute volume-weighted standard deviation from cumulative first and second moments. Signal candle compares with VWAP and deviation bands shifted one full 15m candle, preventing use of its own volume/price to set the reference band.
- Signal: previous close outside the prior lower/upper band and current close reclaims inside, while remaining on the outer side of VWAP. Compare simple reclaim with directional engulfing reclaim. Bands: 1.0, 1.5, 2.0 standard deviations.
- Risk matrix: signal-candle extreme +0.1 ATR, 1 ATR or 1.5 ATR stop; 1.5R/2R/3R targets; optional completed-1H EMA50 trend-aligned filter; all hours or four UTC time buckets; long and short signals both evaluated.
- Intraday controls: next 15m open entry; one position at a time/config; 8h maximum hold; force exit at horizon; 70/15/15 chronological split; fixed train/validation funnel; evaluate OOS once only if a candidate passes validation.
- Execution/costs: SL first on same-bar ambiguity; adverse gap-through stop fill; 12bp assumed round-trip; no funding or separate spread/slippage model; skip gap-crossing, boundary-crossing and >5% stop trades.
- Code: `research/vwap_reversion_intraday_backtest.py`; workflow `.github/workflows/vwap-reversion-intraday-backtest.yml`; branch `ai-quant-rebuild`; script commit `e8c861568e796ee2f24e4c13ebb167687cc85226`; workflow commit `556c9414a7d0bfbff05cc37a0aa2d4b09fa584f7`; session-boundary mask fix `c6172641b19e370206556b51715b83c3729257f6`.
- Workflow [42814968615](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42814968615) triggered; compile and backtest status to be checked. No performance claim until logs and artifacts are inspected.
- Keep experimental only; no production changes, orders, execution alerts or `main` branch changes.


### Intraday UTC-anchored VWAP deviation reversion — completed, rejected (2026-11-10)

- Workflow [42814968615](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42814968615) completed successfully; artifact ID 13763903797. Script compiled and all 540 configurations executed.
- Dataset: Delta BTCUSD 15m, 70,079 rows, 0 missing intervals; 2024-11-10 12:30 UTC to 2026-11-10 12:00 UTC; 17,519 complete 1H bars; 80 zero-volume bars; total reported candle volume 7,243,420,002. Dataset CSV SHA-256 `1384d16567016d08b47ccc8ebe6999e88fe123475919675693fc333d3487b076`. Train ends 2026-04-05 12:15 UTC; validation ends 2026-07-24 00:15 UTC; OOS begins 2026-07-24 00:15 UTC.
- Rules: UTC-day cumulative typical-price × exchange-reported volume VWAP and volume-weighted standard deviation; band references lagged one full 15m candle; previous close outside band followed by close reclaiming inside but still outside VWAP; simple reclaim or engulfing-reclaim; 1.0/1.5/2.0 SD bands; signal-extreme +0.1 ATR, 1 ATR or 1.5 ATR stop; 1.5R/2R/3R target; optional completed-1H EMA50 direction filter; all hours or four UTC time buckets; next 15m open; 8h max hold.
- Funnel: only 1 of 540 configs passed training; it was shortlisted, but 0 passed validation. OOS was correctly not evaluated.
- Best training config: 2 SD band, engulfing reclaim, 1.5 ATR stop, 3R target, no EMA filter, 07:00–13:00 UTC: 131 trades, 39.69% profitable, PF 1.071, +7.42R, average +0.057R/trade, DD -12.50R, losing streak 6; 61.1% positive active months. Matching validation: 21 trades, 33.33% profitable, PF 0.632, -7.47R, DD -12.65R, losing streak 4, 0% positive active months.
- Best validation-only row: 1.5 SD, engulfing reclaim, 1.5 ATR stop, 2R target, no filter, 00:00–07:00 UTC: 72 trades, 51.39% profitable, PF 1.216, +9.29R, DD -16.77R, losing streak 7, 75% positive active months. Matching training was 375 trades, PF 0.608, -119.98R, DD -140.37R, losing streak 13. Severe train/validation inconsistency; reject.
- Methodology: chronological 70/15/15; one position/config; SL first; adverse gap-through stop fill; 12bp assumed round-trip; no funding or separate spread/slippage model. Delta candle volume is an exchange-specific contract-volume proxy, not consolidated market-wide VWAP. OOS remains untouched.
- Code: `research/vwap_reversion_intraday_backtest.py`; workflow `.github/workflows/vwap-reversion-intraday-backtest.yml`; final code commit `c6172641b19e370206556b51715b83c3729257f6`. Artifact contents (train/validation summaries and data-quality JSON) were downloaded and audited.

## Next BTC intraday family — UTC opening-range breakout (running)

- Hypothesis: the first 15m close outside a completed one-hour UTC opening range may capture intraday expansion. This is a mechanical ORB baseline, not a discretionary market-session strategy.
- Data: Delta BTCUSD 15m; same 730-day fetch and causal completed-1H EMA50 context; dataset SHA-256, coverage and gaps to be recorded after run.
- Opening ranges: four completed 15m bars beginning at UTC 00:00, 07:00, 13:00 or 19:00. During the following UTC block, take only the first 15m close outside the range, with 0 or 0.1 × signal-bar ATR(14) breakout buffer; enter next 15m open.
- Matrix: 4 UTC anchors × 2 breakout buffers × 4 stops (opposite range edge, breakout-candle extreme + 0.1 ATR, 1 ATR, 1.5 ATR) × 4 targets (1.5R/2R/3R/4R) × 2 filters (none/completed-1H EMA50 aligned) = 256 configurations.
- Execution: one position at a time/config; max 8h/32 15m bars; force time exit; one first-breakout signal per opening-range block; reject >5% stop; skip gaps and sample-boundary trades; same-bar SL first; adverse gap-through stop fill; target gaps receive no favourable improvement.
- Selection: chronological 70/15/15; train >=40 trades, positive net R, PF>=1.05, DD >=-25R; shortlist top 25 by net-R/drawdown; validation >=20 trades, positive net R, PF>=1.05, DD >=-15R, positive in >=50% active months; evaluate OOS once only if a candidate passes validation.
- Costs: 12bp assumed round trip; actual fee tier unverified; no funding or separate spread/slippage model. UTC anchors are fixed clock buckets, not DST-adjusted London/NY opens.
- Code: `research/intraday_orb_backtest.py`; workflow `.github/workflows/intraday-orb-backtest.yml`; branch `ai-quant-rebuild`; workflow commit `f1d0131da78331a74408e900431368182020262d`; script commit `757caed5495903332c54ecd5210c04c2e57f0106`.
- Workflow [42823428170](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42823428170) was triggered; inspect completion, logs and artifact before reporting any performance. Experimental only; no live/production changes.


### Intraday UTC opening-range breakout — completed, rejected (2026-11-10)

- Initial run [42823428170](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42823428170) failed at runtime because the opening-range timestamp vector was a NumPy array without a DatetimeIndex `.asi8` attribute. This was fixed in commit `c69f76989a8725ca392551b35e59f0aa04491206`; the corrected run [42823544670](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42823544670) compiled, executed all 256 configurations and uploaded artifact ID 13767394390. The failed run is not treated as a result.
- Dataset: Delta BTCUSD 15m, 70,079 rows, zero gaps; 2024-11-10 13:30 UTC to 2026-11-10 13:00 UTC; 17,519 complete 1H bars. CSV SHA-256 `b48732745bab603714d3fe76268868b8bb141e1734e5db1006082b22452d09f5`. Train ends 2026-04-05 13:15 UTC; validation ends 2026-07-24 01:15 UTC; OOS begins 2026-07-24 01:15 UTC.
- Rules: one-hour opening ranges from four 15m bars beginning 00:00/07:00/13:00/19:00 UTC; first subsequent 15m close beyond range with 0/0.1 ATR buffer; next-open entry; opposite-range, breakout-candle +0.1 ATR, 1 ATR or 1.5 ATR stop; 1.5R/2R/3R/4R target; optional completed-1H EMA50 alignment; one trade at a time/config; 8h maximum hold.
- Result: **0 of 256 configurations passed the training screen**; no shortlist and no validation pass. OOS was correctly not evaluated.
- Least-bad training row: 13:00 UTC range, 0.1 ATR buffer, opposite-range stop, 4R target, EMA50 filter: 332 trades, 36.75% profitable, PF 0.934, -12.45R, average -0.038R, DD -45.64R, losing streak 11, positive in 38.9% of active months (21 TP /126 SL /185 TIME; 169 long /163 short). Matching validation: 77 trades, 31.17% profitable, PF 0.433, -28.63R, DD -28.63R, losing streak 5, no positive active month (0 TP /34 SL /43 TIME).
- Best validation-only row was still negative: 07:00 UTC range, 0.1 ATR buffer, opposite-range stop, 1.5R target, EMA50 filter: 65 trades, 46.15% profitable, PF 0.931, -2.63R, DD -7.33R, losing streak 7, positive in 50% of active months. Its matching training result was 305 trades, PF 0.633, -77.38R, DD -79.95R, losing streak 8, positive in 27.8% of active months.
- The best training row was positive in only 7/18 active months; its matching validation row lost in all 4 active months. Reject this mechanical ORB baseline.
- Execution/cost limitations: SL first on same-bar ambiguity; adverse gap-through stop fill; 12bp assumed round-trip; no funding or separate spread/slippage model. UTC anchors are fixed time buckets, not DST-adjusted exchange session opens. The 4R target was only a target parameter; the tested strategy's realised expectancy was negative.
- Code: `research/intraday_orb_backtest.py`; workflow `.github/workflows/intraday-orb-backtest.yml`; branch `ai-quant-rebuild`; workflow commit `f1d0131da78331a74408e900431368182020262d`; final code commit `c69f76989a8725ca392551b35e59f0aa04491206`. Artifact summaries and monthly CSVs were downloaded and inspected.

## Next BTC intraday family — Supertrend flip continuation with 8h cap (preregistered)

- Motivation: prior Supertrend test used a multi-day holding horizon and was negative OOS; test a distinct strictly intraday version with the same indicator concept and a hard 8h cap, rather than reusing its results as if already intraday.
- Hypothesis: a confirmed 15m Supertrend direction flip may have short-horizon continuation when entry is next-bar open and stop remains at the signal-bar Supertrend line.
- Rules: 15m Supertrend source HL2 or 15m EMA50; Wilder ATR length 7 or 10; multiplier 2.0/2.5/3.0; signal only on confirmed direction flip at candle close; enter next 15m open; initial stop is the signal-bar Supertrend line; fixed target 1.5R/2R/3R; optional completed-1H EMA50 direction filter; evaluate both directions together, long-only and short-only; all hours or four UTC time buckets; one position/config; maximum 8h/32 bars, force time exit.
- Matrix: 2 sources × 2 ATR lengths × 3 multipliers × 3 targets × 2 filters × 3 direction modes × 5 session modes = 1,080 configurations.
- Execution/selection: causal closed-candle indicator; same-bar SL first; adverse gap-through stop fill; skip >5% stops, gaps and sample-boundary trades; 12bp assumed round trip; chronological 70/15/15; same train/validation funnel as preceding intraday studies; OOS once only if a candidate passes validation.
- Limitations: 12bp is assumed, not fee-tier verified; no funding or separate spread/slippage model; UTC buckets ignore DST; OHLC backtest cannot resolve intrabar order beyond SL-first.
- Code/workflow are being added on `ai-quant-rebuild` only. No live/production changes, orders, alerts or main-branch changes.

- Implementation: `research/supertrend_intraday_backtest.py`; workflow `.github/workflows/supertrend-intraday-backtest.yml`; workflow commit `22cfb9423e655b3e429ac777d89ac0808bfad4a9`; initial code commit `8402dcc6064756e9576a8ac906a2e7ed08ad7775`; session-filter correction commit `707f6d233a7b1b400715af830012c124423afec4` (UTC bucket is assigned by actual next-bar entry time, not signal-candle time).
- Initial run [42823897545](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42823897545) was started against the initial code; corrected run [42823967966](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42823967966) uses the session-boundary correction. At ledger update time both are still running; only the corrected run may be used for reported results. No performance result is claimed yet.


## Intraday BTCUSD Supertrend flip continuation — completed, rejected (2026-11-10)

- Corrected workflow [42823967966](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42823967966) completed successfully; artifact ID 13767464963 was downloaded and inspected. The older run [42823897545](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42823897545) is superseded; only the corrected entry-time session assignment run is used.
- Dataset: Delta BTCUSD 15m, 70,079 rows, zero gaps; 2024-11-10 13:30 UTC to 2026-11-10 13:00 UTC; 17,519 complete 1H bars. Dataset CSV SHA-256 `1b896d35e78bb9354794c6086fd297c17aae142214a4ac7c8665cb6c81ee63fa`. Train ends 2026-04-05 13:15 UTC; validation ends 2026-07-24 01:15 UTC; OOS begins 2026-07-24 01:15 UTC.
- Rules/matrix: confirmed 15m Supertrend direction flip; Wilder ATR(7/10), multiplier 2/2.5/3; source HL2 or 15m EMA50; next 15m open entry; fixed signal-bar Supertrend-line stop; 1.5R/2R/3R target; optional completed-1H EMA50 filter; both/long-only/short-only; all-hours or four fixed UTC buckets; max 8h/32 bars; 1,080 configurations.
- Funnel: 82 configurations passed the training screen; top 25 shortlisted; **0 passed validation**. OOS correctly not evaluated.
- Best training row: EMA50 source, ATR10×2.5, 3R, completed-1H EMA50 filter, short-only, 13:00–19:00 UTC: 90 trades, 51.11% profitable, PF 1.405, +11.70R, avg +0.130R/trade, max DD -6.40R, losing streak 4, 58.8% positive active months (6 TP /15 SL /69 TIME). Its matching validation: 15 trades, 26.67% profitable, PF 0.107, -8.20R, DD -8.20R, losing streak 3, 0% positive active months (0 TP /4 SL /11 TIME).
- Best validation-only row: HL2, ATR10×2.5, 2R, no 1H filter, long-only, 13:00–19:00 UTC: 48 trades, 50.00% profitable, PF 1.608, +9.69R, DD -5.56R, losing streak 6, 75% positive months. Matching training was 252 trades, PF 0.706, -41.49R, DD -43.65R, losing streak 11, 22.2% positive active months. Clear regime/selection inconsistency; reject.
- Execution/costs: 12bp assumed round-trip; actual fee tier unverified; no funding or separate spread/slippage; SL first on same-bar ambiguity; adverse gap-through stop fill; no favourable target gap improvement; UTC buckets fixed and not DST-adjusted. Many trades timed out (69/90 in best train), so time-exit mark-to-close is a material component.
- Code/workflow: `research/supertrend_intraday_backtest.py`, `.github/workflows/supertrend-intraday-backtest.yml`; branch `ai-quant-rebuild`; corrected session assignment commit `707f6d233a7b1b400715af830012c124423afec4`. Experimental only; do not promote.

## Next BTC intraday family — Bollinger/Keltner squeeze breakout (new experiment)

- Hypothesis: a confirmed BB(20, 2σ) compression inside a Keltner channel (EMA20 ± 1.5/2.0 × Wilder ATR14), followed by a 15m close through the prior Donchian 20/40-bar extreme, may capture intraday volatility expansion.
- Causal signal: require at least 4 consecutive completed 15m squeeze bars. The squeeze run must have ended 1–8 bars before the breakout signal. First qualifying close beyond the prior Donchian high/low is used; channel extrema are shifted one bar; enter at next 15m open; consume each squeeze release after one signal.
- Matrix: KC multiplier 1.5/2.0 × Donchian length 20/40 × stop (signal-candle extreme +0.1 ATR14 / 1.5 ATR14) × target 1.5R/2R/3R × no filter/completed-1H EMA50 aligned × both/long-only/short-only × all hours/07:00–13:00/13:00–19:00 UTC = 432 configurations.
- Intraday/execution: 15m signals and entries; max 8h/32 bars; one position at a time/config; stop-first same-bar ambiguity; adverse gap-through stop fill; fixed target fill without favourable gap improvement; reject >5% stops; skip data gaps and trades that cannot complete the 8h horizon within sample.
- Selection: chronological 70/15/15; train >=40 trades, positive net R, PF>=1.05, DD >=-25R; shortlist top 25 by train net-R/drawdown quality; validation >=20 trades, positive net R, PF>=1.05, DD >=-15R, >=50% positive active months; OOS evaluated once only if a candidate passes.
- Costs/limitations: 12bp assumed round trip, not actual fee-tier verified; no funding or separate spread/slippage model; fixed UTC buckets are not exchange session definitions; OHLC ambiguity resolved SL-first. Delta exchange OHLCV is used for price and ATR; volume is not used in this setup.
- Code: `research/squeeze_breakout_intraday_backtest.py` (initial commit `646e793b3ec14e262b14e0af16b82f3bec73ca2f`; correction commit `6c8b48b827b421510d5cd1951b405f657385faf3`, which invalidates an older squeeze when a newer sub-threshold squeeze run completes); workflow `.github/workflows/squeeze-breakout-intraday-backtest.yml` (commit `540fabce0a9f1db054c9a143491586c96470e7bc`); branch `ai-quant-rebuild`. Research workflow [42832756746](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42832756746) compiled successfully and is executing the 432-configuration matrix; inspect completion and artifacts before reporting performance. Deterministic CI [42832756063](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42832756063) is still running at this ledger update.
- Keep experimental only; no production/live rule changes, orders, execution alerts or `main` branch changes.


### Intraday BTCUSD Bollinger/Keltner squeeze breakout — completed, rejected (2026-11-10)

- Workflow [42832756746](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42832756746) completed successfully; artifact ID 13772490798 was downloaded and inspected. Script compilation and all 432 configurations succeeded.
- Dataset: Delta BTCUSD 15m, 70,079 rows, zero gaps; 2024-11-10 14:30 UTC to 2026-11-10 14:00 UTC; 17,519 complete 1H bars. CSV SHA-256 `a9fca1d134e7552c50492b12567578c180908571dfbfca68de595e3fe565fdbb`. Train ends 2026-04-05 14:15 UTC; validation ends 2026-07-24 02:15 UTC; OOS begins 2026-07-24 02:15 UTC.
- Rules: BB(20, 2σ) must be inside Keltner EMA20 ± 1.5/2.0 × Wilder ATR14 for at least 4 consecutive completed bars; the latest qualifying squeeze run must have ended 1–8 bars before a signal. Signal is the first 15m close beyond the prior shifted 20/40-bar Donchian high/low; enter next 15m open; one signal per squeeze release. Stops: signal-candle extreme +0.1 ATR or 1.5 ATR; targets 1.5R/2R/3R; optional completed-1H EMA50; both/long-only/short-only; all hours, 07–13 or 13–19 UTC; max 8h.
- Funnel: 2/432 configurations passed training; both shortlisted; **0 passed validation**, so OOS was not evaluated.
- Best training row by raw net R was below the pre-registered 40-trade minimum: KC1.5, Donchian20, 1.5 ATR stop, 3R, 1H EMA50, short-only, 07–13 UTC: 37 trades, 40.54% profitable, PF 1.334, +9.73R, DD -18.62R, losing streak 9 (15 TP /21 SL /1 TIME). It is descriptive only and not train-eligible.
- Best train-eligible row by train net-R/drawdown quality: KC1.5, Donchian40, signal-extreme stop, 3R, 1H EMA50, short-only, 13–19 UTC: 49 trades, 36.73% profitable, PF 1.090, +3.46R, DD -16.68R, losing streak 6, only 37.5% positive active months (14 TP /27 SL /8 TIME). Matching validation: 10 trades, 40% profitable, PF 1.546, +3.76R, DD -4.38R, losing streak 4, 33.3% positive months. It fails the minimum 20 validation trades and monthly-stability gate.
- Best validation-only row: KC2.0, Donchian20, 1.5 ATR stop, 1.5R, 1H EMA50, short-only, 13–19 UTC: 21 trades, 61.90% profitable, PF 1.540, +5.40R, DD -3.93R, losing streak 3, 50% positive active months. Matching training: 93 trades, PF 0.842, -10.19R, DD -22.07R, losing streak 5, 35.3% positive active months. Reject as train/validation inconsistency.
- Execution/costs: 12bp assumed round-trip; actual fee tier unverified; no funding or separate spread/slippage model; same-bar SL-first, adverse gap-through stop fills; fixed target fills; one position/config; no trades crossing data gaps or sample boundaries. Fixed UTC buckets are not exchange-session definitions. The squeeze release is a mechanical BB/Keltner proxy, not a discretionary volatility-compression read.
- Code: `research/squeeze_breakout_intraday_backtest.py`; initial commit `646e793b3ec14e262b14e0af16b82f3bec73ca2f`, corrected squeeze-run invalidation commit `6c8b48b827b421510d5cd1951b405f657385faf3`; workflow `.github/workflows/squeeze-breakout-intraday-backtest.yml` commit `540fabce0a9f1db054c9a143491586c96470e7bc`. Experimental only; do not promote.


## Next BTC intraday family — 5m EMA pullback continuation (queued)

- Motivation: prior EMA pullback research used 15m execution. This study changes execution granularity to 5m, uses a hard 2h holding cap, and retains completed-1H context to test whether a faster pullback entry has distinct behaviour. It is not a retest of the prior 15m result.
- Data: Delta BTCUSD 5m candles fetched for up to 730 days using the public history endpoint in 1,800-candle chunks; discard current incomplete candle, duplicates and malformed OHLC; verify 5m timestamp alignment, continuity and full 12-candle 1H bars. If the endpoint returns materially less than 50,000 5m bars, fail rather than silently shorten the sample.
- Signals: completed 5m candle touches and closes back across EMA20 or EMA50; compare basic EMA reclaim with reclaim plus close beyond prior candle high/low. Enter next 5m open. Optional trend filter uses EMA50 from fully completed 1H bars aggregated from 12 contiguous 5m candles.
- Matrix: EMA20/50 × EMA reclaim/prior-bar break × signal-extreme +0.1 ATR14 or 1.5 ATR14 stop × 1.5R/2R/3R target × no filter/completed-1H EMA50 alignment × both/long-only/short-only × all hours/07:00–13:00/13:00–19:00 UTC = 432 configurations.
- Intraday/execution: one position at a time/config; maximum hold 2h/24 5m bars; force time exit; signal after candle close, next-open entry; same-bar SL first; adverse gap-through stop fill; fixed target fill; skip >5% stop distances, data gaps and trades that cannot complete the holding horizon within the sample.
- Selection: chronological 70/15/15; train >=80 trades, positive net R, PF>=1.05, DD >=-35R; shortlist top 25 by train net-R/drawdown quality; validation >=30 trades, positive net R, PF>=1.05, DD >=-20R, >=50% positive active months; OOS once only for a single validation-selected candidate.
- Costs/limitations: 12bp assumed round trip, actual fee tier unverified; no funding or separate spread/slippage model; fixed UTC buckets are not exchange session definitions; OHLC same-bar ambiguity resolves stop first. This cost assumption is deliberately conservative but may not match actual taker/maker execution.
- Code: `research/ema_pullback_5m_intraday_backtest.py` (initial commit `899a6b11beea5dfb02c97f72102f48eafa9d8054`; timestamp-alignment integrity check commit `56dcc8aa021b4dd5169143cdd3c721099bb56463`); workflow `.github/workflows/ema-pullback-5m-intraday-backtest.yml` commit `4a1f0e91af2fb29fdde5a065da527f643605283f`; branch `ai-quant-rebuild`. Initial research workflow [42833406569](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42833406569) compiled but failed before backtesting because the integrity check incorrectly assumed timestamps must align to Unix UTC 5m boundaries; the returned Delta series has a fixed exchange-origin offset. No performance result was produced. Corrected code commit `c602bca849db30c4fc7b74a24ae13e349bcf22ef` now checks regular 5m cadence relative to the first returned candle. Corrected workflow [42833704498](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42833704498) failed before backtesting: its relative-to-first-timestamp cadence check flagged 210,029 timestamps after a phase discontinuity. Compilation passed, but no data-quality artifact or performance result was produced.
- This follows the completed squeeze breakout rejection: 432 configurations, only 2 training-qualified, 0 validation-qualified; OOS was not evaluated. Keep all work experimental; no live/production changes, orders, alerts or `main` branch changes.


## 5m EMA pullback pipeline repair — 2026-11-10 follow-up

- Audit of workflow [42833704498](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42833704498) showed the run failed at the timestamp-integrity gate after Python compilation; it did not execute the strategy matrix and produced no artifacts. The check compared every timestamp with the first timestamp. A single phase discontinuity can make all later timestamps appear off-cadence, so the prior failure count (210,029) did not prove that every interval was malformed.
- Code update commit: `2158672b507fa0900f679e59bb8445ed3a7b5e60` on `ai-quant-rebuild`, file `research/ema_pullback_5m_intraday_backtest.py`.
- Revised integrity logic validates adjacent timestamp intervals. It permits only a small number of non-5m-multiple intervals (maximum of 5 or 0.1% of rows, whichever is larger); such irregular intervals remain marked as gaps and the simulator skips any trade window crossing them. Larger irregularity fails closed.
- Replaced 1H EMA context synthesized by UTC resampling of 5m candles with native Delta BTCUSD 1h candles. EMA50 is reset after any missing-hour discontinuity and becomes available to a 5m signal only at the completed hourly candle's close. Both 5m and 1h datasets are now persisted with SHA-256 hashes for audit.
- This is a data-pipeline correction only, not a strategy result. The 432-configuration matrix remains untested until the new GitHub Actions run completes and its data-quality files, monthly files and trade outputs are inspected. The 12bp round-trip cost assumption remains unverified; funding and separate spread/slippage are not modelled.


- Corrected follow-up workflow [42842886745](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42842886745) was triggered by code commit `2158672b507fa0900f679e59bb8445ed3a7b5e60`. At the latest status check, Python compilation had passed and the 5m EMA matrix step was still running; no performance result was yet available.

## BTCUSD 5m EMA pullback continuation — completed, rejected (2026-11-10)

- Corrected workflow [42842886745](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42842886745) completed successfully; artifact ID 13776198763 was uploaded and inspected through workflow logs. The earlier two failed attempts produced no strategy results and are retained above as pipeline history.
- Dataset: Delta BTCUSD 5m, 210,239 rows, zero 5m gaps, zero off-grid intervals; 2024-11-10 15:20 UTC to 2026-11-10 15:10 UTC; 17,519 native 1H bars, zero hourly gaps. 5m SHA-256 `ba871949a45b8e1a9e71fb5af33156eca846154405f5eeca3e1f9c626145f374`; 1h SHA-256 `5705fb33b342855d504ef2b09d4eff10a3ad5c42ae361040d67ae681d925c335`. Chronological split: train through 2026-04-05 15:15 UTC; validation through 2026-07-24 03:15 UTC; OOS begins 2026-07-24 03:15 UTC.
- Matrix: 432 configurations; EMA20/50 touch-and-reclaim; basic reclaim versus close beyond prior candle extreme; signal-extreme +0.1 ATR or 1.5 ATR stop; 1.5R/2R/3R target; no filter or completed native 1H EMA50 alignment; both/long-only/short-only; all hours/07–13/13–19 UTC; next-5m-open entry; 2h maximum hold.
- Result: **0 training-eligible, 0 shortlisted, 0 validation passes**. OOS was not evaluated. The best training row was still deeply negative: EMA50 prior-bar-break, 1.5 ATR stop, 2R, 1H EMA50 filter, long-only, 13–19 UTC: 558 trades, 38.17% profitable, PF 0.535, -230.93R, max DD -233.76R, losing streak 12, positive in only 11.1% of active months. Best validation-only row was EMA50 prior-bar-break, 1.5 ATR, 2R, 1H EMA50, short-only, 13–19 UTC: 97 trades, 40.21% profitable, PF 0.617, -30.69R, DD -32.27R, losing streak 5, positive in 25% of active months. Its matching training row was 567 trades, PF 0.491, -276.30R, DD -276.30R, losing streak 9. This is not a viable candidate.
- Execution/costs: 12bp assumed round trip; actual fee tier unverified; no funding or separate spread/slippage; same-bar SL-first and adverse gap-through stop fill; one position/config; trades crossing gaps or sample boundaries skipped. The 12bp cost is particularly material for tight 5m stops and requires fee-tier/slippage sensitivity before any future strategy can be considered.
- Code: `research/ema_pullback_5m_intraday_backtest.py`, corrected data-integrity/native-hourly-context commit `c602bca849db30c4fc7b74a24ae13e349bcf22ef`; workflow `.github/workflows/ema-pullback-5m-intraday-backtest.yml`; branch `ai-quant-rebuild`. No live/production rules, orders, alerts or `main` changes.

## Next BTC intraday family — 5m RSI extreme-reclaim mean reversion (queued 2026-11-11)

- Hypothesis: a completed 5m RSI cross back out of an oversold/overbought extreme may capture short-horizon mean reversion; test whether simple crossback plus a direction-confirming candle and/or completed-1H trend context improves expectancy after realistic costs.
- Data: same Delta BTCUSD 5m and native 1h endpoints, up to 730 days; discard incomplete bars; validate adjacent 5m cadence and hourly gaps; persist SHA-256 hashes. Use a fresh chronological 70/15/15 split and no OOS access unless one candidate passes the pre-registered train and validation funnel.
- Signals: Wilder RSI lengths 2/5/14; threshold pairs 10/90 and 20/80. Long signal only when prior completed 5m RSI is at/below oversold threshold and current completed RSI crosses above it; short signal when prior RSI is at/above overbought threshold and current completed RSI crosses below. Compare crossback alone versus crossback plus a same-direction signal candle. Enter next 5m open.
- Matrix: 3 RSI lengths × 2 threshold pairs × 2 confirmations × 2 stops (signal extreme ±0.1 ATR14 or 1.5 ATR14) × 3 targets (1.5R/2R/3R) × 2 filters (none/completed native 1h EMA50 alignment) × 3 directions (both/long-only/short-only) × 2 session modes (all hours/07–19 UTC) = 864 configurations. One position at a time/configuration; 2h max holding period.
- Selection: chronological 70/15/15; training >=80 trades, net R >0, PF >=1.05, DD >=-35R; shortlist top 25 by net-R/drawdown quality; validation >=30 trades, net R >0, PF >=1.05, DD >=-20R and >=50% positive active months; evaluate OOS once only for a single validation-selected candidate. Record monthly summaries, win rate, PF, net R, DD and losing streak.
- Execution/costs: next-open entry; same-candle SL-first; adverse gap-through stop fill; fixed target fill; 2h time exit; skip gaps and sample-boundary-crossing trades; reject >5% stop distances. Retain 12bp assumed round-trip cost for comparability, but clearly flag that actual fee tier, funding and separate spread/slippage are not modelled. Tight 5m stop sensitivity to costs is a specific limitation.
- Experimental only; do not change production/live rules, send execution alerts, place orders or modify `main`.


- RSI implementation commit: `583b4cb0fff244f2211a9289763ac8bd818abd38`; workflow definition commit: `03d63c59084c0a0e29d0d6f4cb22c89a1f15bd23`; workflow-trigger commit: `704c30e61cfdee05e1c279ac5bcbd2cd85bd124f`.
- RSI workflow [42882926862](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42882926862) has started on `ai-quant-rebuild`. At this ledger update, dependencies were still installing; compilation and backtest had not yet run. No RSI performance result is available at this point.


## BTCUSD 5m RSI extreme-reclaim mean reversion — completed, rejected (2026-11-10)

- Workflow [42882926862](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42882926862) completed successfully; artifact ID 13794143490 was downloaded and inspected. Python compilation and the full 864-configuration matrix completed.
- Dataset: Delta BTCUSD 5m, 210,239 rows, zero 5m gaps and zero off-grid intervals; 2024-11-10 19:15 UTC to 2026-11-10 19:05 UTC; 17,519 native 1h bars, zero hourly gaps. SHA-256 5m c1ae887fabc6664631e450082357cd9e786ac699f88439cfd2495ed7cc18e3c2; 1h 1d95e88c4354a0372ab1f5e2c4f8c032db0a00e1eddb90d0563a2cad2aafe2d6. Chronological split: train ends 2026-04-05 19:10 UTC; validation ends 2026-07-24 07:10 UTC; OOS begins 2026-07-24 07:10 UTC.
- Rules/matrix: Wilder RSI(2/5/14) crossback from 10/90 or 20/80 extremes; compare crossback alone versus same-direction signal candle; next-5m-open entry; signal-extreme +0.1 ATR or 1.5 ATR stop; 1.5R/2R/3R target; optional completed native 1h EMA50 alignment; both/long-only/short-only; all hours or 07:00–19:00 UTC; 2h maximum hold; 864 configurations.
- Funnel: 0/864 training-eligible, 0 shortlisted, 0 validation passes. OOS was not evaluated.
- Best training configuration with at least 80 trades: RSI14, 20/80, crossback, 1.5 ATR stop, 1.5R target, no 1h filter, long-only, 07:00–19:00 UTC: 144 trades, 44.44% profitable, PF 0.603, -41.13R, average -0.286R, max DD -42.31R, losing streak 8, positive in 23.5% of active months.
- Best validation-only row was small-sample: RSI14, 20/80, crossback, 1.5 ATR stop, 3R target, completed 1h EMA50 filter, long-only: 7 trades, 85.71% profitable, PF 5.857, +7.30R, DD -1.50R, losing streak 1. Matching training: 29 trades, PF 0.455, -14.22R, DD -18.07R, losing streak 8, positive in 35.7% of active months. Not eligible and inconsistent.
- A diagnostic audit of the artifact showed the 5m RSI2/20-80 both-direction signal generated 20,831 train trades but only 29.67% profitable, PF 0.143, -26,835.25R, DD -26,836.24R, losing streak 65 and no positive active months. Tight signal-extreme risk makes the fixed 12bp cost large in R terms; this is a material execution-cost sensitivity, not evidence that the strategy is viable at lower costs.
- Reporting correction: the workflow log's TOP TRAIN table was sorted by net R without excluding zero-trade configurations, so its first displayed rows were zero-trade/zero-R rows rather than the best active configurations. The full train_summary.csv and validation_summary.csv artifacts were inspected directly; the rejection decision is based on the full matrices and the pre-registered eligibility filter, not those misleading first log rows. Future leaderboards must exclude zero-trade rows.
- Execution/costs: 12bp assumed round trip; actual fee tier unverified; no funding or separate spread/slippage; same-candle SL-first; adverse gap-through stop fill; fixed target fill; one position/config; 2h time exit. No production/live changes.
- Code: research/rsi_reversion_5m_intraday_backtest.py; implementation commit 583b4cb0fff244f2211a9289763ac8bd818abd38; workflow-trigger commit 704c30e61cfdee05e1c279ac5bcbd2cd85bd124f; branch ai-quant-rebuild. Experimental only; do not promote.

## Next BTC intraday family — ADX + EMA pullback continuation (queued 2026-11-11)

- Motivation: test a distinct trend-strength-filtered pullback model after the 5m RSI mean-reversion rejection. This is not another Supertrend flip or raw EMA cross; direction is gated by Wilder DMI (+DI/-DI), ADX strength and an optional completed-1h EMA50/EMA200 regime.
- Dataset: Delta BTCUSD 15m candles from the existing crt_backtest.fetch("15m") pipeline, up to 730 days; drop incomplete/malformed bars; compute indicators separately within contiguous 15m segments; only complete 1h aggregates of four 15m bars are used for higher-timeframe context. Persist 15m and 1h CSV SHA-256 hashes and report gaps/off-grid intervals.
- Signal: 15m EMA20 or EMA50 pullback touch/reclaim. Long requires low touching EMA, bullish close back above it, and +DI > -DI; short is symmetric. Compare a simple EMA reclaim against a stronger close beyond the prior candle high/low. Require ADX14 >= 15/20/25; compare no ADX-slope requirement versus ADX rising versus three bars earlier. Optional completed-1h EMA50/EMA200 regime alignment.
- Matrix: EMA20/50 × ADX threshold 15/20/25 × ADX rising false/true × reclaim/prior-bar-break confirmation × signal-extreme +0.1 ATR or 1.5 ATR stop × 1.5R/2R/3R target × no HTF filter/completed-1h EMA50-vs-EMA200 alignment × both/long-only/short-only × all hours/07:00–19:00 UTC = 1,728 configurations.
- Execution: enter next 15m open; one position at a time/config; 8h maximum hold (32 bars); skip data gaps and sample-boundary-crossing trades; same-bar SL first; adverse gap-through stop fill; fixed target fill; skip stop distances >5% of entry; fixed 12bp assumed round-trip cost.
- Selection: chronological 70/15/15; train >=40 trades, positive net R, PF >=1.05, max DD no worse than -25R; shortlist top 25 by net-R/drawdown quality; validation >=20 trades, positive net R, PF >=1.05, DD no worse than -15R, and >=50% positive active months; OOS only once for a single candidate that passes both gates. Exclude zero-trade rows from leaderboards.
- Costs/limitations: 12bp round trip is an assumption, actual Delta fee tier unverified; no funding or separate spread/slippage model; fixed UTC 07–19 bucket is not a DST-aware exchange session; ADX/EMA definitions are mechanical proxies; OHLC same-bar ambiguity resolves SL first.
- Code: research/adx_ema_intraday_backtest.py; initial code commit 3a33e394d8a802d651904e6e3535b233b75e76ff, ADX warm-up/gap-safe correction commit f304f22393ec28171d0edb9221df8440e2ecd8dc; workflow .github/workflows/adx-ema-intraday-backtest.yml, commit 453c70555036a7af177ac69d6cd175f1a6277e96; branch ai-quant-rebuild. The workflow is configured for branch pushes affecting the script/workflow; execution status and performance results have not yet been verified. Experimental only; no live rules, orders, alerts or main changes.



## BTCUSD 15m ADX + EMA pullback continuation — completed, rejected (2026-11-11 audit)

- Workflow [42922753784](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42922753784) completed successfully; artifact ID 13812722678 was downloaded and the complete train/validation summary CSVs were inspected directly.
- Dataset: Delta BTCUSD 15m, 70,079 rows, zero 15m gaps/off-grid intervals; 2024-11-10 23:30 UTC to 2026-11-10 23:00 UTC; 17,519 complete 1h bars, zero hourly gaps. 15m SHA-256 `a461d0157f65bcaac746f4a0da8a13074d5a237237ef8049cead0cb9e266da1d`; 1h SHA-256 `90a9351abb6bd44afa9adf25eb0bc32d70047148bca347b148b19bae53d7df8b`. Train ends 2026-04-05 23:15 UTC; validation ends 2026-07-24 11:15 UTC; OOS begins 2026-07-24 11:15 UTC.
- Matrix: 1,728 configurations across EMA20/50, ADX14 thresholds 15/20/25, rising/not rising, EMA reclaim/prior-candle break, signal-extreme/1.5 ATR stops, 1.5R/2R/3R targets, optional completed-1h EMA50/200 alignment, both/long-only/short-only and all-hours/07–19 UTC. Next-15m-open entry; 8h max hold; 12bp assumed round-trip cost.
- Full CSV audit: 14 configurations met the training screen and were shortlisted; **0 passed validation**, so OOS was not evaluated. Important reporting correction: the workflow's first displayed TOP NONZERO TRAIN rows were not the train-eligible leaderboard; one displayed row had only 34 trades, below the 40-trade minimum. Use the full summary CSV and explicit eligibility filters.
- Best training-qualified row: EMA50, ADX14 >=20 and rising, prior-candle-break confirmation, 1.5 ATR stop, 3R target, no HTF filter, short-only, all hours: 73 trades, 39.73% profitable, PF 1.153, +8.17R, avg +0.112R, max DD -14.56R, losing streak 5, 50.0% positive active months (21 TP /40 SL /12 TIME). Matching validation: 13 trades, 7.69% profitable, PF 0.011, -15.36R, DD -15.36R, losing streak 8, 0% positive active months (0 TP /12 SL /1 TIME).
- Best validation-only row with at least 20 trades: EMA20, ADX14 >=15 and rising, EMA reclaim, 1.5 ATR stop, 2R target, no HTF filter, long-only, 07–19 UTC: 23 trades, 60.87% profitable, PF 1.622, +8.03R, DD -4.48R, losing streak 3, 75% positive active months. Its matching training result: 165 trades, 33.94% profitable, PF 0.612, -55.85R, DD -57.65R, losing streak 8, 16.7% positive active months. Clear chronological inconsistency; reject.
- Execution/cost limitations: 12bp round trip is assumed, not actual fee-tier verified; no funding or separate spread/slippage; 07–19 UTC is a fixed proxy; same-bar stop-first and adverse gap-through stop fill. The 15m and native 1h series had no gaps in this sample. No OOS result exists for this experiment.

## Next BTCUSD intraday family — Donchian breakout with ATR chandelier trailing stop (new experiment; run started 2026-11-11)

- Hypothesis: the prior simple Donchian breakout used fixed stops and a multi-day holding horizon; a separate strictly intraday variant with a causal ATR chandelier trailing stop may retain directional expansion while reducing giveback. This is a new exit model, not a re-labeling of the earlier Donchian baseline.
- Data: Delta BTCUSD 15m from the existing `crt_backtest.fetch("15m")` endpoint; discard incomplete/malformed bars; deduplicate timestamps; split any non-15m interval into a new segment; do not fill gaps. Build ATR(14) and prior 20/55-bar channel highs/lows within each contiguous segment. Build only complete hourly candles containing four contiguous 15m bars from one segment; expose right-edge hourly EMA50/EMA200 only after close.
- Signal/entry: first qualifying completed 15m close beyond the prior shifted Donchian 20/55 high/low; enter at next 15m open. Direction modes both/long-only/short-only. Optional completed-1h EMA50/EMA200 alignment. Session comparison all hours versus 07–19 UTC, assigned by actual next-bar entry time.
- Matrix: 2 Donchian lengths × 2 initial ATR stops (1.5/2.0) × 2 chandelier multipliers (2.0/3.0 ATR) × 4 target modes (trail-only/2R/3R/4R) × 2 HTF filters × 3 direction modes × 2 sessions = 384 configurations.
- Trailing-stop causality: on each completed post-entry 15m candle, update the high/low water mark and calculate the candidate chandelier stop using that candle's completed ATR; ratchet only in the favourable direction; the updated stop becomes active on the next candle. On each candle, test the already-active stop before target (SL-first for ambiguous OHLC); adverse gap-through stop fills at the worse opening price. Fixed targets fill at target without favourable gap improvement. Maximum hold 32 bars/8h. Skip gap-crossing and sample-boundary trades; reject initial stops >5% of entry; one position at a time/config.
- Costs/splits: primary 12bp assumed round-trip cost, plus 6bp and 20bp sensitivity on the same gross trades; no funding or separate spread/slippage model. Chronological 70/15/15 split. Training gate >=40 trades, positive net R, PF>=1.05, DD no worse than -25R; top 25 by net-R/(abs(DD)+1); validation gate >=20 trades, positive net R, PF>=1.05, DD no worse than -15R, >=50% positive active months; evaluate OOS once only for one selected validation-passing candidate. Monthly and completed-1h bull/bear/mixed regime diagnostics are exported.
- Code: `research/donchian_atr_trailing_intraday_backtest.py`, commit `503763375babdc7c4ddfb900bd129c1e1abdb800`; workflow `.github/workflows/donchian-atr-trailing-intraday.yml`, commit `9c103e9cf24d8a6971acd0b4a658ab66c7c6d7b3`; branch `ai-quant-rebuild`. Research workflow [42951481514](https://github.com/undaviyabrijnesh-sys/SMC-crypto-alerts/actions/runs/42951481514) is executing. Python compilation passed; matrix execution status must be checked before reporting performance. Experimental only; no production/live changes, orders, execution alerts or `main` changes.


## BTCUSD 15m Donchian breakout + ATR chandelier — completed and rejected (2026-11-11)

- Workflow [42951481514](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42951481514) completed successfully; artifact [13824789423](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42951481514/artifacts/13824789423) was downloaded and inspected, including train/validation, monthly and regime CSVs.
- Dataset: Delta BTCUSD 15m, 70,079 candles, zero 15m gaps; 2024-11-11 03:30 UTC to 2026-11-11 03:00 UTC. SHA-256 `6d3d820ceffbbfb9f02759cf61afe541773fa063e09eb5d74d94d09dce195137`. Train boundary 2026-04-06 03:00 UTC; validation boundary 2026-07-24 15:00 UTC; OOS begins 2026-07-24 15:15 UTC.
- Matrix: 384 configurations; 20/55 Donchian channel, initial 1.5/2 ATR stop, 2/3 ATR chandelier, trail-only/2R/3R/4R, optional completed 1h EMA50/200 alignment, both/long-only/short-only, all-hours/07–19 UTC. 8h max hold; next-open entry; chandelier updated only after completed bars and active from the next bar.
- Primary 12bp results: **0 train-eligible, 0 shortlisted, 0 validation passes**. OOS correctly not evaluated. Best training row still lost: 262 trades, 34.73% profitable, PF 0.821, -29.86R, avg -0.114R, max DD -49.72R, losing streak 12, 33.3% positive months. This row was DC20, initial 2 ATR, trail 3 ATR, 3R cap, 1h EMA50/200, short-only, 07–19 UTC.
- Best validation-only row: DC55, initial 1.5 ATR, trail 3 ATR, 4R cap, 1h EMA50/200, short-only, all-hours: 56 trades, 28.57% profitable, PF 1.057, +2.53R, avg +0.045R, max DD -9.72R, losing streak 5. It was positive in only 2/4 active months (Apr +0.35R, May -6.28R, Jun +9.68R, Jul -1.22R) and all trades were classified in the bear regime. Matching training did not qualify; reject.
- Cost sensitivity: best training row was -1.72R at 6bp, -29.86R at 12bp and -67.38R at 20bp. Best validation-only row was +9.95R at 6bp, +2.53R at 12bp and -7.36R at 20bp. The apparent validation edge is fragile to costs and chronologically inconsistent.
- Assumptions/limitations: round-trip costs 6/12/20bp, actual Delta fee tier unverified; no funding or separate spread/slippage; fixed 07–19 UTC session proxy; OHLC same-bar ambiguity stop-first and adverse gap-through stop fills. No OOS metrics exist.
- Decision: reject the Donchian + chandelier intraday model; do not promote it or alter production.

## Next BTCUSD 15m family — failed Donchian breakout reversal (new; workflow committed 2026-11-11)

- Hypothesis: some channel breakouts fail and reverse. Test whether a close outside the prior shifted 20/55-bar Donchian channel followed by a close back inside the frozen breakout boundary produces a more selective reversal than trend-following breakouts.
- Causal signal: breakout close outside prior channel; within 1 or 3 subsequent 15m candles, price closes back inside that same frozen boundary. Confirmation is either close-inside alone or close-inside plus opposite candle body. Enter opposite the breakout at the next 15m open.
- Stop: beyond the full breakout-to-reclaim excursion plus 0 or 0.1 ATR(14) buffer. Fixed 1.5R/2R/3R/4R targets; 32-bar/8h max hold; one open trade per configuration; stop-first same-candle ambiguity and adverse gap-through fills. Reject risk wider than 5% of entry.
- Filters/matrix: channel 20/55; failure window 1/3; confirmation close-inside/opposite-body; stop buffer 0/0.1 ATR; target 1.5/2/3/4R; optional completed 1h EMA50/200 alignment; both/long-only/short-only; all-hours/07–19 UTC = 768 configurations.
- Data: Delta BTCUSD 15m via existing `research/crt_backtest.py` fetcher; malformed bars removed, duplicate timestamps removed, gaps segmented and not filled; complete 1h bars only for EMA context. Dataset hash/date coverage will be recorded by the workflow.
- Costs/splits: assumed 6/12/20bp round trip, no funding or separate spread/slippage; chronological 70/15/15. Train gate >=40 trades, positive net R, PF>=1.05, DD no worse than -25R; top 25 by net-R/(abs(DD)+1); validation gate >=20 trades, positive net R, PF>=1.05, DD no worse than -15R and >=50% positive active months. **OOS is not part of the matrix; it is evaluated once for one candidate only after both gates pass.**
- Code: `research/failed_breakout_reversal_intraday_backtest.py`, latest code commit `7e02b2492a19e77ddb59504c617e0e2b83a1d85c`; workflow `.github/workflows/failed-breakout-reversal.yml`, commit `8abed2da2bad5e35f2220fa86760ca89033f27bd`; branch `ai-quant-rebuild`. The workflow has been added and the push should trigger it; compile and execution status have not yet been verified through the available run/job endpoint. Experimental only; no production/live changes, orders, execution alerts or `main` changes.

- Verification update: repository CI run [42979265599](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42979265599) completed successfully. Its PR merge checkout contains this exact script blob (`dd1119025e2bee71a756cd4d02747568de6f82ee`) and executed `python -m compileall -q .`; 27 repository unit tests also passed. This verifies Python syntax in the committed script, not the dedicated 768-configuration matrix. The custom research workflow's run ID/results have not yet been confirmed, so no strategy performance claim is made.

- Follow-up code hygiene: the train leaderboard was changed to exclude zero-trade configurations from its displayed ranking (eligibility gates already excluded them); latest script commit is `6e345edfaf01649dfeba0b4978de9d716520b77f` (blob `c2dfa93194034bf06c39319a63b99d864a232827`). The earlier CI compile check covered the prior script blob; this small display-only edit has not yet been independently recompiled. No backtest result is available for this new family yet.


## BTCUSD 15m failed Donchian-breakout reversal — completed and rejected (2026-11-11)

- Dedicated workflow [42979803435](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42979803435) completed successfully; all seven research steps passed and artifact [13836219793](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42979803435/artifacts/13836219793) was uploaded.
- Dataset: Delta BTCUSD 15m, 70,079 rows, zero missing 15m intervals; 2024-11-11 07:30 UTC to 2026-11-11 07:00 UTC. SHA-256 `e00134b927f215e80e415909e4c9016e95a686cf631ae0a45b731b16a5b3b25d`. Train boundary 2026-04-06 07:00 UTC; validation boundary 2026-07-24 19:00 UTC; reserved OOS begins 2026-07-24 19:15 UTC.
- Matrix: 768 configurations. 15m close outside prior shifted Donchian 20/55 channel; first close back inside frozen boundary within 1/3 bars; confirmation close-inside or opposite candle body; next 15m open entry in reversal direction; stop beyond full breakout excursion plus 0/0.1 ATR; 1.5/2/3/4R fixed targets; optional completed 1h EMA50/200 alignment; both/long-only/short-only; all-hours/07–19 UTC; 8h maximum hold.
- Primary 12bp results: **0 train-eligible, 0 shortlisted, 0 validation passes**. OOS correctly not evaluated. Best training row in the displayed nonzero-trade leaderboard was still negative: 27 trades, 44.44% profitable, PF 0.548, -10.47R, average -0.388R, max DD -12.90R, losing streak 4, 33.3% positive months. This was DC55, 1-bar failure window, 1.5R, 1h EMA50/200, long-only, 07–19 UTC.
- Best validation-only row: 12 trades, 41.67% profitable, PF 2.367, +7.52R, average +0.627R, max DD -2.48R, losing streak 3, 66.7% positive active months. It used DC55, 3-bar failure window, opposite-body confirmation, 0.1 ATR stop buffer, 4R target, 1h EMA50/200, both directions, 07–19 UTC. It did not meet the 20-trade validation minimum, and no training candidate qualified. This small validation result is not evidence of an edge.
- Cost sensitivity was run at 6/12/20bp round trip. No funding or separate spread/slippage; actual Delta fee tier remains unverified. Stop-first same-candle ambiguity and adverse gap-through stop fills; UTC session proxy is fixed and ignores DST.
- Decision: reject this mechanical failed-breakout reversal model under the tested definitions and assumptions; do not promote or evaluate OOS.

## Next BTCUSD 15m family — confirmed 1H liquidity sweep + 15m market-structure shift (new; workflow committed 2026-11-11)

- Hypothesis: a wick through a confirmed 1H swing high/low followed by a close back across the level, then a later 15m close through the last pre-sweep confirmed opposite 15m swing, may identify a more selective reversal than simple channel failure.
- Causal definitions: 1H external pivot high/low uses 2 or 3 bars on each side and becomes usable only after the right-side confirmation hour closes. A 15m sweep requires wick-through and close-back-across the frozen level. The local MSS reference is the last 15m swing pivot confirmed before the sweep; the MSS must close through it within 4 or 8 subsequent 15m bars. Enter at the next 15m open. A failed reclaim during the MSS wait cancels the setup. External levels expire after 72 hours.
- Risk/exit: stop beyond the full sweep-to-MSS excursion plus 0 or 0.1 ATR(14) buffer; fixed 1.5R/2R/3R/4R targets; 32-bar/8h max hold; one position at a time per configuration; skip risk >5% of entry; stop-first OHLC ambiguity and adverse gap-through stop fills.
- Filters/matrix: external pivot strength 2/3 × local pivot strength 2/3 × MSS wait 4/8 × stop buffer 0/0.1 ATR × target 1.5/2/3/4R × optional completed 4H EMA50/200 trend alignment × both/long-only/short-only × all-hours/07–19 UTC = 768 configurations. Completed 4H bars are built only from 16 contiguous 15m bars; EMA values are exposed only after the 4H close.
- Data: Delta BTCUSD 15m via `research/crt_backtest.py` fetcher; malformed bars removed, duplicates removed, gaps segmented and not filled. 1H external pivots and 4H regime are built from completed contiguous bars. Dataset hash, date coverage, event counts and split boundaries will be written to `methodology.json` by the workflow.
- Costs/splits: assumed 6/12/20bp round trip, no funding or separate spread/slippage; chronological 70/15/15. Training gate >=40 trades, positive net R, PF>=1.05, DD no worse than -25R; top 25 by net-R/(abs(DD)+1); validation gate >=20 trades, positive net R, PF>=1.05, DD no worse than -15R and >=50% positive active months. OOS is evaluated once for one candidate only if both gates pass.
- Code: `research/liquidity_sweep_mss_intraday_backtest.py`, commit `5d275e6a85b5a184c4e622917ba5be4ada325bfd`; workflow `.github/workflows/liquidity-sweep-mss-intraday.yml`, commit `661ba2fabbd8452203dd11eb48d7f3c0d6a8b886`; branch `ai-quant-rebuild`. Dedicated workflow status/results must be confirmed before reporting any performance. Experimental only; no production/live changes, orders, execution alerts or `main` changes.
