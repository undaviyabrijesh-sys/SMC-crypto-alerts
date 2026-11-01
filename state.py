import json
import os

PATH = os.environ.get("STATE_PATH", "state.json")


def load():
    try:
        with open(PATH) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("watches", {})
    s.setdefault("rearm", {})
    s.setdefault("seen", [])
    s.setdefault("log", [])
    return s


def save(s):
    s["seen"] = s["seen"][-300:]
    s["log"] = s["log"][-1000:]
    with open(PATH, "w") as f:
        json.dump(s, f, indent=1)
