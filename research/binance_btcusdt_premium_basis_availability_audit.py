#!/usr/bin/env python3
"""BTCUSDT USD-M premium/index-basis archive availability audit. Data audit only."""
from __future__ import annotations
import argparse, csv, hashlib, io, json, math, statistics, time, zipfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

BASE = "https://data.binance.vision"
API = "https://fapi.binance.com"
SYMBOL, INTERVAL, MONTH, DAY = "BTCUSDT", "5m", "2026-10", "2026-11-19"
STEP_MS = 300_000
SERIES = {
    "contract": {"archive": "klines", "endpoint": "/fapi/v1/klines", "param": "symbol"},
    "index": {"archive": "indexPriceKlines", "endpoint": "/fapi/v1/indexPriceKlines", "param": "pair"},
    "mark": {"archive": "markPriceKlines", "endpoint": "/fapi/v1/markPriceKlines", "param": "symbol"},
    "premium": {"archive": "premiumIndexKlines", "endpoint": "/fapi/v1/premiumIndexKlines", "param": "symbol"},
}

def utc_ms(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

def finite_float(value: Any) -> float:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError(f"non-finite numeric value: {value!r}")
    return x

def archive_path(kind: str, period: str, date_key: str) -> str:
    name = f"{SYMBOL}-{INTERVAL}-{date_key}.zip"
    return f"data/futures/um/{period}/{kind}/{SYMBOL}/{INTERVAL}/{name}"

def get_bytes(session: requests.Session, url: str, timeout: int = 60) -> bytes:
    last = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}: {last}")

def download_archive(session: requests.Session, kind: str, period: str, date_key: str):
    rel = archive_path(kind, period, date_key)
    url = f"{BASE}/{rel}"
    checksum_url = url + ".CHECKSUM"
    checksum_text = get_bytes(session, checksum_url).decode("utf-8").strip()
    expected = checksum_text.split()[0].lower()
    payload = get_bytes(session, url)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise AssertionError(f"SHA-256 mismatch for {rel}: expected {expected}, got {actual}")
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise AssertionError(f"ZIP CRC failed for {rel}: {bad}")
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(members) != 1:
            raise AssertionError(f"expected one CSV in {rel}, found {members}")
        raw = zf.read(members[0]).decode("utf-8-sig")
    rows = []
    for line_no, row in enumerate(csv.reader(io.StringIO(raw)), 1):
        if not row:
            continue
        if line_no == 1 and not row[0].strip().isdigit():
            continue
        if len(row) != 12:
            raise AssertionError(f"{rel} line {line_no}: expected 12 columns, got {len(row)}")
        ts, close_time = int(row[0]), int(row[6])
        values = [finite_float(row[i]) for i in range(1, 5)]
        if ts % STEP_MS:
            raise AssertionError(f"{rel} has off-grid open time {ts}")
        if close_time < ts or close_time >= ts + STEP_MS:
            raise AssertionError(f"{rel} has invalid close time at {ts}")
        if kind != "premiumIndexKlines" and values[3] <= 0:
            raise AssertionError(f"{rel} has non-positive close at {ts}")
        rows.append({"open_time": ts, "open": values[0], "high": values[1],
                     "low": values[2], "close": values[3], "close_time": close_time})
    rows.sort(key=lambda x: x["open_time"])
    times = [r["open_time"] for r in rows]
    if len(times) != len(set(times)):
        raise AssertionError(f"{rel} has duplicate open times")
    gaps = sum(1 for a, b in zip(times, times[1:]) if b - a != STEP_MS)
    meta = {"relative_path": rel, "url": url, "checksum_url": checksum_url,
            "sha256": actual, "expected_sha256": expected, "bytes": len(payload),
            "zip_crc": "passed", "csv_member": members[0], "rows": len(rows),
            "first_open_time": times[0] if times else None,
            "last_open_time": times[-1] if times else None, "gap_count": gaps,
            "duplicate_count": 0}
    if not rows:
        raise AssertionError(f"{rel} contained no data rows")
    return rows, meta

def rest_rows(session: requests.Session, kind: str, start_ms: int, end_ms: int):
    spec = SERIES[kind]
    params = {spec["param"]: SYMBOL, "interval": INTERVAL,
              "startTime": start_ms, "endTime": end_ms, "limit": 1500}
    url = API + spec["endpoint"]
    try:
        response = session.get(url, params=params, timeout=30)
        if response.status_code != 200:
            return {"status": "unavailable", "http_status": response.status_code,
                    "url": response.url, "error": response.text[:300]}
        data = response.json()
        if not isinstance(data, list):
            return {"status": "unavailable", "http_status": 200, "url": response.url,
                    "error": "non-list response"}
        parsed = {}
        for row in data:
            if len(row) != 12:
                raise AssertionError(f"REST {kind}: expected 12 fields")
            parsed[int(row[0])] = finite_float(row[4])
        return {"status": "available", "http_status": 200, "url": response.url,
                "rows": len(parsed), "closes": parsed}
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)[:400]}

def basis_endpoint(session: requests.Session):
    url = API + "/futures/data/basis"
    params = {"pair": SYMBOL, "contractType": "PERPETUAL", "period": INTERVAL, "limit": 500}
    try:
        response = session.get(url, params=params, timeout=30)
        if response.status_code != 200:
            return {"status": "unavailable", "http_status": response.status_code,
                    "url": response.url, "error": response.text[:300],
                    "documented_limit": "latest 30 days only"}
        data = response.json()
        if not isinstance(data, list):
            return {"status": "unavailable", "http_status": 200, "error": "non-list response",
                    "documented_limit": "latest 30 days only"}
        residuals, rate_residuals, timestamps = [], [], []
        for row in data:
            futures, index = finite_float(row["futuresPrice"]), finite_float(row["indexPrice"])
            basis, rate = finite_float(row["basis"]), finite_float(row["basisRate"])
            if index <= 0:
                raise AssertionError("basis endpoint returned non-positive index price")
            residuals.append(abs(basis - (futures - index)))
            rate_residuals.append(abs(rate - basis / index))
            timestamps.append(int(row["timestamp"]))
        timestamps.sort()
        gaps = sum(1 for a, b in zip(timestamps, timestamps[1:]) if b - a != STEP_MS)
        return {"status": "available", "http_status": 200, "url": response.url,
                "rows": len(data), "first_timestamp": min(timestamps) if timestamps else None,
                "last_timestamp": max(timestamps) if timestamps else None,
                "timestamp_gap_count": gaps,
                "max_abs_basis_arithmetic_error": max(residuals, default=None),
                "max_abs_basis_rate_error": max(rate_residuals, default=None),
                "arithmetic_pass": bool(data) and max(residuals, default=1) <= 1e-7
                                   and max(rate_residuals, default=1) <= 1e-5,
                "documented_limit": "latest 30 days only"}
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)[:400],
                "documented_limit": "latest 30 days only"}

def quantile(values, q):
    if not values:
        return None
    x = sorted(values)
    pos = (len(x) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return x[lo] if lo == hi else x[lo] * (hi - pos) + x[hi] * (pos - lo)

def correlation(a, b):
    if len(a) != len(b) or len(a) < 3:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    da, db = [x-ma for x in a], [x-mb for x in b]
    den = math.sqrt(sum(x*x for x in da) * sum(x*x for x in db))
    return sum(x*y for x, y in zip(da, db)) / den if den else None

def audit(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "salty-quant-premium-basis-audit/1.0"})
    archives, manifest = {}, {"audit": "BTCUSDT USD-M premium/index-basis availability",
        "research_type": "data_availability_audit", "data_classification": "market_data_quality",
        "validation_state": "not_applicable", "oos_evaluated": False,
        "decision": "data_availability_audit_only", "symbol": SYMBOL, "interval": INTERVAL, "monthly_period": MONTH,
        "daily_period": DAY, "series": {}, "rest_checks": {}}
    for kind in SERIES:
        archives[kind], manifest["series"][kind] = {}, {}
        for period, key in (("monthly", MONTH), ("daily", DAY)):
            rows, meta = download_archive(session, SERIES[kind]["archive"], period, key)
            archives[kind][period], manifest["series"][kind][period] = rows, meta
    aligned = []
    for period in ("monthly", "daily"):
        maps = {kind: {r["open_time"]: r for r in archives[kind][period]} for kind in SERIES}
        common, union = set.intersection(*(set(m) for m in maps.values())), set.union(*(set(m) for m in maps.values()))
        expected = 31 * 288 if period == "monthly" else 288
        for kind in SERIES:
            m = manifest["series"][kind][period]
            m["expected_rows"] = expected
            m["missing_expected_rows"] = max(0, expected - m["rows"])
        manifest.setdefault("alignment", {})[period] = {
            "common_rows": len(common), "union_rows": len(union),
            "rows_missing_from_at_least_one_series": len(union-common),
            "common_coverage_pct_of_expected": 100.0 * len(common) / expected}
        for ts in sorted(common):
            c, i, m, p = (maps[k][ts]["close"] for k in ("contract", "index", "mark", "premium"))
            if i <= 0:
                raise AssertionError(f"non-positive index close at {ts}")
            aligned.append({"period": period, "open_time": ts, "contract_close": c,
                "index_close": i, "mark_close": m, "premium_index_close": p,
                "perp_index_basis_bps": 10000.0 * (c/i - 1.0),
                "mark_index_premium_bps": 10000.0 * (m/i - 1.0)})
        if period == "daily":
            start, end = utc_ms(DAY), utc_ms(DAY) + 86_400_000 - 1
            for kind in SERIES:
                check = rest_rows(session, kind, start, end)
                if check.get("status") == "available":
                    archive_map, rest_map = maps[kind], check.pop("closes")
                    common_rest = set(rest_map) & set(archive_map)
                    diffs = [abs(rest_map[t]-archive_map[t]["close"]) for t in common_rest]
                    check["matched_rows"] = len(common_rest)
                    check["archive_rest_max_abs_close_diff"] = max(diffs, default=None)
                    check["archive_rest_exact_close_matches"] = sum(
                        1 for t in common_rest if abs(rest_map[t]-archive_map[t]["close"]) <= 1e-10)
                manifest["rest_checks"][kind] = check
    manifest["basis_endpoint"] = basis_endpoint(session)
    if not aligned:
        raise AssertionError("no common timestamps across contract, index, mark and premium archives")
    basis = [r["perp_index_basis_bps"] for r in aligned]
    mark = [r["mark_index_premium_bps"] for r in aligned]
    prem_bps = [r["premium_index_close"]*10000.0 for r in aligned]
    manifest["derived_feature_summary"] = {
        "aligned_rows": len(aligned),
        "perp_index_basis_bps": {"min": min(basis), "p05": quantile(basis,.05),
            "median": quantile(basis,.5), "p95": quantile(basis,.95), "max": max(basis)},
        "mark_index_premium_bps": {"min": min(mark), "p05": quantile(mark,.05),
            "median": quantile(mark,.5), "p95": quantile(mark,.95), "max": max(mark)},
        "premium_index_native": {"min": min(r["premium_index_close"] for r in aligned),
            "median": statistics.median(r["premium_index_close"] for r in aligned),
            "max": max(r["premium_index_close"] for r in aligned)},
        "descriptive_corr_premium_index_x10000_vs_mark_index_bps": correlation(prem_bps,mark),
        "warning": "Premium-index close is not asserted to equal mark/index or contract/index basis."}
    with (out/"aligned_features.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(aligned[0])); w.writeheader(); w.writerows(aligned)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    rows=[]
    for kind in SERIES:
        for period in ("monthly","daily"):
            m=manifest["series"][kind][period]
            rows.append({"series":kind,"period":period,"rows":m["rows"],"expected":m["expected_rows"],
                         "gaps":m["gap_count"],"sha256":m["sha256"],"crc":m["zip_crc"]})
    with (out/"coverage.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    report=["# BTCUSDT USD-M premium/index-basis availability audit",
        "", "**Classification: data audit only — no signal or trading backtest.**",
        "",f"- Monthly archive: {MONTH}; daily archive: {DAY}; interval: {INTERVAL}.",
        f"- Aligned 5m rows: {len(aligned)}.","","## Archive coverage","","| Series | Period | Rows | Expected | Gaps | SHA-256 / ZIP CRC |",
        "|---|---|---:|---:|---:|---|"]
    for r in rows:
        report.append(f"| {r['series']} | {r['period']} | {r['rows']} | {r['expected']} | {r['gaps']} | {r['sha256'][:12]}… / {r['crc']} |")
    report += ["","## Four-series timestamp alignment",""]
    for period,a in manifest["alignment"].items():
        report.append(f"- {period}: common={a['common_rows']}, union={a['union_rows']}, missing-from-any-series={a['rows_missing_from_at_least_one_series']}, common coverage={a['common_coverage_pct_of_expected']:.3f}%.")
    report += ["","## REST archive cross-check",""]
    for kind,c in manifest["rest_checks"].items():
        report.append(f"- {kind}: {c.get('status')}; HTTP={c.get('http_status','—')}; matched rows={c.get('matched_rows','—')}; exact close matches={c.get('archive_rest_exact_close_matches','—')}; max close difference={c.get('archive_rest_max_abs_close_diff','—')}.")
    b=manifest["basis_endpoint"]
    report += ["","## Recent direct basis endpoint","",
        f"- Status: {b.get('status')}; HTTP={b.get('http_status','—')}; rows={b.get('rows','—')}; arithmetic pass={b.get('arithmetic_pass','—')}; documented availability: latest 30 days only."]
    if b.get("error"): report.append(f"- Error: {b['error']}")
    report += ["","## Derived features (not interchangeable)",""]
    for key,val in manifest["derived_feature_summary"].items():
        if isinstance(val,dict):
            report.append(f"- {key}: "+", ".join(f"{k}={v:.8g}" for k,v in val.items()))
    report += ["","Direct perp/index basis uses contract close versus index close. Mark/index premium uses mark close versus index close. Premium-index close is retained in native units and is not assumed to equal either price ratio.",
        "","## Decision","",
        "This audit establishes only availability and alignment for the tested pilot archives. A separate event study is permitted only if archive coverage and semantics are satisfactory. No predictive edge, strategy, trade PnL, fees, funding cashflow, win rate, PF, R, drawdown, or execution result is claimed.",
        "","REST HTTP/network failures are recorded as unavailable and do not invalidate a checksum-verified archive. The /futures/data/basis endpoint is a recent reference only and must not be extrapolated beyond its documented 30-day window."]
    (out/"REPORT.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    return manifest

class AuditTests(unittest.TestCase):
    def test_archive_paths(self):
        self.assertEqual(archive_path("premiumIndexKlines","monthly","2026-10"),
            "data/futures/um/monthly/premiumIndexKlines/BTCUSDT/5m/BTCUSDT-5m-2026-10.zip")
        self.assertEqual(archive_path("indexPriceKlines","daily","2026-11-19"),
            "data/futures/um/daily/indexPriceKlines/BTCUSDT/5m/BTCUSDT-5m-2026-11-19.zip")
    def test_utc_day(self):
        self.assertEqual(utc_ms("2026-11-19"),1795046400000)
    def test_basis_formulas_are_distinct(self):
        contract,mark,index,premium=101.0,100.5,100.0,0.0002
        self.assertAlmostEqual(10000*(contract/index-1),100.0)
        self.assertAlmostEqual(10000*(mark/index-1),50.0)
        self.assertNotAlmostEqual(10000*(contract/index-1),premium*10000)
    def test_quantile(self):
        self.assertEqual(quantile([1.0,2.0,3.0,4.0],.5),2.5)
    def test_correlation(self):
        self.assertAlmostEqual(correlation([1,2,3],[2,4,6]),1.0)
        self.assertIsNone(correlation([1,1,1],[2,3,4]))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--out",type=Path,default=Path("premium_basis_audit_results"))
    args=parser.parse_args()
    if args.self_test:
        result=unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(AuditTests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    m=audit(args.out)
    print(json.dumps({"out":str(args.out),"aligned_rows":m["derived_feature_summary"]["aligned_rows"],
        "basis_endpoint_status":m["basis_endpoint"].get("status")},indent=2))

if __name__=="__main__":
    main()
