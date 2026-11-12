#!/usr/bin/env python3
"""Reconcile Delta OI historical candle values against live ticker OI fields.

Public read-only audit. It places no orders and does not access account data.
Historical candle timestamps are treated as interval opens; this assumption is
reported explicitly because the public candle schema does not define OI units.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.india.delta.exchange"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "SaltyQuantOISemanticsAudit/1.0",
}
INTERVALS = {"5m": 300, "1h": 3600}
MATCH_TOLERANCE_PCT = 5.0
MAX_TICKER_AGE_SECONDS = 900

ANOMALY_WINDOWS = [
    {"label": "2025-12-21_09UTC", "start": 1766307600, "end": 1766314800},
    {"label": "2026-08-19_15UTC", "start": 1787151600, "end": 1787158800},
    {"label": "2026-10-29_14UTC", "start": 1793282400, "end": 1793289600},
    {"label": "2026-11-08_21UTC", "start": 1794171600, "end": 1794178800},
]


class AuditError(RuntimeError):
    pass


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def numeric(value: Any, label: str, *, positive: bool = True) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise AuditError(f"{label}: not numeric") from exc
    if not math.isfinite(out) or (positive and out <= 0):
        raise AuditError(f"{label}: invalid value {value!r}")
    return out


def normalize_epoch_timestamp(value: Any) -> tuple[float, str]:
    """Normalize Delta ticker timestamps; current payloads may use microseconds."""
    raw = numeric(value, "ticker.timestamp")
    if raw >= 10**14:
        return raw / 1_000_000.0, "microseconds"
    if raw >= 10**11:
        return raw / 1_000.0, "milliseconds"
    return raw, "seconds"


def product_conversion_check(ticker: dict, product: dict) -> dict:
    """Check whether ticker oi multiplied by contract_value explains oi_value."""
    try:
        oi = numeric(ticker.get("oi"), "ticker.oi")
        oi_value = numeric(ticker.get("oi_value"), "ticker.oi_value")
        contract_value = numeric(product.get("contract_value"), "product.contract_value")
    except AuditError:
        return {"status": "unavailable"}
    product_unit = product.get("contract_unit_currency")
    value_unit = ticker.get("oi_value_symbol")
    units_match = bool(product_unit and value_unit and str(product_unit).upper() == str(value_unit).upper())
    if not units_match:
        return {
            "status": "unit_mismatch_or_unknown",
            "contract_value": contract_value,
            "contract_unit_currency": product_unit,
            "oi_value_symbol": value_unit,
        }
    implied_base = oi * contract_value
    ratio = implied_base / oi_value
    return {
        "status": "checked",
        "contract_value": contract_value,
        "contract_unit_currency": product_unit,
        "oi_value_symbol": value_unit,
        "units_match": True,
        "implied_base_from_ticker_oi": implied_base,
        "ticker_oi_value_base": oi_value,
        "implied_base_to_oi_value_ratio": ratio,
        "within_5pct": abs(ratio - 1.0) <= MATCH_TOLERANCE_PCT / 100.0,
        "implied_contract_count_from_oi_value": oi_value / contract_value,
        "ticker_oi_to_implied_contract_count_ratio": oi / (oi_value / contract_value),
    }


def ticker_value_diagnostics(ticker: dict) -> dict:
    """Check whether oi duplicates oi_value and whether USD conversion implies mark."""
    out = {}
    try:
        oi = numeric(ticker.get("oi"), "ticker.oi")
        base = numeric(ticker.get("oi_value"), "ticker.oi_value")
        ratio = oi / base
        out["oi_vs_oi_value_relative_difference_pct"] = (ratio - 1.0) * 100.0
        out["oi_and_oi_value_numerically_identical"] = abs(ratio - 1.0) <= 1e-9
    except AuditError:
        out["oi_and_oi_value_numerically_identical"] = None
    try:
        base = numeric(ticker.get("oi_value"), "ticker.oi_value")
        usd = numeric(ticker.get("oi_value_usd"), "ticker.oi_value_usd")
        mark = numeric(ticker.get("mark_price"), "ticker.mark_price")
        implied_price = usd / base
        ratio = implied_price / mark
        out["oi_usd_conversion_implied_price"] = implied_price
        out["mark_price"] = mark
        out["usd_conversion_vs_mark_difference_pct"] = (ratio - 1.0) * 100.0
    except AuditError:
        out["oi_usd_conversion_implied_price"] = None
    return out


def classify_oi_scale_match(
    matches: dict, fresh: bool, ticker_diagnostics: dict, product_conversion: dict
) -> tuple[str, list[str], str]:
    strong = [
        field for field, by_tf in matches.items()
        if fresh and by_tf["5m"] and by_tf["1h"]
    ]
    provisional = [
        field for field, by_tf in matches.items()
        if fresh and (by_tf["5m"] or by_tf["1h"])
    ]
    fields_identical = ticker_diagnostics.get("oi_and_oi_value_numerically_identical") is True
    conversion_checked = product_conversion.get("status") == "checked"
    conversion_matches = product_conversion.get("within_5pct") is True

    if (
        strong and fields_identical and conversion_checked
        and product_conversion.get("units_match") is True and not conversion_matches
        and "oi_value_base" in strong
    ):
        return (
            "strong_base_asset_match_ticker_oi_contract_count_semantics_conflict",
            ["oi_value_base"],
            "Historical OI candles match base-asset oi_value in both resolutions. "
            "Ticker oi is numerically identical to oi_value, but multiplying oi by "
            "the product contract_value does not reproduce oi_value. Do not treat "
            "ticker oi as a raw contract count despite the generic docs label."
        )
    if strong and conversion_matches:
        return (
            "strong_contract_count_to_base_value_match",
            strong,
            "The product contract_value conversion reconciles ticker contract count "
            "to base-asset oi_value, and the historical OI candles match in both resolutions."
        )
    if strong and fields_identical:
        return (
            "strong_scale_match_but_oi_field_identity_ambiguous",
            strong,
            "The OI candles match both resolutions, but ticker oi and oi_value are "
            "numerically identical in this snapshot and product conversion did not resolve them."
        )
    if strong:
        return (
            "strong_same_scale_match",
            strong,
            "Historical OI closes match the named ticker field(s) within 5% in both completed resolutions."
        )
    if provisional:
        return (
            "provisional_single_resolution_match",
            provisional,
            "Only one completed resolution matches the fresh ticker; treat the mapping as provisional."
        )
    return (
        "unresolved_no_fresh_scale_match",
        [],
        "No fresh ticker field matches the completed OI candles within tolerance. Quarantine raw OI changes."
    )


def get_payload(session: requests.Session, path: str, params: dict | None = None) -> tuple[Any, dict]:
    response = session.get(
        f"{BASE_URL}{path}",
        params=params,
        headers=HEADERS,
        timeout=(5, 25),
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise AuditError(f"{path}: response was not JSON") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise AuditError(f"{path}: unsuccessful API payload")
    server_date = response.headers.get("Date")
    server_time = None
    if server_date:
        try:
            server_time = parsedate_to_datetime(server_date).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            server_time = None
    return payload.get("result"), {
        "http_status": response.status_code,
        "server_date_header_utc": server_time,
        "payload_sha256": canonical_sha256(payload),
    }


def parse_candles(records: Any, symbol: str, resolution: str) -> list[dict]:
    if not isinstance(records, list):
        raise AuditError(f"{symbol} {resolution}: result is not a list")
    rows = []
    seen = set()
    for item in records:
        if not isinstance(item, dict):
            raise AuditError(f"{symbol} {resolution}: malformed candle")
        try:
            ts_raw = float(item["time"])
            if not math.isfinite(ts_raw) or ts_raw != math.floor(ts_raw):
                raise ValueError
            ts = int(ts_raw)
            if ts > 10**12:
                raise ValueError
            o = numeric(item["open"], "candle open")
            h = numeric(item["high"], "candle high")
            l = numeric(item["low"], "candle low")
            c = numeric(item["close"], "candle close")
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditError(f"{symbol} {resolution}: invalid OHLC candle") from exc
        if ts in seen:
            raise AuditError(f"{symbol} {resolution}: duplicate timestamp {ts}")
        seen.add(ts)
        if h < max(o, c, l) or l > min(o, c, h):
            raise AuditError(f"{symbol} {resolution}: invalid OHLC bounds at {ts}")
        rows.append({"time": ts, "open": o, "high": h, "low": l, "close": c})
    return sorted(rows, key=lambda row: row["time"])


def latest_completed(rows: list[dict], interval_seconds: int, asof_epoch: float) -> dict | None:
    complete = [
        row for row in rows
        if row["time"] + interval_seconds <= asof_epoch
    ]
    return complete[-1] if complete else None


def cadence_stats(rows: list[dict], interval_seconds: int) -> dict:
    times = [row["time"] for row in rows]
    deltas = [b - a for a, b in zip(times, times[1:])]
    gaps = [delta for delta in deltas if delta > interval_seconds * 1.5]
    irregular = [delta for delta in deltas if delta != interval_seconds]
    return {
        "rows": len(rows),
        "first_open_utc": datetime.fromtimestamp(times[0], timezone.utc).isoformat() if times else None,
        "last_open_utc": datetime.fromtimestamp(times[-1], timezone.utc).isoformat() if times else None,
        "gap_count": len(gaps),
        "largest_gap_seconds": max(gaps) if gaps else 0,
        "irregular_interval_count": len(irregular),
    }


def value_comparison(candle_close: float, ticker: dict) -> dict:
    fields = {
        "oi_contract_count": ticker.get("oi"),
        "oi_value_base": ticker.get("oi_value"),
        "oi_value_usd": ticker.get("oi_value_usd"),
    }
    result = {}
    for name, raw in fields.items():
        if raw is None:
            result[name] = None
            continue
        try:
            field_value = numeric(raw, f"ticker.{name}")
        except AuditError:
            result[name] = None
            continue
        ratio = candle_close / field_value
        result[name] = {
            "ticker_value": field_value,
            "candle_to_ticker_ratio": ratio,
            "relative_difference_pct": (ratio - 1.0) * 100.0,
            "within_5pct": abs(ratio - 1.0) <= MATCH_TOLERANCE_PCT / 100.0,
        }
    return result


def cross_resolution_check(
    hourly: list[dict], five_minute: list[dict], asof_epoch: float
) -> dict:
    five_by_open = {row["time"]: row for row in five_minute}
    comparisons = []
    for hour in hourly:
        hour_end = hour["time"] + 3600
        if hour_end > asof_epoch:
            continue
        last_five_open = hour_end - 300
        five = five_by_open.get(last_five_open)
        if five is None:
            continue
        ratio = five["close"] / hour["close"]
        comparisons.append({
            "hour_open_utc": datetime.fromtimestamp(hour["time"], timezone.utc).isoformat(),
            "hourly_close": hour["close"],
            "last_5m_close": five["close"],
            "relative_difference_pct": (ratio - 1.0) * 100.0,
            "within_1pct": abs(ratio - 1.0) <= 0.01,
        })
    diffs = [abs(row["relative_difference_pct"]) for row in comparisons]
    return {
        "matched_hours": len(comparisons),
        "within_1pct": sum(row["within_1pct"] for row in comparisons),
        "median_abs_difference_pct": sorted(diffs)[len(diffs)//2] if diffs else None,
        "comparisons": comparisons[-12:],
    }


def compare_hourly_to_5m(hourly: list[dict], five_minute: list[dict]) -> dict:
    five_by_open = {row["time"]: row for row in five_minute}
    comparisons = []
    for hour in hourly:
        hour_end = hour["time"] + 3600
        bars = [
            five_by_open[t]
            for t in range(hour["time"], hour_end, 300)
            if t in five_by_open
        ]
        if len(bars) != 12:
            comparisons.append({
                "hour_open_utc": datetime.fromtimestamp(hour["time"], timezone.utc).isoformat(),
                "five_minute_bars": len(bars),
                "complete_12_bars": False,
                "ohlc_match_within_0_1pct": False,
            })
            continue
        aggregate = {
            "open": bars[0]["open"],
            "high": max(row["high"] for row in bars),
            "low": min(row["low"] for row in bars),
            "close": bars[-1]["close"],
        }
        diffs = {
            key: (aggregate[key] / hour[key] - 1.0) * 100.0
            for key in ("open", "high", "low", "close")
        }
        close_moves = [
            (bars[i]["close"] / bars[i-1]["close"] - 1.0) * 100.0
            for i in range(1, len(bars))
        ]
        comparisons.append({
            "hour_open_utc": datetime.fromtimestamp(hour["time"], timezone.utc).isoformat(),
            "five_minute_bars": len(bars),
            "complete_12_bars": True,
            "hourly_ohlc": {key: hour[key] for key in ("open", "high", "low", "close")},
            "aggregated_5m_ohlc": aggregate,
            "relative_difference_pct": diffs,
            "ohlc_match_within_0_1pct": all(abs(value) <= 0.1 for value in diffs.values()),
            "max_abs_5m_close_change_pct": max((abs(value) for value in close_moves), default=0.0),
        })
    complete = [row for row in comparisons if row.get("complete_12_bars")]
    return {
        "hourly_candles": len(hourly),
        "complete_5m_groups": len(complete),
        "ohlc_matches_within_0_1pct": sum(row.get("ohlc_match_within_0_1pct", False) for row in complete),
        "comparisons": comparisons,
    }


def fetch_anomaly_windows(session: requests.Session, symbol: str) -> list[dict]:
    reports = []
    for window in ANOMALY_WINDOWS:
        item = {"label": window["label"], "start": window["start"], "end": window["end"]}
        try:
            hourly_raw, hourly_meta = get_payload(
                session,
                "/v2/history/candles",
                {
                    "resolution": "1h",
                    "symbol": f"OI:{symbol}",
                    "start": str(window["start"]),
                    "end": str(window["end"]),
                },
            )
            five_raw, five_meta = get_payload(
                session,
                "/v2/history/candles",
                {
                    "resolution": "5m",
                    "symbol": f"OI:{symbol}",
                    "start": str(window["start"]),
                    "end": str(window["end"]),
                },
            )
            hourly = parse_candles(hourly_raw, symbol, "1h")
            five = parse_candles(five_raw, symbol, "5m")
            item.update({
                "status": "ok" if hourly and five else "missing_historical_rows",
                "hourly_request_sha256": hourly_meta["payload_sha256"],
                "five_minute_request_sha256": five_meta["payload_sha256"],
                "five_minute_rows": len(five),
                "aggregation_check": compare_hourly_to_5m(hourly, five),
            })
        except Exception as exc:
            item.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        reports.append(item)
    return reports


def fetch_symbol(session: requests.Session, symbol: str) -> dict:
    ticker_result, ticker_meta = get_payload(session, f"/v2/tickers/{symbol}")
    if not isinstance(ticker_result, dict):
        raise AuditError(f"{symbol}: ticker result is not an object")
    if ticker_result.get("symbol") not in (None, symbol):
        raise AuditError(f"{symbol}: ticker symbol mismatch")
    ticker_oi = numeric(ticker_result.get("oi"), f"{symbol}.ticker.oi")
    ticker_ts_raw = numeric(ticker_result.get("timestamp"), f"{symbol}.ticker.timestamp")
    ticker_ts, ticker_timestamp_unit = normalize_epoch_timestamp(ticker_ts_raw)
    server_date = ticker_meta.get("server_date_header_utc")
    asof_epoch = (
        datetime.fromisoformat(server_date.replace("Z", "+00:00")).timestamp()
        if server_date else time.time()
    )
    ticker_age = asof_epoch - ticker_ts

    product_result, product_meta = get_payload(session, f"/v2/products/{symbol}")
    if not isinstance(product_result, dict):
        raise AuditError(f"{symbol}: product result is not an object")
    product_info = {
        "id": product_result.get("id"),
        "symbol": product_result.get("symbol"),
        "description": product_result.get("description"),
        "contract_type": product_result.get("contract_type"),
        "notional_type": product_result.get("notional_type"),
        "contract_value": product_result.get("contract_value"),
        "contract_unit_currency": product_result.get("contract_unit_currency"),
        "quoting_asset": product_result.get("quoting_asset"),
        "underlying_asset": product_result.get("underlying_asset"),
        "settling_asset": product_result.get("settling_asset"),
    }
    product_conversion = product_conversion_check(ticker_result, product_result)
    ticker_diagnostics = ticker_value_diagnostics(ticker_result)

    histories = {}
    history_meta = {}
    for resolution, interval in INTERVALS.items():
        lookback = 12 * 3600 if resolution == "5m" else 48 * 3600
        end_epoch = int(asof_epoch)
        start_epoch = int((asof_epoch // interval) * interval - lookback)
        records, meta = get_payload(
            session,
            "/v2/history/candles",
            {
                "resolution": resolution,
                "symbol": f"OI:{symbol}",
                "start": str(start_epoch),
                "end": str(end_epoch),
            },
        )
        rows = parse_candles(records, symbol, resolution)
        histories[resolution] = rows
        history_meta[resolution] = {
            **meta,
            "api_symbol": f"OI:{symbol}",
            "resolution": resolution,
            "requested_start_utc": datetime.fromtimestamp(start_epoch, timezone.utc).isoformat(),
            "requested_end_utc": datetime.fromtimestamp(end_epoch, timezone.utc).isoformat(),
            **cadence_stats(rows, interval),
        }

    selected = {}
    for resolution, interval in INTERVALS.items():
        row = latest_completed(histories[resolution], interval, asof_epoch)
        if row is None:
            selected[resolution] = {"status": "no_completed_candle", "comparison": None}
            continue
        close_time = row["time"] + interval
        candle_age = asof_epoch - close_time
        comparison = value_comparison(row["close"], ticker_result)
        selected[resolution] = {
            "status": "ok",
            "candle_open_utc": datetime.fromtimestamp(row["time"], timezone.utc).isoformat(),
            "candle_close_available_utc": datetime.fromtimestamp(close_time, timezone.utc).isoformat(),
            "candle_age_seconds_at_ticker_snapshot": candle_age,
            "candle_close": row["close"],
            "comparison": comparison,
        }

    cross = cross_resolution_check(histories["1h"], histories["5m"], asof_epoch)
    fresh = -30.0 <= ticker_age <= MAX_TICKER_AGE_SECONDS
    field_names = ("oi_contract_count", "oi_value_base", "oi_value_usd")
    matches = {}
    for field in field_names:
        matches[field] = {
            resolution: bool(
                selected[resolution].get("status") == "ok"
                and selected[resolution]["comparison"].get(field)
                and selected[resolution]["comparison"][field]["within_5pct"]
            )
            for resolution in INTERVALS
        }
    classification, likely_field, interpretation = classify_oi_scale_match(
        matches, fresh, ticker_diagnostics, product_conversion
    )
    anomaly_drilldown = fetch_anomaly_windows(session, symbol)

    return {
        "symbol": symbol,
        "ticker_received_at_utc": datetime.fromtimestamp(asof_epoch, timezone.utc).isoformat(),
        "ticker_timestamp_raw": ticker_ts_raw,
        "ticker_timestamp_unit_inferred": ticker_timestamp_unit,
        "ticker_timestamp_utc": datetime.fromtimestamp(ticker_ts, timezone.utc).isoformat(),
        "ticker_age_seconds": ticker_age,
        "ticker_fresh_within_15m": fresh,
        "ticker": {
            "symbol": ticker_result.get("symbol"),
            "timestamp_raw": ticker_ts_raw,
            "oi": ticker_oi,
            "oi_value": ticker_result.get("oi_value"),
            "oi_value_symbol": ticker_result.get("oi_value_symbol"),
            "oi_value_usd": ticker_result.get("oi_value_usd"),
            "mark_price": ticker_result.get("mark_price"),
            "close": ticker_result.get("close"),
        },
        "ticker_value_diagnostics": ticker_diagnostics,
        "product": product_info,
        "product_request": product_meta,
        "product_conversion_check": product_conversion,
        "ticker_request": ticker_meta,
        "history_requests": history_meta,
        "latest_completed_candles": selected,
        "cross_resolution_1h_vs_5m": cross,
        "scale_match_by_field": matches,
        "classification": classification,
        "candidate_ticker_field": likely_field,
        "anomaly_window_drilldown": anomaly_drilldown,
        "interpretation": interpretation,
    }


def write_outputs(output_dir: Path, symbols: list[str]) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    reports = []
    errors = []
    try:
        for symbol in symbols:
            try:
                reports.append(fetch_symbol(session, symbol))
            except Exception as exc:
                errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        session.close()

    result = {
        "study": "Delta OI historical-candle versus live-ticker semantics reconciliation",
        "classification": "public read-only data audit; not a trading strategy or backtest",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "venue": "Delta Exchange India",
        "base_url": BASE_URL,
        "timestamp_assumption": (
            "Historical candle time is treated as interval open; a candle is complete "
            "only when time + resolution <= ticker-receipt time."
        ),
        "match_tolerance_pct": MATCH_TOLERANCE_PCT,
        "ticker_freshness_limit_seconds": MAX_TICKER_AGE_SECONDS,
        "symbols": reports,
        "errors": errors,
        "limitations": [
            "Official docs define ticker oi as outstanding contract count, oi_value as base-currency value, and oi_value_usd as USD-converted value.",
            "Official historical-candle docs identify OI-prefixed symbols but do not define the OI candle economic unit or sampling convention.",
            "A one-time live snapshot can only establish scale compatibility, not prove the full historical series semantics.",
            "Cross-resolution equality is diagnostic; a 5m and 1h series may be sampled or aggregated differently.",
            "No account data, credentials, orders, or execution alerts are used.",
        ],
    }
    json_path = output_dir / "reconciliation.json"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Delta OI semantics reconciliation",
        "",
        f"- Audit time: {result['created_at_utc']}",
        "- Scope: BTCUSD and ETHUSD; public ticker plus completed 5m/1h OI candles.",
        "- This is a data-semantics audit, not a strategy result.",
        "",
        "| Contract | Classification | Candidate ticker field | Ticker age | 5m vs base OI | 1h vs base OI | Contract conversion | 1h/5m matched hours |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for item in reports:
        def fmt(res):
            row = item["latest_completed_candles"].get(res, {})
            comp = row.get("comparison") or {}
            val = comp.get("oi_value_base")
            return f"{val['relative_difference_pct']:+.3f}%" if val else "n/a"
        candidate = ", ".join(item["candidate_ticker_field"]) or "unresolved"
        cross = item["cross_resolution_1h_vs_5m"]
        lines.append(
            f"| {item['symbol']} | {item['classification']} | {candidate} | "
            f"{item['ticker_age_seconds']:.1f}s | {fmt('5m')} | {fmt('1h')} | "
            f"{item['product_conversion_check'].get('within_5pct', 'n/a')} | {cross['matched_hours']} |"
        )
    if errors:
        lines += ["", "## Errors", ""]
        lines += [f"- {e['symbol']}: {e['error']}" for e in errors]
    lines += [
        "",
        "## Interpretation rules",
        "",
        "- A strong scale match requires a fresh ticker (age from the HTTP Date header to the normalized ticker timestamp) and both completed 5m/1h OI closes within 5% of the same ticker field. Timestamp units are inferred as seconds, milliseconds or microseconds.",
        "- A single-resolution match is provisional only.",
        "- If ticker oi and oi_value are numerically identical, a one-snapshot match cannot distinguish contract count from base-asset value. Use product contract_value × contract count and contract_unit_currency to test the conversion. A match does not establish that all historical jumps are genuine; repeated snapshots and independent unit reconciliation are still required.",
        "- If unresolved, quarantine raw OI percentage-change signals. Do not tune or backtest another OI strategy from the ambiguous series.",
        "",
        "## Official documentation",
        "",
        "- Delta ticker endpoint and ticker field definitions: https://docs.delta.exchange/",
        "- Delta historical candles API, OI-prefixed symbols: https://docs.delta.exchange/",
    ]
    md_path = output_dir / "summary.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    rows = [
        {"time": 0, "open": 10, "high": 11, "low": 9, "close": 10.5},
        {"time": 300, "open": 10.5, "high": 11, "low": 10, "close": 10.8},
        {"time": 600, "open": 10.8, "high": 11, "low": 10.5, "close": 10.9},
        {"time": 900, "open": 10.9, "high": 11.2, "low": 10.8, "close": 11.1},
        {"time": 1200, "open": 11.1, "high": 11.3, "low": 11, "close": 11.2},
    ]
    parsed = parse_candles(rows, "BTCUSD", "5m")
    assert latest_completed(parsed, 300, 1200)["time"] == 900
    assert latest_completed(parsed, 300, 1199)["time"] == 600

    seconds, unit = normalize_epoch_timestamp(1794470534)
    assert seconds == 1794470534 and unit == "seconds"
    milliseconds, unit = normalize_epoch_timestamp(1794470534338)
    assert abs(milliseconds - 1794470534.338) < 1e-6 and unit == "milliseconds"
    microseconds, unit = normalize_epoch_timestamp(1794470534338862)
    assert abs(microseconds - 1794470534.338862) < 1e-6 and unit == "microseconds"

    ticker = {"oi": "11.1", "oi_value": "10.9", "oi_value_usd": "700"}
    comparison = value_comparison(11.1, ticker)
    assert comparison["oi_contract_count"]["within_5pct"]
    assert comparison["oi_value_base"]["within_5pct"]
    assert not comparison["oi_value_usd"]["within_5pct"]

    matching_ticker = {
        "oi": "1000", "oi_value": "1", "oi_value_symbol": "BTC",
        "oi_value_usd": "2000", "mark_price": "2000",
    }
    matching_product = {"contract_value": "0.001", "contract_unit_currency": "BTC"}
    conversion = product_conversion_check(matching_ticker, matching_product)
    assert conversion["status"] == "checked" and conversion["within_5pct"]
    diagnostics = ticker_value_diagnostics({
        "oi": "1", "oi_value": "1", "oi_value_usd": "2000", "mark_price": "2000"
    })
    assert diagnostics["oi_and_oi_value_numerically_identical"]
    assert abs(diagnostics["usd_conversion_vs_mark_difference_pct"]) < 1e-9

    hourly = [{"time": 0, "open": 10, "high": 11, "low": 9, "close": 10.8}]
    five = [
        {"time": 0, "open": 10, "high": 10.5, "low": 9.5, "close": 10.1},
        {"time": 300, "open": 10.1, "high": 10.5, "low": 10, "close": 10.2},
        {"time": 3300, "open": 10.2, "high": 10.9, "low": 10.1, "close": 10.8},
    ]
    cross = cross_resolution_check(hourly, five, 3600)
    assert cross["matched_hours"] == 1 and cross["within_1pct"] == 1
    stats = cadence_stats(parsed, 300)
    assert stats["rows"] == 5 and stats["gap_count"] == 0
    print("10 OI semantics reconciliation self-tests passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--symbols", default="BTCUSD,ETHUSD")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.output_dir:
        parser.error("--output-dir is required unless --self-test is used")
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    if not symbols or any(symbol not in {"BTCUSD", "ETHUSD"} for symbol in symbols):
        parser.error("symbols must be a comma-separated subset of BTCUSD,ETHUSD")
    result = write_outputs(args.output_dir, symbols)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
