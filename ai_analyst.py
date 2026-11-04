"""Vision-first discretionary market analyst using the OpenAI Responses API."""
import base64
import json
import os

import requests

MODEL_DEFAULT = "gpt-6.1-terra"

SYSTEM_PROMPT = """
You are the visual SMC analyst for Salty Quant AI. Analyse the supplied raw candlestick chart images as a skilled discretionary trader would analyse a live chart screenshot.

IMPORTANT DESIGN RULES
- The chart images are the primary source for structure and context. The accompanying OHLCV rows are supplied for exact price/time precision, not for a rule-based zone algorithm.
- Do NOT use, reproduce, imitate, or rely on the repository's old ATR-zigzag, FVG-gated zone finder, scoring rules, or any precomputed supply/demand zones. Those legacy calculations are not part of this engine.
- Infer zones visually from price behaviour: consolidation/base before displacement, repeated clean reactions, wick/body origins, failed breakdowns/breakouts, and decisive role reversals. Zones must be meaningful price BANDS with a low and high, not thin arbitrary lines.
- Read Daily and 4H first for broad context; 1H for swing structure and major zones; 15m and 5m for confirmation, liquidity sweeps and executable entry timing.
- Identify demand, supply, RBS, SBR, BOS/CHOCH, equal highs/lows, buy-side/sell-side liquidity, stop runs, displacement and visible fair-value gaps where the candles support the interpretation. Do not invent a concept if the chart does not show it.
- Distinguish a genuine liquidity sweep and reclaim from a simple breakout. A role reversal needs a decisive break/close and a meaningful retest; do not label every broken level RBS/SBR.
- Report the clearest zones and levels, their timeframe, and concise visual evidence. Preserve their actual price scale.
- Prefer no trade when price is in the middle of a range, zones conflict, price has not reached an actionable area, confirmation is absent, or a clean plan cannot be formed.
- Return TRADE only when the setup is actionable at the latest closed 5m price as an immediate MARKET entry, with a realistic entry, stop beyond structural invalidation, and first target offering at least 2R. The proposed entry must be within 0.35% of the latest closed 5m price. If price must first retrace to a limit zone or wait for confirmation, return NO_TRADE. Otherwise return NO_TRADE. There is no WATCH state because Discord is reserved for execution alerts.
- Never force a trade to fill a quota. It is valid to return NO_TRADE for every symbol.
- Never claim a setup has a proven win rate. Confidence is a qualitative setup-quality estimate, not a probability.
- Use only the symbols present in the input. No external quotes or assumptions.
- Be precise and internally consistent: LONG requires stop_loss < entry < take_profit_1; SHORT requires take_profit_1 < entry < stop_loss.
- Do not provide hidden chain-of-thought. Give short evidence-based summaries only.
"""


def _zone_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "low": {"type": "number"},
            "high": {"type": "number"},
            "timeframe": {"type": "string", "enum": ["1d", "4h", "1h", "15m", "5m"]},
            "quality": {"type": "integer", "minimum": 1, "maximum": 5},
            "evidence": {"type": "string"}
        },
        "required": ["low", "high", "timeframe", "quality", "evidence"]
    }


def _liquidity_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "price": {"type": "number"},
            "kind": {"type": "string", "enum": ["EQH", "EQL", "BSL", "SSL", "SWING_HIGH", "SWING_LOW"]},
            "timeframe": {"type": "string", "enum": ["1d", "4h", "1h", "15m", "5m"]},
            "evidence": {"type": "string"}
        },
        "required": ["price", "kind", "timeframe", "evidence"]
    }


ANALYSIS_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "symbol": {"type": "string", "enum": ["BTC", "ETH", "XAU"]},
        "bias": {"type": "string", "enum": ["BULLISH", "BEARISH", "RANGE", "UNCLEAR"]},
        "structure_summary": {"type": "string"},
        "demand_zones": {"type": "array", "items": _zone_schema()},
        "supply_zones": {"type": "array", "items": _zone_schema()},
        "liquidity_levels": {"type": "array", "items": _liquidity_schema()},
        "key_observations": {"type": "array", "items": {"type": "string"}},
        "action": {"type": "string", "enum": ["NO_TRADE", "TRADE"]},
        "direction": {"type": "string", "enum": ["LONG", "SHORT", "NONE"]},
        "setup_type": {"type": "string", "enum": [
            "DEMAND_REJECTION", "SUPPLY_REJECTION", "RBS_RETEST", "SBR_RETEST",
            "LIQUIDITY_SWEEP_REVERSAL", "BREAKOUT_RETEST", "FVG_RETRACE", "OTHER", "NONE"
        ]},
        "entry_mode": {"type": "string", "enum": ["MARKET", "LIMIT", "NONE"]},
        "entry": {"type": ["number", "null"]},
        "stop_loss": {"type": ["number", "null"]},
        "take_profit_1": {"type": ["number", "null"]},
        "take_profit_2": {"type": ["number", "null"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "rationale": {"type": "string"},
        "invalidation": {"type": "string"},
        "timeframes_in_agreement": {"type": "array", "items": {"type": "string", "enum": ["1d", "4h", "1h", "15m", "5m"]}}
    },
    "required": [
        "symbol", "bias", "structure_summary", "demand_zones", "supply_zones",
        "liquidity_levels", "key_observations", "action", "direction", "setup_type",
        "entry_mode", "entry", "stop_loss", "take_profit_1", "take_profit_2",
        "confidence", "rationale", "invalidation", "timeframes_in_agreement"
    ]
}

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "market_commentary": {"type": "string"},
        "analyses": {"type": "array", "items": ANALYSIS_ITEM}
    },
    "required": ["market_commentary", "analyses"]
}


def _extract_output_text(response_json):
    if isinstance(response_json.get("output_text"), str):
        return response_json["output_text"]
    chunks = []
    for item in response_json.get("output", []):
        for part in item.get("content", []):
            if part.get("type") in ("output_text", "text") and part.get("text"):
                chunks.append(part["text"])
    if not chunks:
        raise ValueError("Responses API returned no output text")
    return "\n".join(chunks)


def analyse(chart_images, market_context, active_positions=None, model=None):
    """Send all available symbol charts in one multimodal request and return schema-validated JSON."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured in GitHub repository secrets")

    content = [{
        "type": "input_text",
        "text": (
            "Analyse this market snapshot as one cross-market quant desk. All chart timestamps are UTC. "
            "Each image contains Daily, 4H, 1H, 15m and 5m candlestick panels. "
            "The JSON below contains exact recent OHLCV candles and feed timestamps. "
            "Inspect each chart visually; use exact rows to pin price levels. "
            "Return one analysis for every symbol included, in the same order. "
            "Do not emit trade alerts for symbols with an already-open position.\n\n"
            f"MARKET DATA:\n{json.dumps(market_context, separators=(',', ':'), ensure_ascii=False)}\n\n"
            f"OPEN POSITIONS:\n{json.dumps(active_positions or {}, separators=(',', ':'), ensure_ascii=False)}"
        )
    }]
    for symbol, png_bytes in chart_images.items():
        data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
        content.append({"type": "input_text", "text": f"VISUAL CHART: {symbol}"})
        content.append({"type": "input_image", "image_url": data_url, "detail": "high"})

    chosen_model = model or os.environ.get("OPENAI_MODEL", MODEL_DEFAULT)
    body = {
        "model": chosen_model,
        "store": False,
        "max_output_tokens": 7000,
        "reasoning": {"effort": os.environ.get("OPENAI_REASONING_EFFORT", "high")},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": content}
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "salty_quant_visual_analysis",
                "strict": True,
                "schema": OUTPUT_SCHEMA
            }
        }
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=150
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI API {response.status_code}: {response.text[:1200]}")
    payload = response.json()
    text = _extract_output_text(payload)
    parsed = json.loads(text)
    expected = set(chart_images)
    returned = {item.get("symbol") for item in parsed.get("analyses", [])}
    if returned != expected:
        raise ValueError(f"Model symbols mismatch: expected {sorted(expected)}, got {sorted(returned)}")
    return parsed, {"model": chosen_model, "response_id": payload.get("id"), "usage": payload.get("usage", {})}
