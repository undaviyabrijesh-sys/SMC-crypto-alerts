"""One-shot authenticated Delta read-only connectivity test.

Run locally or on a deployment host whose public IP is whitelisted by Delta:
    python smoke_delta_auth.py
"""
import os
import sys

from delta_auth import DeltaAuthError, DeltaReadOnlyClient


def main():
    if not os.environ.get("DELTA_API_KEY") or not os.environ.get("DELTA_API_SECRET"):
        print("FAIL: Set DELTA_API_KEY and DELTA_API_SECRET in the private environment.")
        return 2
    try:
        DeltaReadOnlyClient.from_env().get_trading_preferences()
    except DeltaAuthError as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: Delta authenticated read-only API connection succeeded.")
    print("No orders were placed and no account settings were changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
