"""Always-on five-minute scheduler for a single persistent quant-desk worker."""
import json
import os
import signal
import threading
import time
from pathlib import Path

import pandas as pd

import quant_worker


WORKER_MODE = os.environ.get("WORKER_MODE", "quant").strip().lower()
if WORKER_MODE not in {"quant", "dns", "visual"}:
    raise ValueError("WORKER_MODE must be 'quant', 'dns', or 'visual'")


def _run_cycle():
    """Run the explicitly selected paper lane; visual decisions are model-led."""
    if WORKER_MODE == "visual":
        import visual_worker
        visual_worker.run()
    elif WORKER_MODE == "dns":
        import dns_worker
        dns_worker.run()
    else:
        quant_worker.run()


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
    if not (os.environ.get("DISCORD_TRIGGER_WEBHOOK") or os.environ.get("DISCORD_WEBHOOK")):
        print("[worker] WARNING: Discord webhook absent; paper analysis continues, outbound notifications remain pending/disabled", flush=True)


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
        f"[worker] Salty Quant starting; mode={WORKER_MODE}; interval={INTERVAL_SECONDS}s; "
        + (
            "independent multi-setup chart vision; closed-candle analysis; hard risk gates; paper-only"
            if WORKER_MODE == "visual"
            else (
                "visual DNS maps refresh infrequently; coded local watcher scans every cycle; "
                "optional Bull/Bear/Chief debate runs only after a DNS event; paper-only"
                if WORKER_MODE == "dns"
                else "deterministic multi-strategy research; no AI API calls; OOS promotion required; paper-only"
            )
        ),
        flush=True
    )
    _heartbeat("starting")

    # Run immediately at boot; subsequent cycles align to the next five-minute boundary.
    while not STOP.is_set():
        try:
            _run_cycle()
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
