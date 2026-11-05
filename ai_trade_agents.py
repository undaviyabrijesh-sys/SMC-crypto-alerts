"""TradingAgents-inspired bull/bear review for rare DNS-triggered opportunities.

The visual DNS mapper remains the market-structure source of truth. The local DNS
watcher discovers candidate events. These three independent roles challenge a
candidate only after that deterministic trigger appears; none can edit prices.
The deterministic DNS/risk checks remain authoritative.
"""
import json
import os

import requests

import ai_analyst


RESEARCHER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "stance": {"type": "string", "enum": ["SUPPORT", "CHALLENGE", "MIXED"]},
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stance", "summary", "evidence", "risks"],
}

TRADER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["APPROVE", "REJECT", "NO_TRADE"]},
        "rationale": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "rationale", "key_risks"],
}

PROMPTS = {
    "BULL_RESEARCHER": (
        "You are the independent Bull Researcher on Salty Quant. Make the strongest "
        "evidence-based case FOR this exact candidate. Use only the supplied AI-mapped "
        "DNS zones, liquidity observations, candidate and closed OHLCV bars. Check that "
        "a LONG is genuinely at demand or a SHORT at supply, that the zone is active, "
        "and that the trigger is supported. Explicitly identify contrary evidence. "
        "Do not invent order-book data, news, indicators or price levels. Do not change "
        "entry, stop or target. Return concise structured evidence, not hidden reasoning."
    ),
    "BEAR_RESEARCHER": (
        "You are the independent Bear Researcher and adversarial reviewer. Try to "
        "disprove this exact candidate. Check stale or invalidated zones, weak location, "
        "nearby opposing liquidity/zones, contradictory timeframe context, failed "
        "confirmation, chasing and unrealistic reward space. Use only supplied evidence; "
        "OHLCV liquidity is a proxy, not proof of resting orders. Do not invent data or "
        "change prices. Return concise structured objections, not hidden reasoning."
    ),
    "CHIEF_TRADER": (
        "You are the Chief Trader. Review the original candidate, the visual DNS map, "
        "the closed OHLCV snapshot, and the independent Bull and Bear reports. Choose "
        "APPROVE only when the directional zone and trigger are well supported and "
        "the Bear objections are adequately answered. Choose NO_TRADE when evidence is "
        "mixed or incomplete; REJECT when the setup is materially flawed. Never alter "
        "entry, stop-loss or target and never waive mechanical checks. The deterministic "
        "risk manager has final authority after your advisory decision. Do not provide "
        "hidden chain-of-thought."
    ),
}


def enabled():
    """AI debate is opt-in; DNS mapping/local scanning work without this setting."""
    return os.environ.get("AI_TRADE_DEBATE_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _round_number(value):
    number = float(value)
    return round(number, 8)


def _market_evidence(candidate, snapshot, frames):
    """Build a compact, closed-candle-only evidence packet for the agents."""
    bars = {}
    for timeframe, frame in (frames or {}).items():
        if frame is None or frame.empty:
            continue
        recent = []
        for stamp, row in frame.tail(3).iterrows():
            recent.append({
                "time_utc": stamp.isoformat(),
                "open": _round_number(row.open),
                "high": _round_number(row.high),
                "low": _round_number(row.low),
                "close": _round_number(row.close),
                "volume": _round_number(row.volume),
            })
        bars[timeframe] = recent

    map_data = snapshot if isinstance(snapshot, dict) else {}
    def zones(name):
        return [{
            "low": z.get("low"), "high": z.get("high"),
            "timeframe": z.get("timeframe"), "quality": z.get("quality"),
            "status": z.get("status"), "evidence": z.get("evidence"),
        } for z in map_data.get(name, []) if isinstance(z, dict)]

    liquidity = [
        {
            "price": item.get("price"), "kind": item.get("kind"),
            "timeframe": item.get("timeframe"), "evidence": item.get("evidence"),
        }
        for item in map_data.get("liquidity_levels", [])
        if isinstance(item, dict)
    ]
    return {
        "candidate": candidate,
        "market_map": {
            "symbol": map_data.get("symbol"),
            "revision": map_data.get("revision"),
            "mapped_at": map_data.get("mapped_at"),
            "reference_price": map_data.get("reference_price"),
            "bias": map_data.get("bias"),
            "structure_summary": map_data.get("structure_summary"),
            "demand_zones": zones("demand_zones"),
            "supply_zones": zones("supply_zones"),
            "liquidity_levels": liquidity[:20],
            "key_observations": map_data.get("key_observations", [])[:12],
        },
        "closed_ohlcv_last_three_bars_by_timeframe": bars,
        "data_limits": [
            "Only closed OHLCV bars are supplied.",
            "No order-book depth, historical spread or external news is supplied.",
            "A wick/sweep is an OHLCV proxy, not proof of resting liquidity.",
        ],
    }


def _schema_for(role):
    return TRADER_SCHEMA if role == "CHIEF_TRADER" else RESEARCHER_SCHEMA


def _request_agent(role, evidence):
    """Call one role through the same Responses API/model configuration as ai_analyst."""
    if role not in PROMPTS:
        raise ValueError(f"Unknown research role: {role}")
    api_key = ai_analyst._configured_api_key()
    model, effort = ai_analyst._model_settings()
    schema = _schema_for(role)
    body = {
        "model": model,
        "store": False,
        "max_output_tokens": 900,
        "reasoning": {"effort": effort},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": PROMPTS[role]}]},
            {"role": "user", "content": [{
                "type": "input_text",
                "text": json.dumps(evidence, separators=(",", ":"), ensure_ascii=False, default=str),
            }]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "salty_" + role.lower(),
                "strict": True,
                "schema": schema,
            }
        },
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=75,
    )
    if not response.ok:
        # Avoid logging request headers or credentials. Keep the provider error useful.
        raise RuntimeError(f"OpenAI API {response.status_code}: {response.text[:500]}")
    payload = response.json()
    parsed = json.loads(ai_analyst._extract_output_text(payload))
    if not isinstance(parsed, dict):
        raise ValueError(f"{role} returned a non-object response")
    return parsed, {
        "model": model,
        "response_id": payload.get("id"),
        "usage": payload.get("usage", {}),
    }


def _invoke(role, evidence, call_agent):
    result = call_agent(role, evidence) if call_agent else _request_agent(role, evidence)
    if isinstance(result, tuple):
        parsed, metadata = result
    else:
        parsed, metadata = result, {}
    if not isinstance(parsed, dict):
        raise ValueError(f"{role} did not return a JSON object")
    return parsed, metadata if isinstance(metadata, dict) else {}


def _validate_researcher(role, report):
    if report.get("stance") not in {"SUPPORT", "CHALLENGE", "MIXED"}:
        raise ValueError(f"{role} returned an invalid stance")
    if not isinstance(report.get("summary"), str) or not report["summary"].strip():
        raise ValueError(f"{role} returned no summary")
    for key in ("evidence", "risks"):
        if not isinstance(report.get(key), list) or any(not isinstance(x, str) for x in report[key]):
            raise ValueError(f"{role} returned invalid {key}")
        report[key] = [item[:300] for item in report[key][:6]]
    report["summary"] = report["summary"][:700]


def _validate_trader(report):
    if report.get("decision") not in {"APPROVE", "REJECT", "NO_TRADE"}:
        raise ValueError("Chief Trader returned an invalid decision")
    if not isinstance(report.get("rationale"), str) or not report["rationale"].strip():
        raise ValueError("Chief Trader returned no rationale")
    risks = report.get("key_risks")
    if not isinstance(risks, list) or any(not isinstance(x, str) for x in risks):
        raise ValueError("Chief Trader returned invalid key_risks")
    report["rationale"] = report["rationale"][:700]
    report["key_risks"] = [item[:300] for item in risks[:8]]


def review_candidate(candidate, snapshot, frames, *, enabled_override=None, call_agent=None):
    """Run Bull -> Bear -> Chief Trader only after a local DNS trigger.

    DISABLED preserves the deterministic DNS path. When enabled, only an explicit
    APPROVE allows the caller to continue; API errors and malformed answers fail closed.
    This layer is advisory and cannot create or edit execution levels.
    """
    is_enabled = enabled() if enabled_override is None else bool(enabled_override)
    if not is_enabled:
        return {"status": "DISABLED", "reason": "AI trade debate is opt-in"}

    evidence = _market_evidence(candidate, snapshot, frames)
    metadata = []
    try:
        bull, meta = _invoke("BULL_RESEARCHER", evidence, call_agent)
        _validate_researcher("BULL_RESEARCHER", bull)
        metadata.append(meta)

        bear, meta = _invoke("BEAR_RESEARCHER", evidence, call_agent)
        _validate_researcher("BEAR_RESEARCHER", bear)
        metadata.append(meta)

        trader_payload = {
            **evidence,
            "bull_researcher_report": bull,
            "bear_researcher_report": bear,
        }
        trader, meta = _invoke("CHIEF_TRADER", trader_payload, call_agent)
        _validate_trader(trader)
        metadata.append(meta)
        decision = trader["decision"]
        return {
            "status": "APPROVED" if decision == "APPROVE" else "REJECTED",
            "decision": decision,
            "bull": bull,
            "bear": bear,
            "trader": trader,
            "metadata": metadata,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            "completed_roles": len(metadata),
            "metadata": metadata,
        }
