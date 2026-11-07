# Supervisor handoff — EXP-003 strategy discovery

**Updated:** 2026-11-07  
**Working branch:** `ai-quant-rebuild`  
**Pull request:** #1, still draft/open/unmerged; target `main`.  
**Latest implementation commit:** `fdb00a8720e9afdb7ff917d27cf31b95a5413156`  
**Scope:** independent Quant Discovery research only. Production alerts, visual analyst, paper position logic and approval allowlist were not changed.

## What was implemented

The user supplied the NYU Stern / Glucksman 2025 study of Follow-the-Winner, Follow-the-Loser, Pattern Matching and Meta-Learning, plus Quantified Strategies as a catalogue of possible strategy hypotheses.

Added EXP-003 as a prequential research selector:
- Follow-the-Winner (shrunk EWMA of completed net-R outcomes).
- Follow-the-Loser (mirrored historical performance, a contrarian control).
- Pattern Matching (exact asset / timeframe / trend / volatility context).
- A fixed-weight Meta-Ensemble of winner, pattern and online-Hedge-style components.
- One existing shadow candidate at most per asset and policy, no created setups, no blending of incompatible directions.
- Three prior expert observations or three exact-context matches required before a selector can act; no non-positive prior signal is selected.
- Research output tables include summary, five chronological prequential slices, selected trades and decisions, plus input hash manifest.

EXP-003 reads only EXP-002's final OOS shadow-trade CSV. The EXP-002 candle timestamps denote candle opens; a result is not visible to the selector until the exit candle closes (exit timestamp plus timeframe duration). The test suite covers this no-look-ahead boundary, cost conversion, duplicate/risk validation, non-overlap, simultaneous exit-event loss streaks and output creation.

The specification is in `quant_discovery/EXP003_ONLINE_META_SELECTOR_SPEC.md`. Code/tests are `quant_discovery/strategy_discovery.py` and `quant_discovery/test_strategy_discovery.py`.

## Workflow and verification evidence

The existing one-time historical OHLCV workflow was extended to run EXP-003 after EXP-001 and EXP-002, and to include EXP-003 in the run summary and research artifact. The implementation commit intentionally starts a new one-time archive run on this research branch.

GitHub Actions evidence:
- Push CI run [42341048498](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42341048498) — passed on the EXP-003 implementation head.
- PR CI run [42341052077](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42341052077) — passed on the same head.
- Historical archive run [42341048484](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/42341048484) — was still downloading the three-year BTC/ETH/XAUT OHLCV archive at the latest inspection. Dataset verification, EXP-001, EXP-002 and EXP-003 had not yet started at that inspection. Do not assume it completed or that it generated research metrics; re-check the run and its jobs/artifacts first.
- The preceding archive run [42340120427](https://github.com/undaviyabr-sys/SMC-crypto-alerts/actions/runs/42340120427) completed successfully: all 18 datasets verified and EXP-001 plus EXP-002 completed. It produced:
  - archive artifact ID `13561158245`, expires 2026-11-21 04:57 UTC;
  - research result artifact ID `13561148256`, expires 2026-11-21 04:57 UTC.
  The new EXP-003 run should be used for its own result set; do not treat the previous run as EXP-003 evidence.

## Research interpretation and limits

- The NYU paper's NASDAQ-100 results are not evidence of an edge in BTC, ETH or XAUT perpetuals.
- Quantified Strategies is a source of hypotheses, not a source of validated crypto strategies.
- EXP-003's five chronological slices are prequential periods with history carried forward; they are not five independent training/validation/OOS datasets.
- EXP-003 treats each EXP-002 strategy stream as a full-information shadow expert, including unselected counterfactual trades. A live analogue would need a dedicated parallel shadow ledger.
- 10/20/40 bps round-trip cost cases plus 1 bp/8h adverse carry stress are assumptions, not measured execution costs or realized funding. Historical spread/depth/market-impact and funding settlement semantics remain unresolved.
- EXP-003 is research-only. Its result cannot modify `APPROVED_STRATEGIES`, alter production alerts, open paper positions or submit orders.
- Existing EXP-001 result remains rejected: all 30 asset/timeframe/family OOS baseline combinations were negative at the 10 bps scenario. EXP-002 and EXP-003 results must be inspected separately before any new conclusion.

## Exact next steps

1. Re-check latest branch SHA and PR #1, then inspect historical workflow run 42341048484 until it completes.
2. Confirm the archive has 18 verified CSV datasets and that EXP-001, EXP-002 and EXP-003 steps all succeeded.
3. Download and preserve the result artifact promptly; record its ID, expiry, ZIP hash and source archive/manifest hashes.
4. Independently inspect EXP-003 summary, folds, selected-trade counts, per-asset splits and decisions at 10/20/40 bps. Check small-sample effects, empty/no-trade policies, drawdown/loss streak and fold concentration. Do not rank policies solely by the top row.
5. Compare selector results with EXP-002 individual experts and the existing EXP-001 baselines. Require separate untouched future data before considering any promotion review.
6. Keep all strategies research-only; `APPROVED_STRATEGIES` must remain empty unless new evidence passes an explicit owner-reviewed promotion gate.
7. Do not modify `main`, merge PR #1, deploy, change secrets, activate live trading or place exchange orders.

## Current state at handoff

Latest implementation commit: `fdb00a8720e9afdb7ff917d27cf31b95a5413156`.  
Both deterministic push and PR CI passed. The full historical replay including EXP-003 was still in progress at last inspection. No new strategy edge is asserted, no production alert was generated, and no live chart-to-AI or Discord-delivery claim is made.
