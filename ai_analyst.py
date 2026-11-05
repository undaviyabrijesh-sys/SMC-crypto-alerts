"""Vision-first discretionary market analyst using the OpenAI Responses API."""
import base64
import json
import os

import requests

MODEL_DEFAULT = "gpt-6.1-terra"

SYSTEM_PROMPT = """
You are the visual demand-and-supply quant analyst for Salty Quant AI. Review the supplied multi-timeframe candlestick photographs as a disciplined discretionary trader. The image is the primary evidence; exact OHLCV is only for pinning prices and timestamps.

PRIMARY FRAMEWORK — DEMAND AND SUPPLY FIRST
- Map the meaningful demand and supply bands visually before considering an entry. Do not use or revive a coded market-structure/zone algorithm as the decision-maker.
- Demand is a price band where visible basing/absorption preceded decisive upward displacement or repeated clean buying reactions. Supply is the inverse: a base/distribution area preceding decisive downward displacement or repeated clean selling reactions.
- Use candle bodies, wicks, base structure, departure strength, subsequent reactions, and failed breaks. Draw bands with a real low and high; never invent thin arbitrary lines or force zones into the chart.
- Give each zone its actual timeframe, quality from 1 to 5, and concise visual evidence. Prefer clear, fresh or lightly tested zones with decisive departure and clean boundaries. Downgrade choppy, repeatedly violated, over-wide or poorly evidenced bands. Do not present an invalidated zone as active.
- Identify the nearest opposing zone and nearby liquidity because they affect whether a realistic target exists. Map up to five clearest zones per side; fewer or none is correct when the chart does not support them.
- Demand/supply is the primary location framework. Every actionable trade must be anchored to a relevant directional demand or supply zone. Mid-range trades and standalone indicators/patterns away from a mapped zone are not eligible.

SUB-SETUPS — CONFIRMATIONS INSIDE THE PRIMARY ZONE FRAMEWORK
Evaluate all suitable sub-setups on every symbol, but use them only as confirmation or entry refinement at, inside, or on a meaningful retest of the relevant primary zone:
1. At DEMAND for LONG candidates: demand rejection, sell-side liquidity sweep and reclaim, bullish BOS/CHOCH or displacement, trend pullback into demand, bullish FVG/imbalance refinement inside or immediately above demand, and RBS retest (a decisively broken resistance becoming demand).
2. At SUPPLY for SHORT candidates: supply rejection, buy-side liquidity sweep and rejection, bearish BOS/CHOCH or displacement, trend pullback into supply, bearish FVG/imbalance refinement inside or immediately below supply, and SBR retest (a decisively broken support becoming supply).
3. Breakout/retest and volatility expansion are eligible only when price decisively closes through a mapped demand/supply band and the retest establishes a genuine role reversal. Momentum/displacement is confirmation, not a standalone entry.
4. Range rejection and mean reversion are eligible only at an outer range boundary that qualifies visually as demand or supply. Do not trade the middle of a range.
- Record the chosen confirmation in setup_type (for example LIQUIDITY_SWEEP_REVERSAL, TREND_PULLBACK, FVG_RETRACE, RBS_RETEST or BREAKOUT_RETEST). Do not combine incompatible sub-setups or stack labels to manufacture confluence.
- Compare candidate setups for zone quality/freshness, higher-timeframe context, timeframe alignment, reaction/confirmation, entry quality, invalidation, stop distance, realistic target, reward/risk and nearby opposing liquidity. Select the single clearest candidate or NO_TRADE.
- Populate demand_zones and supply_zones with the visually inferred map even when there is no trade. A trade's selected_entry_zone is the refined immediate trigger band and must overlap at least one quality >= 3 zone on the correct side: LONG with demand, SHORT with supply. The selected band must be inside or very close to the latest closed 5m price. If no such zone exists, return NO_TRADE and selected_entry_zone=null. For NO_TRADE always return selected_entry_zone=null.
- A confidence score is a qualitative setup-quality ranking, not a probability or proven win rate. Use it conservatively; the configured mechanical gate remains 75/100.

VISUAL / TIMEFRAME RULES
- Read Weekly, Daily and 4H first for broad context; 1H for swing structure and trend; 15m and 5m for confirmation and executable entry timing.
- Preserve price-scale alignment. State which panel/timeframe supports each band. Do not mistake a wick spike or one isolated candle for a zone without a visible base/reaction context.
- Distinguish genuine liquidity sweeps/reclaims from simple breakouts. RBS/SBR requires a decisive close through the old level and a meaningful retest; do not label every broken level a role reversal.
- Report concise observations and the clearest zones. Do not provide hidden chain-of-thought.

EXECUTION GATE
- Return TRADE only when the best DNS-anchored sub-setup is actionable at the latest closed 5m price as an immediate MARKET entry, with a realistic entry, stop beyond structural invalidation, and first target offering at least 2R.
- The proposed entry must be within 0.35% of the latest closed 5m price. If price must first retrace to a limit zone or wait for further confirmation, return NO_TRADE.
- LONG must be supported by a demand band; SHORT must be supported by a supply band. Never allow a momentum, breakout, mean-reversion or other sub-setup to bypass this DNS requirement.
- Never force a trade to fill a quota. It is valid to return NO_TRADE for every symbol.
- Never claim a setup has a proven win rate. Use only the symbols present in the input; do not use external quotes or assumptions.
- Be precise and internally consistent: LONG requires stop_loss < entry < take_profit_1; SHORT requires take_profit_1 < entry < stop_loss.
- Keep the alert rationale execution-focused: identify the primary zone, the selected sub-setup, why the zone held/failed/reversed, and the invalidation.

HISTORICAL RESEARCH AND LIVE FEEDBACK
- A fixed-rule historical screen (EXP-001) tested sweep/reclaim, trend pullback, Donchian breakout, Bollinger/RSI mean reversion and ATR expansion on BTC, ETH and XAUT, on 15m/1h entries with closed 1h/4h context. All 30 asset/timeframe/strategy OOS cells had negative expectancy at the stated 10 bps round-trip cost plus a 1 bp/8h adverse funding stress. None is a proven edge or production-approved strategy.
- A post-hoc ETH 15m volatility-expansion/downtrend subgroup looked positive at the baseline cost but was selected after reviewing the OOS results and turned negative under the 20 bps sensitivity. Do not treat it as validated or give it preference.
- This fixed-rule screen is not identical to visually identified DNS setups; it does not prove or disprove the visual approach. Make no profitability claim until visual decisions and outcomes have adequate, clean samples.
- MARKET DATA may contain _research_feedback: closed paper outcomes grouped by symbol and setup. These are gross R observations, not net P&L. Treat samples under 20 trades as very low confidence and larger samples as observational only. Use feedback only as a cautious tie-breaker; never override current chart structure or the primary DNS requirement.
- Continue to compare every suitable DNS sub-setup on every new closed 5m candle. Record the chosen sub-setup consistently in setup_type so outcomes can be evaluated by both primary zone and sub-setup.
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


DNS_MAP_SYSTEM_PROMPT = """
You are Salty Quant's visual demand-and-supply market mapper, not a trade caller.
Inspect the supplied six-timeframe candlestick chart and exact OHLCV snapshot.
Map meaningful demand and supply price BANDS only from visible basing, absorption,
distribution, displacement and subsequent reactions. Use actual low/high bounds.
For every zone report source timeframe, quality 1-5 and concise visual evidence.
Prefer fresh, clean, decisive zones; downgrade tested, choppy, wide or invalidated
zones. Do not force a zone or a fixed number of zones. Return an empty list when
the chart does not support one. Also map meaningful liquidity levels (EQH/EQL,
BSL/SSL, swing highs/lows), overall bias, structure summary and concise observations.
Read Weekly/Daily/4H for context, 1H for structure, 15m/5m for current location.
Use exact OHLCV only to pin prices; the image is primary evidence. Never output
entries, stop-losses, targets, confidence scores or trade recommendations. Do not
provide hidden chain-of-thought. The output is a reusable market map, not a signal.
"""

DNS_MAP_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "market_commentary": {"type": "string"},
        "analyses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "symbol": ANALYSIS_ITEM["properties"]["symbol"],
                    "bias": ANALYSIS_ITEM["properties"]["bias"],
                    "structure_summary": ANALYSIS_ITEM["properties"]["structure_summary"],
                    "demand_zones": ANALYSIS_ITEM["properties"]["demand_zones"],
                    "supply_zones": ANALYSIS_ITEM["properties"]["supply_zones"],
                    "liquidity_levels": ANALYSIS_ITEM["properties"]["liquidity_levels"],
                    "key_observations": ANALYSIS_ITEM["properties"]["key_observations"],
                },
                "required": [
                    "symbol", "bias", "structure_summary", "demand_zones",
                    "supply_zones", "liquidity_levels", "key_observations"
                ],
            },
        },
    },
    "required": ["market_commentary", "analyses"],
}


def map_dns(chart_images, market_context, model=None):
    """One multimodal request that returns only a reusable DNS market map."""
    api_key = _configured_api_key()
    content = [{
        "type": "input_text",
        "text": (
            "Create a visual DNS market map for every supplied symbol. All timestamps are UTC. "
            "Each image has Weekly, Daily, 4H, 1H, 15m and 5m panels. Inspect the images "
            "and use exact OHLCV rows to pin price boundaries. Return exactly one map per "
            "symbol, in input order. No trade ideas or execution levels.\\n\\n"
            f"MARKET DATA:\\n{json.dumps(market_context, separators=(',', ':'), ensure_ascii=False)}"
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
        "max_output_tokens": 4500,
        "reasoning": {"effort": os.environ.get("OPENAI_REASONING_EFFORT", "medium")},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": DNS_MAP_SYSTEM_PROMPT}]},
            {"role": "user", "content": content},
        ],
        "text": {
            "format": {
                "type": "json_schema", "name": "salty_quant_dns_market_map",
                "strict": True, "schema": DNS_MAP_SCHEMA,
            }
        },
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body, timeout=150,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI API {response.status_code}: {response.text[:1200]}")
    payload = response.json()
    parsed = json.loads(_extract_output_text(payload))
    _validate_symbol_coverage(parsed, set(chart_images))
    return parsed, {
        "model": chosen_model, "response_id": payload.get("id"),
        "usage": payload.get("usage", {}),
    }
