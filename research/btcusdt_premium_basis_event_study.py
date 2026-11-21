#!/usr/bin/env python3
"""BTCUSDT USD-M premium/index-basis dislocation event study; descriptive only."""
from __future__ import annotations
import argparse, bisect, calendar, csv, hashlib, json, math, random, statistics, sys, unittest
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import binance_btcusdt_premium_basis_availability_audit as archive_audit

SYMBOL, INTERVAL = "BTCUSDT", "5m"
STEP_MS = 300_000
WARMUP_START, ANALYSIS_START, ANALYSIS_END = "2025-10-01", "2025-11-01", "2026-11-01"
LOOKBACK = 30 * 24 * 12
EVENT_Z = 2.5
EVENT_COOLDOWN = 49                 # 4h05
CONTROL_RADIUS = 48                 # candidate must be >=49 bars from events/controls
MATCH_DISTANCE = 24 * 12            # +/-24h
HORIZONS = {"15m": 3, "1h": 12, "4h": 48}
PRIMARY = "1h"
BOOTSTRAP_REPS, BOOTSTRAP_SEED = 5000, 20261121
REGIME_CUTOFF = 0.005

def month_keys(start="2025-10", end="2026-10"):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    result = []
    while (y, m) <= (ey, em):
        result.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return result

def expected_month_rows(month):
    y, m = map(int, month.split("-"))
    return calendar.monthrange(y, m)[1] * 288

def rolling_prior_zscores(values, lookback):
    """Each z[i] uses values[i-lookback:i], excluding the current observation."""
    n = len(values)
    out = [None] * n
    sums, sums2 = [0.0] * (n + 1), [0.0] * (n + 1)
    for i, x in enumerate(values):
        sums[i + 1] = sums[i] + x
        sums2[i + 1] = sums2[i] + x * x
    for i in range(lookback, n):
        total = sums[i] - sums[i - lookback]
        total2 = sums2[i] - sums2[i - lookback]
        mean = total / lookback
        sd = math.sqrt(max(0.0, total2 / lookback - mean * mean))
        if sd > 1e-12:
            out[i] = (values[i] - mean) / sd
    return out

def prior_24h_context(prices):
    n = len(prices)
    returns = [0.0] * n
    for i in range(1, n):
        returns[i] = math.log(prices[i] / prices[i - 1])
    sums, sums2 = [0.0] * (n + 1), [0.0] * (n + 1)
    for i, x in enumerate(returns):
        sums[i + 1] = sums[i] + x
        sums2[i + 1] = sums2[i] + x * x
    ret24, rv24 = [None] * n, [None] * n
    for i in range(288, n):
        start = i - 287
        total = sums[i + 1] - sums[start]
        total2 = sums2[i + 1] - sums2[start]
        mean = total / 288
        ret24[i] = math.log(prices[i] / prices[i - 288])
        rv24[i] = math.sqrt(max(0.0, total2 / 288 - mean * mean))
    return ret24, rv24

def split_bounds(start, count):
    a = start + int(count * 0.60)
    b = start + int(count * 0.80)
    return [("development", start, a), ("validation", a, b), ("oos", b, start + count)]

def bucket(value, cuts):
    return None if value is None else bisect.bisect_right(cuts, value)

def regime_of(ret24):
    if ret24 is None:
        return None
    if ret24 <= -REGIME_CUTOFF:
        return "bear"
    if ret24 >= REGIME_CUTOFF:
        return "bull"
    return "neutral"

def select_events(zscores, ret24, rv24, start, end):
    events, last = [], -10**12
    for i in range(start, max(start, end - HORIZONS["4h"])):
        z = zscores[i]
        if z is None or abs(z) < EVENT_Z or ret24[i] is None or rv24[i] is None:
            continue
        if i - last < EVENT_COOLDOWN:
            continue
        events.append(i)
        last = i
    return events

def mark_neighborhood(mask, center, radius=CONTROL_RADIUS):
    for i in range(max(0, center - radius), min(len(mask), center + radius + 1)):
        mask[i] = True

def nearest_control(event_idx, split_start, split_end, side, zscores,
                    ret_buckets, vol_buckets, regimes, blocked):
    for distance in range(MATCH_DISTANCE + 1):
        candidates = [event_idx] if distance == 0 else [event_idx - distance, event_idx + distance]
        for c in candidates:
            if c < split_start or c + HORIZONS["4h"] >= split_end or blocked[c]:
                continue
            z = zscores[c]
            if z is None or z * side <= 0 or abs(z) >= EVENT_Z:
                continue
            if ret_buckets[c] is None or vol_buckets[c] is None:
                continue
            if ret_buckets[c] != ret_buckets[event_idx]:
                continue
            if vol_buckets[c] != vol_buckets[event_idx] or regimes[c] != regimes[event_idx]:
                continue
            return c
    return None

def signed_reversion(start_value, future_value, side):
    return -side * (future_value - start_value)

def cluster_bootstrap_ci(pair_rows, seed, reps=BOOTSTRAP_REPS):
    groups = defaultdict(list)
    for row in pair_rows:
        groups[row["event_day"]].append(float(row["lift_bps"]))
    if len(groups) < 2:
        return None, None, len(groups)
    means = [statistics.mean(v) for _, v in sorted(groups.items())]
    rng, draws = random.Random(seed), []
    for _ in range(reps):
        draws.append(statistics.mean(rng.choice(means) for _ in range(len(means))))
    return archive_audit.quantile(draws, .025), archive_audit.quantile(draws, .975), len(means)

def load_aligned_months(out):
    import requests
    session = requests.Session()
    session.headers.update({"User-Agent": "salty-quant-btc-premium-basis-event-study/1.0"})
    rows_all, archive_manifest = [], []
    for month in month_keys():
        per_series, expected = {}, expected_month_rows(month)
        for name, spec in archive_audit.SERIES.items():
            rows, meta = archive_audit.download_archive(session, spec["archive"], "monthly", month)
            if len(rows) != expected or meta["gap_count"] or meta["duplicate_count"]:
                raise AssertionError(f"{name} {month}: rows={len(rows)}/{expected}, gaps={meta['gap_count']}, duplicates={meta['duplicate_count']}")
            per_series[name] = {r["open_time"]: r for r in rows}
            archive_manifest.append({
                "series": name, "month": month, "rows": len(rows), "expected_rows": expected,
                "gaps": meta["gap_count"], "duplicates": meta["duplicate_count"],
                "sha256": meta["sha256"], "zip_crc": meta["zip_crc"],
                "relative_path": meta["relative_path"], "bytes": meta["bytes"],
            })
        common = set.intersection(*(set(m) for m in per_series.values()))
        union = set.union(*(set(m) for m in per_series.values()))
        if len(common) != expected or len(union) != expected:
            raise AssertionError(f"{month}: four-series alignment {len(common)}/{expected}; union={len(union)}")
        for ts in sorted(common):
            c, ix, mark, prem = (per_series[k][ts]["close"] for k in ("contract", "index", "mark", "premium"))
            if min(c, ix, mark) <= 0:
                raise AssertionError(f"{month}: non-positive price at {ts}")
            rows_all.append({
                "open_time": ts, "contract_close": c, "index_close": ix,
                "mark_close": mark, "premium_index_close": prem,
                "perp_index_basis_bps": 10000.0 * (c / ix - 1.0),
                "mark_index_premium_bps": 10000.0 * (mark / ix - 1.0),
            })
    rows_all.sort(key=lambda r: r["open_time"])
    ts = [r["open_time"] for r in rows_all]
    if len(ts) != len(set(ts)) or any(b - a != STEP_MS for a, b in zip(ts, ts[1:])):
        raise AssertionError("duplicate, gap or off-grid interval across monthly boundaries")
    out.mkdir(parents=True, exist_ok=True)
    return rows_all, archive_manifest

def write_csv(path, rows, fields=None):
    if fields is None:
        fields = list(rows[0]) if rows else ["no_rows"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def run_study(out):
    out.mkdir(parents=True, exist_ok=True)
    rows, archive_manifest = load_aligned_months(out)
    timestamps = [r["open_time"] for r in rows]
    a0 = bisect.bisect_left(timestamps, archive_audit.utc_ms(ANALYSIS_START))
    a1 = bisect.bisect_left(timestamps, archive_audit.utc_ms(ANALYSIS_END))
    if timestamps[a0] != archive_audit.utc_ms(ANALYSIS_START) or timestamps[a1 - 1] != archive_audit.utc_ms(ANALYSIS_END) - STEP_MS:
        raise AssertionError("analysis boundaries are not fully covered")
    count = a1 - a0
    if count != 365 * 288:
        raise AssertionError(f"expected 105120 analysis rows, got {count}")

    basis = [r["perp_index_basis_bps"] for r in rows]
    mark = [r["mark_index_premium_bps"] for r in rows]
    prem = [r["premium_index_close"] for r in rows]
    index = [r["index_close"] for r in rows]
    z = rolling_prior_zscores(basis, LOOKBACK)
    ret24, rv24 = prior_24h_context(index)
    splits = split_bounds(a0, count)
    train_start, train_end = splits[0][1], splits[0][2]
    train_ret = [ret24[i] for i in range(train_start, train_end) if ret24[i] is not None]
    train_vol = [rv24[i] for i in range(train_start, train_end) if rv24[i] is not None]
    if len(train_ret) < 1000 or len(train_vol) < 1000:
        raise AssertionError("insufficient development observations for matching cutpoints")
    ret_cuts = [archive_audit.quantile(train_ret, q / 10) for q in range(1, 10)]
    vol_cuts = [archive_audit.quantile(train_vol, q / 4) for q in range(1, 4)]
    ret_b = [bucket(x, ret_cuts) for x in ret24]
    vol_b = [bucket(x, vol_cuts) for x in rv24]
    regimes = [regime_of(x) for x in ret24]

    events, raw_counts = [], {}
    for name, start, end in splits:
        selected = select_events(z, ret24, rv24, start, end)
        raw_counts[name] = len(selected)
        for i in selected:
            events.append((i, name, start, end, 1 if z[i] > 0 else -1))
    events.sort(key=lambda x: x[0])

    blocked = [False] * len(rows)
    for i, *_ in events:
        mark_neighborhood(blocked, i)
    pair_rows, event_rows, used_controls = [], [], set()
    for i, split_name, start, end, side in events:
        c = nearest_control(i, start, end, side, z, ret_b, vol_b, regimes, blocked)
        event_time = timestamps[i] + STEP_MS
        dt = datetime.fromtimestamp(event_time / 1000, tz=timezone.utc)
        day, month = dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m")
        event = {
            "asset": SYMBOL, "split": split_name, "event_time_utc": event_time,
            "event_day": day, "month": month,
            "side": "positive_basis" if side > 0 else "negative_basis",
            "zscore": z[i], "basis_bps": basis[i],
            "mark_index_premium_bps": mark[i], "premium_index_native": prem[i],
            "prior_24h_index_return": ret24[i], "prior_24h_realized_vol": rv24[i],
            "return_decile": ret_b[i], "volatility_quartile": vol_b[i],
            "regime": regimes[i], "matched": c is not None,
            "control_time_utc": timestamps[c] + STEP_MS if c is not None else None,
        }
        if c is not None:
            if c in used_controls:
                raise AssertionError("control reused")
            used_controls.add(c)
            mark_neighborhood(blocked, c)
            for horizon, bars in HORIZONS.items():
                er = signed_reversion(basis[i], basis[i + bars], side)
                cr = signed_reversion(basis[c], basis[c + bars], side)
                mr = signed_reversion(mark[i], mark[i + bars], side)
                pi_change = -side * (prem[i + bars] - prem[i]) * 10000.0
                pair_rows.append({
                    "asset": SYMBOL, "split": split_name, "horizon": horizon, "bars": bars,
                    "event_time_utc": event_time, "event_day": day, "month": month,
                    "control_time_utc": timestamps[c] + STEP_MS,
                    "side": event["side"], "zscore": z[i],
                    "event_basis_bps": basis[i], "control_basis_bps": basis[c],
                    "event_reversion_bps": er, "control_reversion_bps": cr,
                    "lift_bps": er - cr, "mark_index_signed_reversion_bps": mr,
                    "premium_index_signed_change_x10000": pi_change,
                    "regime": regimes[i], "return_decile": ret_b[i],
                    "volatility_quartile": vol_b[i],
                })
        event_rows.append(event)

    summary = []
    for split_name, _, _ in splits:
        split_events = [r for r in event_rows if r["split"] == split_name]
        for horizon in HORIZONS:
            pairs = [r for r in pair_rows if r["split"] == split_name and r["horizon"] == horizon]
            lifts = [r["lift_bps"] for r in pairs]
            er = [r["event_reversion_bps"] for r in pairs]
            cr = [r["control_reversion_bps"] for r in pairs]
            seed = BOOTSTRAP_SEED + (0 if split_name == "development" else 1000 if split_name == "validation" else 2000) + HORIZONS[horizon]
            low, high, days = cluster_bootstrap_ci(pairs, seed)
            summary.append({
                "asset": SYMBOL, "split": split_name, "horizon": horizon,
                "raw_events": len(split_events), "matched_pairs": len(pairs),
                "event_reversion_mean_bps": statistics.mean(er) if er else None,
                "control_reversion_mean_bps": statistics.mean(cr) if cr else None,
                "paired_lift_mean_bps": statistics.mean(lifts) if lifts else None,
                "paired_lift_median_bps": statistics.median(lifts) if lifts else None,
                "event_beats_control_fraction": sum(x > 0 for x in lifts) / len(lifts) if lifts else None,
                "event_day_clusters": days, "cluster_bootstrap_ci_low_bps": low,
                "cluster_bootstrap_ci_high_bps": high,
            })

    monthly_groups, regime_groups = defaultdict(list), defaultdict(list)
    for row in pair_rows:
        monthly_groups[(row["split"], row["month"])].append(row)
        regime_groups[(row["split"], row["regime"])].append(row)
    monthly, regime = [], []
    for (split_name, month), group in sorted(monthly_groups.items()):
        for horizon in HORIZONS:
            subset = [r for r in group if r["horizon"] == horizon]
            lifts = [r["lift_bps"] for r in subset]
            monthly.append({
                "asset": SYMBOL, "split": split_name, "month": month, "horizon": horizon,
                "matched_pairs": len(subset),
                "mean_event_reversion_bps": statistics.mean([r["event_reversion_bps"] for r in subset]) if subset else None,
                "mean_control_reversion_bps": statistics.mean([r["control_reversion_bps"] for r in subset]) if subset else None,
                "mean_paired_lift_bps": statistics.mean(lifts) if lifts else None,
                "event_beats_control_fraction": sum(x > 0 for x in lifts) / len(lifts) if lifts else None,
            })
    for (split_name, regime_name), group in sorted(regime_groups.items()):
        for horizon in HORIZONS:
            subset = [r for r in group if r["horizon"] == horizon]
            lifts = [r["lift_bps"] for r in subset]
            regime.append({
                "asset": SYMBOL, "split": split_name, "regime": regime_name, "horizon": horizon,
                "matched_pairs": len(subset),
                "mean_event_reversion_bps": statistics.mean([r["event_reversion_bps"] for r in subset]) if subset else None,
                "mean_control_reversion_bps": statistics.mean([r["control_reversion_bps"] for r in subset]) if subset else None,
                "mean_paired_lift_bps": statistics.mean(lifts) if lifts else None,
                "event_beats_control_fraction": sum(x > 0 for x in lifts) / len(lifts) if lifts else None,
            })

    primary = {r["split"]: r for r in summary if r["horizon"] == PRIMARY}
    enough = all(primary.get(s, {}).get("matched_pairs", 0) >= 30 for s in ("development", "validation", "oos"))
    positive_means = all(primary.get(s, {}).get("paired_lift_mean_bps") is not None and primary[s]["paired_lift_mean_bps"] > 0 for s in ("development", "validation", "oos"))
    oos_low = primary.get("oos", {}).get("cluster_bootstrap_ci_low_bps")
    decision = "candidate_for_separate_execution_preregistration" if enough and positive_means and oos_low is not None and oos_low > 0 else "no_stable_predictive_edge_established"

    write_csv(out / "summary.csv", summary)
    write_csv(out / "monthly.csv", monthly)
    write_csv(out / "regime.csv", regime)
    write_csv(out / "matched_pairs.csv", pair_rows)
    write_csv(out / "events.csv", event_rows)
    write_csv(out / "aligned_features.csv", rows)
    write_csv(out / "archive_manifest.csv", archive_manifest)

    split_meta = []
    for name, start, end in splits:
        split_meta.append({
            "split": name,
            "start_utc": datetime.fromtimestamp(timestamps[start] / 1000, tz=timezone.utc).isoformat(),
            "end_exclusive_utc": datetime.fromtimestamp(timestamps[end - 1] / 1000 + STEP_MS, tz=timezone.utc).isoformat(),
            "bars": end - start,
        })
    manifest = {
        "research_type": "event_study", "artifact_type": "descriptive_event_study",
        "data_classification": "derived_market_features", "validation_state": "not_a_strategy",
        "decision": decision, "oos_evaluated": True, "strategy_oos_evaluated": False,
        "symbol": SYMBOL, "venue": "Binance USD-M perpetual", "interval": INTERVAL,
        "warmup_start_utc": WARMUP_START, "analysis_start_utc": ANALYSIS_START,
        "analysis_end_exclusive_utc": ANALYSIS_END, "analysis_bars": count,
        "rolling_basis_zscore_lookback_bars": LOOKBACK, "event_threshold_abs_z": EVENT_Z,
        "event_cooldown_bars": EVENT_COOLDOWN, "primary_horizon": PRIMARY,
        "secondary_horizons": ["15m", "4h"], "horizons_bars": HORIZONS,
        "regime_threshold_abs_24h_return": REGIME_CUTOFF,
        "matching": {
            "same_split": True, "same_basis_side": True,
            "same_development_defined_24h_index_return_decile": True,
            "same_development_defined_24h_realized_volatility_quartile": True,
            "same_fixed_24h_regime": True, "nearest_control_within_hours": 24,
            "minimum_event_control_and_control_control_separation_minutes": 245,
            "no_control_reuse": True, "all_4h_outcomes_inside_split": True,
        },
        "bootstrap": {
            "method": "UTC event-day cluster bootstrap of cluster means",
            "replicates": BOOTSTRAP_REPS, "seed_base": BOOTSTRAP_SEED,
            "interval": "95% descriptive percentile interval; not a p-value",
        },
        "splits": split_meta, "raw_event_counts": raw_counts,
        "matched_pairs_by_split_horizon": {f"{r['split']}_{r['horizon']}": r["matched_pairs"] for r in summary},
        "archive_manifest": archive_manifest,
        "source_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fees_funding": "not_applicable; no positions simulated",
        "trading_metrics": "not_applicable; event study only",
        "rest_crosscheck": "not run; prior pilot REST endpoints returned HTTP 451",
        "decision_rule": {
            "minimum_matched_pairs_each_split_primary_horizon": 30,
            "development_validation_oos_mean_lift_all_positive": True,
            "oos_primary_cluster_ci_lower_positive": True,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def f(x):
        return "—" if x is None else f"{x:.3f}"
    report = [
        "# BTCUSDT USD-M premium/index-basis dislocation event study", "",
        "**Classification: descriptive event study; no executable strategy or PnL.**", "",
        f"- Analysis: {ANALYSIS_START} inclusive to {ANALYSIS_END} exclusive; 12 complete UTC months.",
        f"- Warmup: {WARMUP_START}; prior-only 30-day basis z-score.",
        f"- Aligned analysis bars: {count:,}; 13 monthly archive sets (warmup plus analysis), four series each.",
        "- Series: contract, index, mark and premium-index klines; derived features remain distinct.", "",
        "## Frozen rules", "",
        f"- Event: absolute prior-only 30-day rolling z-score of contract/index basis >= {EVENT_Z:.1f}.",
        "- Positive event means perpetual rich; negative event means perpetual cheap.",
        "- Event cooldown: 245 minutes; no overlapping 4h event horizons.",
        "- Primary outcome: signed basis reversion; positive means movement toward zero.",
        "- Primary horizon: 1h; 15m and 4h are secondary descriptive horizons.",
        "- Controls match split, basis side, development-defined 24h return decile, development-defined 24h realized-volatility quartile and fixed prior-24h regime.",
        "- Nearest eligible control within +/-24h; at least 245 minutes from every event and selected control; no reuse.",
        "- 5,000 UTC event-day cluster bootstrap replicates; intervals are descriptive, not p-values.", "",
        "## Chronological splits", "",
        "| Split | Start | End exclusive | Bars |", "|---|---|---|---:|",
    ]
    for s in split_meta:
        report.append(f"| {s['split']} | {s['start_utc']} | {s['end_exclusive_utc']} | {s['bars']:,} |")
    report += ["", "## Results", "",
        "| Split | Horizon | Events | Matched | Event reversion bps | Control reversion bps | Lift bps | 95% cluster CI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        ci = f"{f(r['cluster_bootstrap_ci_low_bps'])} to {f(r['cluster_bootstrap_ci_high_bps'])}"
        report.append(f"| {r['split']} | {r['horizon']} | {r['raw_events']} | {r['matched_pairs']} | {f(r['event_reversion_mean_bps'])} | {f(r['control_reversion_mean_bps'])} | {f(r['paired_lift_mean_bps'])} | {ci} |")
    report += [
        "", "## Decision", "", f"**{decision}**", "",
        "The preregistered gate uses the primary 1h horizon: at least 30 matched pairs in each split, positive mean paired lift in development/validation/OOS, and a positive lower bound of the OOS event-day cluster-bootstrap interval. This is a screening rule, not a formal significance test.",
        "", "## Costs and trading metrics", "",
        "No position, entry, stop, target or execution is simulated. Fees, spread, slippage and funding are not applicable. Win rate, PF, net R, trading drawdown and losing streak are not applicable. Any later execution strategy requires a separate preregistration with actual funding, fees/slippage and conservative intrabar handling.",
        "", "## Data integrity and limitations", "",
        "- All 52 monthly archive ZIPs and sibling SHA-256 checksums are verified; ZIP CRC, schema, expected row counts, UTC 5m grid, duplicate/gap checks, monthly boundaries and four-series timestamp alignment are fail-closed.",
        "- October 2025 is warmup only; event sample begins 1 November 2025.",
        "- Premium-index close is not assumed equal to contract/index basis or mark/index premium.",
        "- Binance REST cross-check is unavailable from the prior runner due HTTP 451; no REST parity claim is made.",
        "- Matching controls observable context but does not prove causality; cluster intervals may not remove all serial dependence.",
        "- No threshold/lookback/cooldown/horizon grid was run; definitions were frozen before the full download.",
    ]
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return manifest

class StudyTests(unittest.TestCase):
    def test_month_range_and_expected_rows(self):
        self.assertEqual(len(month_keys()), 13)
        self.assertEqual(month_keys()[0], "2025-10")
        self.assertEqual(month_keys()[-1], "2026-10")
        self.assertEqual(expected_month_rows("2025-11"), 8640)
        self.assertEqual(expected_month_rows("2026-10"), 8928)

    def test_prior_zscore_is_causal(self):
        values = [float(i % 17) for i in range(200)]
        before = rolling_prior_zscores(values, 30)
        changed = values[:]
        for i in range(100, len(changed)):
            changed[i] += 100000.0
        after = rolling_prior_zscores(changed, 30)
        self.assertEqual(before[99], after[99])

    def test_event_cooldown(self):
        z, ret, rv = [0.0] * 400, [0.0] * 400, [0.01] * 400
        z[100], z[140], z[149] = 3.0, 3.0, 3.0
        self.assertEqual(select_events(z, ret, rv, 0, 400), [100, 149])

    def test_signed_reversion(self):
        self.assertGreater(signed_reversion(10.0, 5.0, 1), 0)
        self.assertGreater(signed_reversion(-10.0, -5.0, -1), 0)
        self.assertLess(signed_reversion(10.0, 12.0, 1), 0)

    def test_control_nonoverlap_and_no_reuse(self):
        n, z = 500, [0.2] * 500
        z[100], z[300], z[350] = 3.0, -3.0, -0.3
        rb, vb, rg = [0] * n, [0] * n, ["neutral"] * n
        blocked = [False] * n
        mark_neighborhood(blocked, 100)
        mark_neighborhood(blocked, 300)
        c1 = nearest_control(100, 0, 500, 1, z, rb, vb, rg, blocked)
        self.assertEqual(c1, 50)
        mark_neighborhood(blocked, c1)
        c2 = nearest_control(300, 0, 500, -1, z, rb, vb, rg, blocked)
        self.assertEqual(c2, 350)
        self.assertNotEqual(c1, c2)
        self.assertGreaterEqual(abs(c1 - 100), 49)
        self.assertGreaterEqual(abs(c2 - 300), 49)
        self.assertGreaterEqual(abs(c2 - c1), 49)

    def test_exact_split_sizes(self):
        bounds = split_bounds(1000, 105120)
        self.assertEqual([x[2] - x[1] for x in bounds], [63072, 21024, 21024])
        self.assertEqual(bounds[0][2], bounds[1][1])
        self.assertEqual(bounds[1][2], bounds[2][1])

    def test_bootstrap_reproducible(self):
        pairs = [
            {"event_day": "2026-01-01", "lift_bps": 1.0},
            {"event_day": "2026-01-01", "lift_bps": 3.0},
            {"event_day": "2026-01-02", "lift_bps": -1.0},
            {"event_day": "2026-01-03", "lift_bps": 2.0},
        ]
        self.assertEqual(cluster_bootstrap_ci(pairs, 42, 500), cluster_bootstrap_ci(pairs, 42, 500))

    def test_basis_features_are_distinct(self):
        contract, index, mark, premium = 101.0, 100.0, 100.5, 0.0002
        basis = 10000.0 * (contract / index - 1.0)
        mark_premium_bps = 10000.0 * (mark / index - 1.0)
        self.assertEqual(basis, 100.0)
        self.assertEqual(mark_premium_bps, 50.0)
        self.assertNotEqual(basis, premium * 10000.0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("btc-premium-basis-event-study"))
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StudyTests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    result = run_study(args.out)
    print(json.dumps({
        "decision": result["decision"], "analysis_bars": result["analysis_bars"],
        "raw_event_counts": result["raw_event_counts"],
        "matched_pairs": result["matched_pairs_by_split_horizon"],
    }, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
