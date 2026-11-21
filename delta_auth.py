"""Read-only authenticated client for Delta Exchange India.

This module intentionally exposes only GET operations. It contains no order,
position mutation, wallet transfer, or other write methods.
"""
import hashlib
import hmac
import os
import time
from urllib.parse import urlsplit

import requests


DEFAULT_BASE_URL = "https://api.india.delta.exchange"
USER_AGENT = "SaltyQuantAI/1.0"


class DeltaAuthError(RuntimeError):
    """Safe, redacted Delta authentication or API error."""


def sign_message(secret: str, message: str) -> str:
    """Return Delta's hex HMAC-SHA256 signature for the exact prehash string."""
    if not secret:
        raise ValueError("Delta API secret is required")
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class DeltaReadOnlyClient:
    """Minimal authenticated GET client for Delta Exchange India."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 15.0,
        session=None,
        clock=None,
    ):
        if not api_key or not api_secret:
            raise ValueError("Both DELTA_API_KEY and DELTA_API_SECRET are required")
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        if not self.api_key or not self.api_secret:
            raise ValueError("Delta API credentials cannot be blank")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.clock = clock or time.time

    @classmethod
    def from_env(cls):
        return cls(
            api_key=os.environ.get("DELTA_API_KEY", ""),
            api_secret=os.environ.get("DELTA_API_SECRET", ""),
            base_url=os.environ.get("DELTA_API_BASE_URL", DEFAULT_BASE_URL),
        )

    def _signed_get(self, path: str, params=None):
        if path != "/v2/users/trading_preferences":
            raise ValueError("This read-only client only permits GET /v2/users/trading_preferences")

        request = requests.Request(
            method="GET",
            url=f"{self.base_url}{path}",
            params=params or None,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        prepared = self.session.prepare_request(request)
        parsed = urlsplit(prepared.url)
        query_string = f"?{parsed.query}" if parsed.query else ""
        payload = prepared.body or ""
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        timestamp = str(int(self.clock()))
        prehash = "GET" + timestamp + parsed.path + query_string + payload
        signature = sign_message(self.api_secret, prehash)
        prepared.headers.update({
            "api-key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "Content-Type": "application/json",
        })

        try:
            response = self.session.send(prepared, timeout=self.timeout)
        except requests.RequestException as exc:
            raise DeltaAuthError(
                f"Delta request could not reach the API ({type(exc).__name__}). "
                "Check network access and the configured API host."
            ) from None

        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.status_code in (401, 403):
            raw_error = body.get("error") if isinstance(body, dict) else ""
            error = raw_error if isinstance(raw_error, dict) else {}
            status_text = body.get("status") if isinstance(body, dict) else ""
            error_text = raw_error if isinstance(raw_error, str) else ""
            code = str(error.get("code") or status_text or error_text or "").lower()
            if "ip" in code or "whitelist" in code:
                advice = "The request IP is not on this API key's whitelist."
            elif "signature" in code:
                advice = "Delta rejected the signature; verify the API secret and system clock."
            elif "invalid_api_key" in code or "api_key_not_found" in code:
                advice = "Delta did not recognize this API key; verify the key and production environment."
            elif "unauthorized" in code or "permission" in code:
                advice = "The key may not have permission for this read-only account endpoint."
            else:
                advice = "Check the API key, permissions, production host, and IP whitelist."
            raise DeltaAuthError(f"Delta authentication failed (HTTP {response.status_code}). {advice}")

        if not response.ok:
            raise DeltaAuthError(
                f"Delta returned HTTP {response.status_code} for a read-only request."
            )
        if not isinstance(body, dict) or body.get("success") is not True:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
            raise DeltaAuthError(f"Delta returned an unsuccessful response ({code}).")
        return body.get("result")

    def get_trading_preferences(self):
        """Read account preferences only; this endpoint does not modify account state."""
        result = self._signed_get("/v2/users/trading_preferences")
        if not isinstance(result, dict) or result.get("user_id") is None:
            raise DeltaAuthError("Delta responded, but the read-only account response was incomplete.")
        # Return only a success marker; do not persist or log private account preferences.
        return {"authenticated": True}
