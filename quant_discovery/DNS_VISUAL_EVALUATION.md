# DNS visual-first evaluation plan

## Production hypothesis

Demand and supply (DNS) is the primary location framework. The chart image, not a coded structure/zone algorithm, is the source of zone inference. The model maps price bands and records timeframe, bounds, visual evidence and a quality score. Liquidity sweeps, BOS/CHOCH, trend pullbacks, FVGs, RBS/SBR, breakouts/retests, momentum and range behaviour are secondary sub-setups: they refine or confirm a DNS interaction and cannot create a trade in the middle of a range or away from the relevant band.

## Image audit

For every successful AI cycle, retain two images per symbol:
- `<SYMBOL>_raw.png`: exact chart image sent to the model.
- `<SYMBOL>_latest.png`: same six timeframe panels with model-reported demand bands, supply bands and selected entry band drawn on the matching timeframe panel.

Demand bands use green, supply bands red, and the refined selected-entry band a yellow dashed outline. The renderer preserves source price scales and does not calculate any zones. The raw image remains the input to the model; the annotation is generated only after the response, avoiding a feedback loop where the model sees its own drawings. GitHub Actions manual runs upload both images as a seven-day artifact; Docker writes them into the persistent data volume under `market_data/review_charts/` (or the configured `CHART_REVIEW_DIR`).

The research JSONL record includes the response, per-symbol raw/review file paths, SHA-256 values and byte counts, together with the model output and OHLCV context.

## Execution eligibility

A LONG candidate must have a selected immediate entry band overlapping an AI-mapped demand band with quality at least 3/5. A SHORT candidate must overlap a quality at least 3/5 supply band. The zone and entry must be within the existing 0.35% current-price tolerance. The current 75/100 confidence floor, minimum 2R first target, valid SL/TP ordering, latest closed 5m freshness and one-open-paper-position-per-symbol restrictions remain unchanged. No limit setup is silently treated as filled. The AI still decides the visual structure; the deterministic gate only checks the returned plan.

## Evaluation protocol

1. Restore an available OpenAI API quota and run one manual, paper-only cycle; do not enable a recurring scheduler for first validation.
2. Inspect paired raw/annotated images for BTC, ETH and XAU. Check price-scale alignment, meaningful zones, correct timeframe attribution, zone width, departure strength, freshness, retests and whether the model labels invalidated zones as active.
3. Audit the AI's zone bands against the raw candles without looking at subsequent outcomes. Record agreement/disagreement and any mapping corrections in a separate audit table, not by retroactively changing the AI output.
4. Track every eligible alert through its confirmed TP, SL or TIME outcome. Store primary zone side/timeframe/quality, sub-setup, entry/stop/target, and chart/response hashes.
5. Report results by symbol, DNS side, zone timeframe/quality and sub-setup. Include sample count, win rate, expectancy in R, profit factor, max drawdown, consecutive losses, time-in-trade, costs and market regime. Do not rank small samples as edges.
6. Keep paper-only until there is enough independent data to assess zone-mapping accuracy and net execution outcomes; use chronological splits and out-of-sample review before claiming an edge.

## Current evidence and blocker

The code now creates chart overlays, saves paired image evidence, requires directional DNS alignment at the mechanical gate, and formats alerts with the primary DNS band. Automated tests cover rendering, persistence, overlap, quality, direction and alert formatting. This establishes code-path behaviour only; it does not establish that the vision model draws accurate zones or that the setup is profitable.

The last actual Responses API attempt reached OpenAI and returned HTTP 429 `insufficient_quota / credit_balance_exhausted`. Until API quota is restored, no genuine chart-to-AI zone map can be observed. Do not retry repeatedly, lower confidence/RR/zone-quality thresholds, or promote a candidate without fresh model output and paper outcomes.
