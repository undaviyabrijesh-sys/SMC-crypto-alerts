"""Deterministic candidate ranking and fail-closed mechanical risk validation."""
import math

MIN_QUALITY_SCORE = 75
MIN_REWARD_RISK = 2.0
OPPOSING_SIGNAL_TIE_MARGIN = 8

# No current research candidate has passed the repository's full OOS + walk-forward
# + stressed-cost promotion protocol. Keep this empty until a reviewed promotion.
APPROVED_STRATEGIES = frozenset()


def _finite_positive(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def validate_candidate(candidate, current_price, latest_candle=None):
    """Validate a generated candidate; this function never invents an entry or stop."""
    if not isinstance(candidate, dict):
        return False, "candidate is not an object"
    direction = candidate.get("direction")
    if direction not in ("LONG", "SHORT"):
        return False, "invalid direction"
    entry = _finite_positive(candidate.get("entry"))
    stop = _finite_positive(candidate.get("stop_loss"))
    target = _finite_positive(candidate.get("take_profit"))
    price = _finite_positive(current_price)
    atr = _finite_positive(candidate.get("atr_15m"))
    if None in (entry, stop, target, price, atr):
        return False, "candidate contains missing or non-finite prices"
    if abs(entry - price) / price > 1e-9:
        return False, "candidate entry does not match the latest closed 5m price"
    if latest_candle is not None and candidate.get("signal_candle") != latest_candle:
        return False, "candidate is stale"
    if direction == "LONG" and not stop < entry < target:
        return False, "LONG levels must satisfy SL < entry < TP"
    if direction == "SHORT" and not target < entry < stop:
        return False, "SHORT levels must satisfy TP < entry < SL"
    risk = entry - stop if direction == "LONG" else stop - entry
    reward = target - entry if direction == "LONG" else entry - target
    if risk <= 0 or reward / risk < MIN_REWARD_RISK:
        return False, "candidate fails the minimum 2R gate"
    try:
        reported_rr = float(candidate.get("rr"))
    except (TypeError, ValueError, OverflowError):
        return False, "candidate R:R is missing or invalid"
    calculated_rr = reward / risk
    if not math.isfinite(reported_rr) or abs(reported_rr - calculated_rr) > max(0.02, calculated_rr * 0.02):
        return False, "reported R:R does not match the entry/stop/target levels"
    stop_atr = risk / atr
    if not math.isfinite(stop_atr) or not 0.35 <= stop_atr <= 2.5:
        return False, "stop distance is outside the 0.35–2.5 ATR safety band"
    score = candidate.get("quality_score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        return False, "quality score must be an integer from 0 to 100"
    if score < MIN_QUALITY_SCORE:
        return False, "candidate is below the 75-point quality gate"
    if not candidate.get("strategy_id") or not candidate.get("rationale"):
        return False, "candidate is missing its strategy identity or rationale"
    return True, "validated"


def select_candidate(candidates, current_price, latest_candle=None,
                     has_open_position=False, approved_strategy_ids=None):
    """Return one winner, a research-only preview, or NO_TRADE.

    Incompatible opposite-side candidates with near-equal scores cause NO_TRADE.
    Unapproved strategies can be recorded for shadow research but never reach Discord.
    """
    approved = APPROVED_STRATEGIES if approved_strategy_ids is None else frozenset(approved_strategy_ids)
    valid = []
    rejected = []
    for candidate in candidates or []:
        ok, reason = validate_candidate(candidate, current_price, latest_candle)
        if ok:
            valid.append(candidate)
        else:
            rejected.append({"strategy_id": candidate.get("strategy_id") if isinstance(candidate, dict) else None,
                             "reason": reason})
    valid.sort(key=lambda item: (-item["quality_score"], item["strategy_id"], item["direction"]))
    if has_open_position:
        return {"status": "NO_TRADE", "selected": None, "preview": None,
                "reason": "an open paper position already exists", "rejected": rejected}
    if not valid:
        return {"status": "NO_TRADE", "selected": None, "preview": None,
                "reason": "no candidate passed mechanical validation", "rejected": rejected}

    best = valid[0]
    opposing = [item for item in valid[1:] if item["direction"] != best["direction"]]
    if opposing and best["quality_score"] - opposing[0]["quality_score"] < OPPOSING_SIGNAL_TIE_MARGIN:
        return {"status": "NO_TRADE", "selected": None, "preview": None,
                "reason": "conflicting long/short candidates have no clear quality-score separation",
                "rejected": rejected}

    if best["strategy_id"] not in approved:
        return {"status": "RESEARCH_ONLY", "selected": None, "preview": best,
                "reason": "candidate passed mechanical checks but its strategy is not OOS/walk-forward approved",
                "rejected": rejected}
    return {"status": "SELECTED", "selected": best, "preview": best,
            "reason": "highest-ranked approved candidate passed all mechanical gates",
            "rejected": rejected}
