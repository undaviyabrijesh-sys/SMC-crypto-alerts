# Visual-First Independent Setup Analyst — V2 Design

**Status:** implemented as an opt-in paper-only lane; push and PR CI both passed on code checkpoint `01dddffd9772e3a5d69d7e3fb25bf7afd4fa4198` (runs 42149740829 and 42149746808). Not enabled by default; no live chart/API/webhook smoke test or live execution is claimed.
**Branch:** `ai-quant-rebuild`
**Implementation commits:** initial lane `5532f7e8b9356825e33a2c22b2185dc2e14f3530`; validator/test follow-ups through `01dddffd9772e3a5d69d7e3fb25bf7afd4fa4198`.

## Objective

Make the multimodal analyst—not a coded zone, sweep, or market-structure detector—the decision-maker for each eligible closed 5-minute analysis cycle. The analyst must compare independent evidence-supported approaches from the raw six-timeframe charts and return either one best actionable candidate or `NO_TRADE`.

This design does not change the current runtime. Do not enable it, deploy it, or route its output to Discord until the implementation and tests are reviewed.

## Required analysis inputs

For BTC, ETH, and XAUT, provide:

- Fresh, closed OHLCV for 5m, 15m, 1h, 4h, 1d, and 1w.
- One unannotated six-panel chart image per symbol, with symbol, UTC candle-close timestamps, and price scale visible.
- Current paper positions and their entry/stop/target/expiry.
- A compact market snapshot for exact price pinning; OHLCV is supporting numerical context, not a replacement for visual inspection.

Reject a symbol/cycle when any required timeframe or chart is missing, stale, inconsistent, or not demonstrably closed. Do not reuse an old image after a failed refresh. Record chart/image hashes and the exact candle-close watermark with each decision.

## Independent setup families

The analyst may consider any subset supported by the chart; no family is mandatory and there is no quota:

1. SMC / market structure (BOS, CHOCH, displacement, FVG).
2. Supply and demand.
3. Liquidity sweep, reclaim, and rejection.
4. Horizontal support/resistance, RBS/SBR, range boundaries.
5. Trend continuation and pullback.
6. Momentum / impulse continuation.
7. Breakout and retest.
8. Volatility expansion / compression release.
9. Range and volatility mean reversion.
10. Other explicitly described evidence-supported behaviour.

These are independent candidate families. Do not force a DNS anchor, combine incompatible narratives, or allow an indicator to manufacture a setup. A coded zone or structure engine may not preselect, veto, or rank the visual candidates.

## Candidate comparison contract

For each viable candidate, the model must report:

- Stable candidate ID and setup family.
- Symbol, LONG/SHORT direction, trigger timeframe, and intended entry type.
- Higher-timeframe context and the specific timeframe evidence supporting or conflicting with it.
- Visible structure / price-action evidence and the chart panels where it appears.
- Entry zone (low/high) and the exact trigger condition; distinguish immediate market entry from a future limit/retest condition.
- Structural invalidation, stop price, stop distance in price and ATR units.
- Realistic first target, target rationale, reward/risk, and nearby opposing liquidity/obstacles.
- Conditions that cancel the candidate before entry.
- Conflicting signals and why they do or do not invalidate the candidate.
- Confidence / quality explanation; no unsupported numeric precision.

The analyst returns all materially viable candidates, ranks them with a short comparative explanation, and identifies at most one selected candidate. If no candidate is immediately actionable, the selected ID is null and the action is `NO_TRADE`. Do not emit a WATCH message for deferred setups.

### Proposed versioned response shape

```json
{
  "schema_version": 2,
  "cycle_id": "symbol-set-of-closed-candle-watermarks",
  "analyses": [
    {
      "symbol": "BTC",
      "as_of_utc": "ISO-8601",
      "chart_watermarks": {"5m": "...", "15m": "...", "1h": "...", "4h": "...", "1d": "...", "1w": "..."},
      "candidates": [
        {
          "candidate_id": "BTC-...",
          "setup_family": "TREND_PULLBACK",
          "direction": "LONG",
          "trigger_timeframe": "15m",
          "entry_type": "MARKET",
          "entry_zone": {"low": 0, "high": 0},
          "trigger_condition": "...",
          "higher_timeframe_context": "...",
          "supporting_evidence": ["..."],
          "conflicting_evidence": ["..."],
          "invalidation": "...",
          "stop_loss": 0,
          "stop_atr": 0,
          "target_1": 0,
          "target_rationale": "...",
          "reward_risk": 0,
          "cancel_if": ["..."],
          "confidence": 0,
          "quality_score": 0
        }
      ],
      "selected_candidate_id": null,
      "action": "NO_TRADE",
      "comparison_summary": "..."
    }
  ]
}
```

The example values are placeholders, not prices. Final JSON Schema must be strict, versioned, reject unknown symbols/families/timeframes, and enforce exactly one analysis for each requested symbol. Empty candidate lists are valid.

## Deterministic validation boundary

The model selects the market hypothesis. Code validates safety and data integrity only; it must not reconstruct market structure or choose a different setup.

Keep all existing protections unless separately tested and approved:

- Latest closed-candle watermark and chart watermark must match.
- Entry must be immediately actionable; if a future retest/limit is required, return no execution alert.
- Entry deviation remains within the configured 0.35% gate.
- Minimum reward/risk remains 2R.
- Stop distance remains within 0.35–2.5 ATR.
- Confidence/quality remains at least 75.
- LONG/SHORT level ordering, finite positive prices, ATR and stop/target arithmetic must validate.
- Reject Boolean-as-number values, NaN, infinity, stale output, missing chart evidence, malformed schema, duplicate IDs, or a selected ID not present in candidates.
- Opposing viable candidates with no clear separation must resolve to `NO_TRADE`.
- One open paper position per symbol; no duplicate signal for the same symbol/cycle.
- Any API, quota, parse, image, data, or persistence error fails closed.

The validator must return a validation result for the model-selected candidate; it must not silently substitute a lower-ranked candidate. If the selected candidate fails, record the rejection and return `NO_TRADE` for that symbol/cycle.

## Runtime integration plan

1. Add a new isolated `visual` paper mode; do not change the existing `quant` default or make `dns` the new decision path.
2. On each new closed 5m candle, fetch all six timeframes, verify freshness, render raw unannotated charts, and call the visual analyst once for the available symbols.
3. Persist input watermarks, image hashes, raw structured response, candidate comparison, validation result, and model usage to an append-only research log. Never persist credentials.
4. Run the deterministic risk validator on the single model-selected candidate.
5. Only after explicit validation, create a paper signal and send one execution-focused Discord message with setup family, rationale, entry zone/trigger, stop/invalidation, target, R:R, timeframe evidence, and cancellation conditions.
6. Track the signal using the existing closed-candle lifecycle; issue a separate update only after confirmed TP, SL, or TIME exit.
7. Keep Quant Discovery separate. Research candidates and deterministic shadow scores never enter the visual execution allowlist automatically.

## Required tests before opt-in

- Strict schema and one-analysis-per-symbol contract.
- Every independent setup family can be represented without DNS fields.
- No mandatory demand/supply zone or zone-quality field for non-DNS candidates.
- Multi-candidate comparison returns exactly one winner or `NO_TRADE`.
- Conflicting LONG/SHORT candidates fail closed.
- Selected ID missing, duplicated, or outside candidate list fails closed.
- Missing/stale/mismatched chart or timeframe blocks the cycle.
- Future/retest-only entry cannot become an immediate market alert.
- Existing 2R, 0.35–2.5 ATR, 0.35% deviation, 75 quality/confidence, one-position, and finite-number checks remain enforced.
- Model/API/quota failure produces no execution alert and is rate-limited.
- Same closed-candle watermark is analyzed at most once.
- Discord formatter contains the setup rationale and all execution levels, and never emits WATCH/status noise.
- TP/SL/TIME lifecycle tests remain green, including gap, same-bar ambiguity, missing-bar, expiry, and retry-safe notification cases.
- Mocked end-to-end visual paper cycle must run without a real API key. Real model and Discord delivery checks are separate opt-in smoke tests and must not be part of ordinary CI.

## Current blockers and guardrails

- The legacy DNS lane still uses an infrequent AI map refresh followed by a coded sweep/reclaim detector. It remains separate and unchanged; do not confuse it with the new visual lane.
- `worker.py` still defaults to AI-free quant. A third `visual` mode now imports `visual_worker.py`; the visual lane itself also requires `ENABLE_VISUAL_PAPER=true`.
- The branch's manual paper workflow now offers a visual/quant selection. Visual execution requires a separate manual boolean confirmation; scheduled runs continue to use the pre-existing quant lane and remain gated by `vars.ENABLE_GITHUB_SCHEDULE == 'true'`. The workflow has not been dispatched or enabled.
- The new visual lane requires a working OpenAI Responses API quota and existing configured `OPENAI_API_KEY`; the last documented live error was HTTP 429 insufficient quota. No credential was changed and no live API request is part of CI.
- `APPROVED_STRATEGIES` remains empty. Quant Discovery candidates remain research-only and are not promoted by the visual worker.
- The legacy scheduled workflow on `main` still runs `python main.py` with legacy WATCH/TRIGGER logic and webhook secrets. Do not modify it from this branch; obtain owner authorization for any cutover.
- No live trading, exchange orders, deployments, secret changes, schedule activation, or PR merge are permitted.

## Acceptance criterion

The visual analyst inspects fresh multi-timeframe chart images on eligible new closed-5m cycles, compares independent candidate families, and either returns one model-selected candidate that passes unchanged mechanical controls or returns `NO_TRADE`. The implementation is isolated behind `WORKER_MODE=visual` plus `ENABLE_VISUAL_PAPER=true`. CI uses mocked API/Discord calls and must never require credentials. A real paper-only vision smoke test and actual Discord delivery/outcome verification remain separate opt-in checks; keep the lane disabled unless a human explicitly confirms a manual paper run.


## Implemented components on ai-quant-rebuild

- `visual_first_analyst.py`: strict V2 multimodal Responses API contract. It receives raw six-timeframe chart PNGs and returns all material candidates, one model-selected ID or `NO_TRADE`; no DNS/zone fields exist in its schema.
- `visual_worker.py`: opt-in per-cycle chart fetch/render, candle watermarks and image hashes, model call, candidate-level fail-closed validation, append-only decision log, pending alert persistence, Discord delivery, and existing closed-5m TP/SL/TIME lifecycle tracking.
- `worker.py`: adds an opt-in `visual` mode without changing the `quant` default or the separate `dns` lane.
- `discord.py`: adds execution-only visual alerts with setup family, entry band, entry, stop, target, R:R, evidence, context, invalidation and pre-entry cancellation conditions.
- `test_visual_first.py`: offline schema, mocked multimodal request, risk-gate, candidate-selection, stale-candle, deduplication, paper-cycle and Discord-format tests. CI runs this suite without an API key or webhook.
- `.github/workflows/alerts.yml`: manual visual selection is available but requires a separate explicit paper confirmation; no workflow has been dispatched and no schedule variable was changed.

The validator validates the model-selected candidate; it does not construct zones, rank setup families, or substitute another candidate. Existing hard gates remain: confidence and quality >=75, R:R >=2, stop distance 0.35–2.5 ATR, entry band within 0.35% of the latest closed price, fresh watermarks, two or more evidence timeframes, no conflicting near-tie, and one open/pending position per symbol.