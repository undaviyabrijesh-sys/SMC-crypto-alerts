"""Independent multimodal setup comparison for the Salty Quant visual-first lane.

This module deliberately has no DNS/zone-engine dependency. The model inspects the
raw six-timeframe charts and selects one candidate or NO_TRADE; deterministic code
only validates timestamps, arithmetic and risk.
"""
import base64
import json

import requests

import ai_analyst


TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d", "1w")
SETUP_FAMILIES = (
    "SMC_MARKET_STRUCTURE",
    "SUPPLY_DEMAND",
    "LIQUIDITY_SWEEP",
    "SUPPORT_RESISTANCE",
    "TREND_PULLBACK",
    "MOMENTUM_CONTINUATION",
    "BREAKOUT_RETEST",
    "VOLATILITY_EXPANSION",
    "MEAN_REVERSION",
    "OTHER_EVIDENCE_SUPPORTED",
)

SYSTEM_PROMPT = """
You are Salty Quant's independent visual trading analyst. The six-panel chart image
is the primary evidence. Exact closed OHLCV and timestamps are supplied only to pin
price and verify the candle watermark. Inspect every panel: 1w, 1d, 4h, 1h, 15m, 5m.

INDEPENDENT SETUP COMPARISON — NO MANDATORY DNS ANCHOR
Evaluate every evidence-supported approach that is actually present in the charts.
Possible independent families include:
- SMC / market structure (BOS, CHOCH, displacement, FVG);
- supply and demand;
- liquidity sweep, reclaim and rejection;
- horizontal support/resistance, RBS/SBR and range boundaries;
- trend continuation and pullback;
- momentum / impulse continuation;
- breakout and retest;
- volatility expansion / compression release;
- range or volatility mean reversion;
- another explicitly described, evidence-supported behaviour.

These are independent candidates, not confirmations inside a required DNS framework.
Do not require a supply/demand zone, do not invent zones, and do not use a coded
market-structure/zone/sweep detector as a decision-maker. No setup family has a quota.
Do not combine incompatible narratives or stack labels to manufacture confluence.

For each materially viable candidate, report:
- candidate ID, one setup family, LONG/SHORT, trigger timeframe, and entry type;
- an actual price entry band and the exact trigger condition;
- higher-timeframe context, evidence timeframes, and visible chart evidence;
- conflicting evidence, and why it matters;
- structural invalidation and stop-loss;
- realistic first target, target rationale, and reward/risk from the latest closed 5m
  close to the proposed stop and target;
- explicit cancellation conditions;
- conservative confidence and quality scores from 0-100. These are rubric scores,
  not win probabilities or proven performance.

Compare candidates for context, timeframe alignment, entry quality, stop distance,
nearby opposing liquidity/obstacles, realistic target, R:R and conflicting signals.
Return all materially viable candidates and a short comparative summary. Select at
most one candidate. The selected candidate must be the clearest highest-conviction
immediately actionable setup. If no candidate is immediately actionable, choose
action=NO_TRADE and selected_candidate_id=null. Never select a future limit, retest
or wait-for-confirmation setup as an immediate market trade; such candidates may be
described but their entry_type must not be MARKET.

For a TRADE selection:
- entry_type must be MARKET and its trigger must already be confirmed on closed bars;
- use only the supplied symbols and exact chart watermarks;
- entry_zone must be close enough to the latest closed 5m price to pass the code gate;
- stop must sit beyond the described structural invalidation;
- target_1 must be realistic and offer at least 2R;
- cite at least two timeframe panels, including the trigger timeframe;
- do not select if an opposing, similarly strong candidate makes direction unclear.

Do not provide hidden chain-of-thought. Return concise evidence and comparative
rationale only. Do not emit WATCH or status messages. Do not claim a setup has a
proven win rate. A valid NO_TRADE for every symbol is preferable to a weak signal.
""".strip()


def _entry_zone_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "low": {"type": "number"},
            "high": {"type": "number"},
            "timeframe": {"type": "string", "enum": list(TIMEFRAMES)},
            "evidence": {"type": "string"},
        },
        "required": ["low", "high", "timeframe", "evidence"],
    }


CANDIDATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidate_id": {"type": "string"},
        "setup_family": {"type": "string", "enum": list(SETUP_FAMILIES)},
        "direction": {"type": "string", "enum": ["LONG", "SHORT"]},
        "trigger_timeframe": {"type": "string", "enum": list(TIMEFRAMES)},
        "entry_type": {"type": "string", "enum": ["MARKET", "LIMIT", "RETEST", "CONDITIONAL"]},
        "entry_zone": _entry_zone_schema(),
        "trigger_condition": {"type": "string"},
        "higher_timeframe_context": {"type": "string"},
        "supporting_evidence": {"type": "array", "items": {"type": "string"}},
        "evidence_timeframes": {"type": "array", "items": {"type": "string", "enum": list(TIMEFRAMES)}},
        "conflicting_evidence": {"type": "array", "items": {"type": "string"}},
        "timeframes_in_agreement": {"type": "array", "items": {"type": "string", "enum": list(TIMEFRAMES)}},
        "stop_loss": {"type": "number"},
        "target_1": {"type": "number"},
        "reward_risk": {"type": "number"},
        "target_rationale": {"type": "string"},
        "invalidation": {"type": "string"},
        "cancel_if": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "quality_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "selection_rationale": {"type": "string"},
    },
    "required": [
        "candidate_id", "setup_family", "direction", "trigger_timeframe", "entry_type",
        "entry_zone", "trigger_condition", "higher_timeframe_context",
        "supporting_evidence", "evidence_timeframes", "conflicting_evidence",
        "timeframes_in_agreement", "stop_loss", "target_1", "reward_risk",
        "target_rationale", "invalidation", "cancel_if", "confidence",
        "quality_score", "selection_rationale",
    ],
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "symbol": {"type": "string", "enum": ["BTC", "ETH", "XAU"]},
        "as_of_utc": {"type": "string"},
        "chart_watermarks": {
            "type": "object",
            "additionalProperties": False,
            "properties": {tf: {"type": "string"} for tf in TIMEFRAMES},
            "required": list(TIMEFRAMES),
        },
        "candidates": {"type": "array", "items": CANDIDATE_SCHEMA},
        "selected_candidate_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "action": {"type": "string", "enum": ["TRADE", "NO_TRADE"]},
        "comparison_summary": {"type": "string"},
    },
    "required": [
        "symbol", "as_of_utc", "chart_watermarks", "candidates",
        "selected_candidate_id", "action", "comparison_summary",
    ],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "integer", "enum": [2]},
        "cycle_id": {"type": "string"},
        "market_commentary": {"type": "string"},
        "analyses": {"type": "array", "items": ANALYSIS_SCHEMA},
    },
    "required": ["schema_version", "cycle_id", "market_commentary", "analyses"],
}


def validate_response_coverage(parsed, expected_symbols, cycle_id):
    """Require a V2 response with exactly one analysis for each requested symbol."""
    if not isinstance(parsed, dict) or parsed.get("schema_version") != 2:
        raise ValueError("visual analyst response must use schema_version=2")
    if parsed.get("cycle_id") != cycle_id:
        raise ValueError("visual analyst response cycle_id does not match the request")
    analyses = parsed.get("analyses")
    if not isinstance(analyses, list):
        raise ValueError("visual analyst response analyses must be a list")
    symbols = []
    for item in analyses:
        if not isinstance(item, dict) or not isinstance(item.get("symbol"), str):
            raise ValueError("visual analyst response contains an analysis without a symbol")
        symbols.append(item["symbol"])
    if len(symbols) != len(expected_symbols) or len(set(symbols)) != len(symbols) or set(symbols) != set(expected_symbols):
        raise ValueError(
            f"visual analyst symbol coverage mismatch: expected {sorted(expected_symbols)}, got {symbols}"
        )
    return {item["symbol"]: item for item in analyses}


def analyse(chart_images, market_context, active_positions=None, model=None):
    """Inspect raw chart images and return the strict independent-candidate V2 contract."""
    if not isinstance(chart_images, dict) or not chart_images:
        raise ValueError("visual analyst requires at least one fresh chart image")
    visual_context = market_context.get("_visual_first") if isinstance(market_context, dict) else None
    if not isinstance(visual_context, dict) or not visual_context.get("cycle_id"):
        raise ValueError("visual analyst request is missing its cycle metadata")

    api_key = ai_analyst._configured_api_key()
    content = [{
        "type": "input_text",
        "text": (
            "Review the raw multi-timeframe images and compare independent setup families. "
            "All timestamps are UTC. Copy the supplied UTC close watermarks exactly. "
            "Return one analysis per supplied symbol and use the request cycle_id exactly.\n\n"
            f"MARKET DATA:\n{json.dumps(market_context, separators=(',', ':'), ensure_ascii=False)}\n\n"
            f"OPEN PAPER POSITIONS:\n{json.dumps(active_positions or {}, separators=(',', ':'), ensure_ascii=False)}"
        ),
    }]
    for symbol, png_bytes in chart_images.items():
        if not isinstance(png_bytes, (bytes, bytearray)) or not png_bytes:
            raise ValueError(f"missing or invalid chart image for {symbol}")
        data_url = "data:image/png;base64," + base64.b64encode(bytes(png_bytes)).decode("ascii")
        content.append({"type": "input_text", "text": f"RAW SIX-TIMEFRAME CHART: {symbol}"})
        content.append({"type": "input_image", "image_url": data_url, "detail": "high"})

    chosen_model, reasoning_effort = ai_analyst._model_settings(model)
    body = {
        "model": chosen_model,
        "store": False,
        "max_output_tokens": 7000,
        "reasoning": {"effort": reasoning_effort},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": content},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "salty_quant_visual_first_v2",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=150,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI API {response.status_code}: {response.text[:1200]}")
    payload = response.json()
    parsed = json.loads(ai_analyst._extract_output_text(payload))
    validate_response_coverage(parsed, set(chart_images), visual_context["cycle_id"])
    return parsed, {
        "model": chosen_model,
        "response_id": payload.get("id"),
        "usage": payload.get("usage", {}),
    }
