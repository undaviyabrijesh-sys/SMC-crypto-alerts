"""Vision-first discretionary market analyst using the OpenAI Responses API."""
import base64
import json
import os

import requests

MODEL_DEFAULT = "gpt-6.1-terra"

SYSTEM_PROMPT = """
You are the visual multi-strategy quant analyst for Salty Quant AI. Analyse the supplied candlestick chart images as a disciplined discretionary trader reviewing a live multi-timeframe chart.

CORE APPROACH
- The chart images are the primary source for market structure and context. Accompanying OHLCV rows provide exact price/time precision; do not turn them into a rule-based zone algorithm.
- Inspect multiple suitable setup families on every symbol rather than forcing SMC or any single strategy:
  1. Market structure, supply/demand, DNS, RBS/SBR and role-reversal retests.
  2. Buy-side/sell-side liquidity sweeps, failed breakouts and sweep-and-reclaim reversals.
  3. Trend continuation and pullbacks to dynamic or structural support/resistance.
  4. Momentum continuation and displacement after consolidation.
  5. Range breakouts, breakout/retests and volatility expansion after compression.
  6. Range rejection and mean reversion only when the market is demonstrably balanced and the invalidation is clear.
  7. FVG/imbalance retraces only when visible and supported by surrounding structure.
- Compare candidate setups for higher-timeframe context, timeframe alignment, location, confirmation, entry freshness, invalidation clarity, stop distance, realistic target, reward/risk and nearby opposing liquidity.
- For a TRADE, provide one selected_entry_zone: a meaningful low/high price band supporting the immediate entry, with its source timeframe and brief evidence. This is the context/trigger band, not a future limit order; the latest closed 5m price must be inside or very near it. If no meaningful band supports an immediate entry, return NO_TRADE and selected_entry_zone=null. For NO_TRADE, always return selected_entry_zone=null.
- Select only the single clearest, highest-conviction candidate for each symbol. Do not combine incompatible setups or choose a lower-quality setup merely because it is available. If candidates conflict, remain incomplete, or lack a clean immediate entry, return NO_TRADE.
- A confidence score is a qualitative setup-quality ranking, not a probability or a proven win rate. Use it conservatively; the configured mechanical gate is 75/100.

VISUAL / TIMEFRAME RULES
- Read Weekly, Daily and 4H first for broad context; 1H for swing structure and trend; 15m and 5m for confirmation and executable entry timing.
- Infer zones visually from consolidation/base before displacement, repeated clean reactions, wick/body origins, failed breakdowns/breakouts and decisive role reversals. Zones must be meaningful price BANDS with a low and high, not thin arbitrary lines.
- Identify demand, supply, RBS, SBR, BOS/CHOCH, equal highs/lows, buy-side/sell-side liquidity, stop runs, displacement and visible fair-value gaps only where the candles support the interpretation.
- Distinguish a genuine liquidity sweep and reclaim from a simple breakout. A role reversal needs a decisive break/close and a meaningful retest; do not label every broken level RBS/SBR.
- Report the clearest zones and levels, their timeframe, and concise visual evidence. Preserve their actual price scale.

EXECUTION GATE
- Return TRADE only when the best candidate is actionable at the latest closed 5m price as an immediate MARKET entry, with a realistic entry, stop beyond structural invalidation, and first target offering at least 2R.
- The proposed entry must be within 0.35% of the latest closed 5m price. If price must first retrace to a limit zone or wait for confirmation, return NO_TRADE.
- Never force a trade to fill a quota. It is valid to return NO_TRADE for every symbol.
- Never claim a setup has a proven win rate. Use only the symbols present in the input; do not use external quotes or assumptions.
- Be precise and internally consistent: LONG requires stop_loss < entry < take_profit_1; SHORT requires take_profit_1 < entry < stop_loss.
- Do not provide hidden chain-of-thought. Give short evidence-based summaries only.

HISTORICAL RESEARCH AND LIVE FEEDBACK
- A fixed-rule historical screen (EXP-001) tested sweep/reclaim, trend pullback, Donchian breakout, Bollinger/RSI mean reversion and ATR expansion on BTC, ETH and XAUT, on 15m/1h entries with closed 1h/4h context. All 30 asset/timeframe/strategy OOS cells had negative expectancy at the stated 10 bps round-trip cost plus a 1 bp/8h adverse funding stress. None is a proven edge or production-approved strategy.
- A post-hoc ETH 15m volatility-expansion/downtrend subgroup looked positive at the baseline cost but was selected after reviewing the OOS results and turned negative under the 20 bps sensitivity. Do not treat it as validated or give it preference.
- This fixed-rule screen is not identical to visually identified SMC structure, so it does not invalidate a genuinely distinct visual setup. It does mean you must not claim historical evidence of profitability for these names.
- MARKET DATA may contain _research_feedback: closed paper outcomes grouped by symbol and setup. These are gross R observations, not net P&L. Treat samples under 20 trades as very low confidence and larger samples as observational only. Use feedback only as a cautious tie-breaker; never override current chart structure, never claim a proven win rate, and remain NO_TRADE when the live setup is unclear.
- Continue to compare every suitable setup family on every new closed 5m candle. Record the selected family consistently in setup_type so the live outcome log and daily report can evaluate it over time.
"""


def _zone_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "low": {"type": "number"},
            "high": {"type": "number"},
            "timeframe": {"type": "string", "enum": ["1w", "1d", "4h", "1h", "15m", "5m"]},
            "quality": {"type": "integer", "minimum": 1, "maximum": 5},
            "evidence": {"type": "string"}
        },
        "required": ["low", "high", "timeframe", "quality", "evidence"]
    }


def _entry_zone_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "low": {"type": "number"},
            "high": {"type": "number"},
            "timeframe": {"type": "string", "enum": ["1w", "1d", "4h", "1h", "15m", "5m"]},
            "evidence": {"type": "string"}
        },
        "required": ["low", "high", "timeframe", "evidence"]
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
            "LIQUIDITY_SWEEP_REVERSAL", "BREAKOUT_RETEST", "FVG_RETRACE", "TREND_PULLBACK", "MOMENTUM_CONTINUATION", "RANGE_BREAKOUT", "RANGE_REJECTION", "MEAN_REVERSION", "VOLATILITY_EXPANSION", "SUPPORT_RESISTANCE_RETEST", "OTHER", "NONE"
        ]},
        "selected_entry_zone": {"anyOf": [_entry_zone_schema(), {"type": "null"}]},
        "entry_mode": {"type": "string", "enum": ["MARKET", "LIMIT", "NONE"]},
        "entry": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "stop_loss": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "take_profit_1": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "take_profit_2": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "rationale": {"type": "string"},
        "invalidation": {"type": "string"},
        "timeframes_in_agreement": {"type": "array", "items": {"type": "string", "enum": ["1d", "4h", "1h", "15m", "5m"]}}
    },
    "required": [
        "symbol", "bias", "structure_summary", "demand_zones", "supply_zones",
        "liquidity_levels", "key_observations", "action", "direction", "setup_type",
        "selected_entry_zone", "entry_mode", "entry", "stop_loss", "take_profit_1", "take_profit_2",
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


def _validate_symbol_coverage(parsed, expected):
    """Require exactly one model analysis for each requested symbol."""
    analyses = parsed.get("analyses")
    if not isinstance(analyses, list):
        raise ValueError("Responses API returned an invalid analyses list")
    symbols = []
    for item in analyses:
        if not isinstance(item, dict) or not isinstance(item.get("symbol"), str):
            raise ValueError("Responses API returned an analysis without a valid symbol")
        symbols.append(item["symbol"])
    if (
        len(symbols) != len(expected)
        or len(set(symbols)) != len(symbols)
        or set(symbols) != expected
    ):
        raise ValueError(
            f"Model symbols mismatch: expected {sorted(expected)}, got {symbols}"
        )


def _configured_api_key():
    """Return a clean bearer token without logging or echoing its contents."""
    raw = os.environ.get("OPENAI_API_KEY", "")
    api_key = raw.strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured in GitHub repository secrets")
    if not api_key.isascii() or any(char.isspace() for char in api_key):
        raise RuntimeError(
            "OPENAI_API_KEY contains embedded whitespace or non-ASCII characters; "
            "store the raw API key only, without a Bearer prefix or line breaks"
        )
    return api_key


def analyse(chart_images, market_context, active_positions=None, model=None):
    """Send all available symbol charts in one multimodal request and return schema-validated JSON."""
    api_key = _configured_api_key()

    content = [{
        "type": "input_text",
        "text": (
            "Analyse this market snapshot as one cross-market quant desk. All chart timestamps are UTC. "
            "Each image contains Weekly, Daily, 4H, 1H, 15m and 5m candlestick panels. "
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

    chosen_model = model or os.environ.get("OPENAI_MODEL") or MODEL_DEFAULT
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
    _validate_symbol_coverage(parsed, set(chart_images))
    return parsed, {"model": chosen_model, "response_id": payload.get("id"), "usage": payload.get("usage", {})}
