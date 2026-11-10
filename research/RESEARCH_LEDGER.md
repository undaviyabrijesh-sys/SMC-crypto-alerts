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
