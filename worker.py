"""Always-on five-minute scheduler for a single persistent quant-desk worker."""
import json
import os
import signal
import threading
import time
from pathlib import Path

import pandas as pd

import dns_worker


INTERVAL_SECONDS = max(60, int(os.environ.get("WORKER_INTERVAL_SECONDS", "300")))
STOP = threading.Event()


def seconds_until_next_tick(epoch_seconds, interval_seconds=INTERVAL_SECONDS):
    """Align to wall-clock interval boundaries rather than drifting after each run."""
    remainder = float(epoch_seconds) % interval_seconds
    return interval_seconds - remainder if remainder > 1e-9 else float(interval_seconds)


def _handle_stop(signum, frame):
    print(f"[worker] received signal {signum}; stopping after the current cycle", flush=True)
    STOP.set()


def _heartbeat(status, detail=None):
    path = Path(os.environ.get("HEARTBEAT_PATH", "/data/worker_heartbeat.json"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "status": status,
            "interval_seconds": INTERVAL_SECONDS,
            "detail": str(detail)[:500] if detail else None
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[worker] heartbeat write failed: {exc}", flush=True)


def _check_required_environment():
    missing = []
    if not (os.environ.get("DISCORD_TRIGGER_WEBHOOK") or os.environ.get("DISCORD_WEBHOOK")):
        missing.append("DISCORD_TRIGGER_WEBHOOK (or DISCORD_WEBHOOK)")
    if missing:
        raise RuntimeError("Missing required environment settings: " + ", ".join(missing))
    if not os.environ.get("OPENAI_API_KEY"):
        print("[worker] WARNING: OPENAI_API_KEY is absent; local DNS monitoring continues, map refreshes are paused", flush=True)


def _check_optional_delta_auth():
    """Check a configured Delta read-only key once at worker startup; never place orders."""
    api_key = os.environ.get("DELTA_API_KEY", "").strip()
    api_secret = os.environ.get("DELTA_API_SECRET", "").strip()
    if not api_key and not api_secret:
        print("[worker] Delta API key not configured; public candle data remains enabled", flush=True)
        return
    if not api_key or not api_secret:
        print("[worker] WARNING: both DELTA_API_KEY and DELTA_API_SECRET are required; skipping authenticated check", flush=True)
        return
    try:
        from delta_auth import DeltaReadOnlyClient
        DeltaReadOnlyClient.from_env().get_trading_preferences()
        print("[worker] Delta authenticated read-only connection passed", flush=True)
    except Exception as exc:
        # Public historical OHLCV remains available without authentication.
        print(f"[worker] WARNING: Delta authenticated read-only check failed: {exc}", flush=True)


def run_forever():
    _check_required_environment()
    _check_optional_delta_auth()
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    print(
        f"[worker] Salty Quant AI DNS local-monitoring desk starting; interval={INTERVAL_SECONDS}s; "
        f"model={os.environ.get('OPENAI_MODEL', 'gpt-6-luna')}; single worker only",
        flush=True
    )
    _heartbeat("starting")

    # Run immediately at boot; subsequent cycles align to the next five-minute boundary.
    while not STOP.is_set():
        try:
            dns_worker.run()
            _heartbeat("ok")
            print("[worker] analysis cycle completed", flush=True)
        except Exception as exc:
            _heartbeat("error", exc)
            print(f"[worker] analysis cycle failed; will retry next interval: {exc}", flush=True)

        if STOP.is_set():
            break

        delay = seconds_until_next_tick(time.time())
        print(f"[worker] next cycle in {delay:.1f}s", flush=True)
        STOP.wait(delay)

    _heartbeat("stopped")
    print("[worker] stopped cleanly", flush=True)


if __name__ == "__main__":
    run_forever()
