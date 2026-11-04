"""Small persistent state for duplicate prevention and paper trade lifecycle."""
import json
import os

PATH = os.environ.get("STATE_PATH", "state.json")


def load():
    try:
        with open(PATH, encoding="utf-8") as handle:
            state = json.load(handle)
    except Exception:
        state = {}
    state.setdefault("positions", {})
    state.setdefault("trade_history", [])
    state.setdefault("last_ai_candle", {})
    state.setdefault("last_analysis_at", None)
    state.setdefault("last_market_commentary", "")
    return state


def save(state):
    state["trade_history"] = state.get("trade_history", [])[-2000:]
    with open(PATH, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
