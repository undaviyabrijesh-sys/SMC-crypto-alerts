"""Small persistent state for duplicate prevention and paper trade lifecycle."""
import json
import os
from pathlib import Path

PATH = os.environ.get("STATE_PATH", "state.json")


def load():
    """Load state without silently discarding an unreadable trading history."""
    try:
        with open(PATH, encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        state = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot safely load trading state at {PATH}; refusing to start with empty state"
        ) from exc

    if not isinstance(state, dict):
        raise RuntimeError(
            f"Trading state at {PATH} must contain a JSON object; refusing to reset it"
        )

    state.setdefault("positions", {})
    state.setdefault("pending_alerts", {})
    state.setdefault("pending_outcomes", {})
    state.setdefault("trade_history", [])
    state.setdefault("last_ai_candle", {})
    state.setdefault("last_analysis_at", None)
    state.setdefault("last_market_commentary", "")
    state.setdefault("daily_reports_sent", [])
    state.setdefault("pending_daily_reports", {})
    return state


def save(state):
    """Atomically persist state so an interrupted write cannot truncate the live file."""
    state["trade_history"] = state.get("trade_history", [])[-2000:]
    path = Path(PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
