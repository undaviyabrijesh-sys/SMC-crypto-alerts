#!/usr/bin/env python3
"""Causal BTC/ETH OI-expansion plus price-impulse event study.

Exploratory event study only, not an executable strategy backtest. Delta mark
prices are used only for forward-return diagnostics, never as trade fills.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

H1 = pd.Timedelta(hours=1)
M5 = pd.Timedelta(minutes=5)
LOOKBACK, MIN_PERIODS = 168, 72
MAIN_Z, MAIN_Q, COOLDOWN_H = 1.5, 95, 8


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["timestamp"])
    if not d["timestamp"].dt.tz or d["timestamp"].duplicated().any():
        raise ValueError(f"{path.name}: timestamps must be unique and timezone-aware")
    d = d.sort_values("timestamp").set_index("timestamp")
    for c in ("open", "high", "low", "close"):
        if not np.isfinite(d[c].to_numpy(float)).all():
            raise ValueError(f"{path.name}: invalid {c}")
    return d


def validate_cadence(index: pd.DatetimeIndex, step: pd.Timedelta, label: str) -> None:
    bad = index.to_series().diff().dropna().ne(step).sum()
    if bad:
        raise ValueError(f"{label}: {bad} irregular intervals; no gap filling allowed")


def latest_known_close(mark_close: pd.Series, when: pd.Timestamp) -> float:
    """Return last mark close available at the requested timestamp, never a future bar."""
    i = mark_close.index.searchsorted(when, side="right") - 1
    if i < 0 or when - mark_close.index[i] > M5:
        return float("nan")
    return float(mark_close.iloc[i])


def causal_features(oi: pd.DataFrame, mark: pd.DataFrame) -> pd.DataFrame:
    # Historical candle timestamps are treated as candle opens. An OI close is
    # exposed only at open + 1h; mark closes are available at open + 5m.
    mc = pd.Series(mark.close.to_numpy(float), index=mark.index + M5).sort_index()
    available = oi.index + H1
    px0 = np.array([latest_known_close(mc, t) for t in oi.index])
    px1 = np.array([latest_known_close(mc, t) for t in available])
    f1 = np.array([latest_known_close(mc, t + H1) for t in available])
    f4 = np.array([latest_known_close(mc, t + 4 * H1) for t in available])
    f8 = np.array([latest_known_close(mc, t + 8 * H1) for t in available])
    d = pd.DataFrame(index=available)
    d.index.name = "available_time"
    d["oi_close"] = oi.close.to_numpy(float)
    d["oi_pct"] = d.oi_close.pct_change()
    r = d.oi_pct.rolling(LOOKBACK, min_periods=MIN_PERIODS)
    d["oi_z"] = (d.oi_pct - r.mean().shift(1)) / r.std(ddof=0).shift(1).replace(0, np.nan)
    d["price_1h"] = px1 / px0 - 1
    d["fwd1h"], d["fwd4h"], d["fwd8h"] = f1 / px1 - 1, f4 / px1 - 1, f8 / px1 - 1
    q = d.price_1h.abs().rolling(LOOKBACK, min_periods=MIN_PERIODS)
    d["q90"], d["q95"] = q.quantile(.90).shift(1), q.quantile(.95).shift(1)
    return d


def non_overlapping(d: pd.DataFrame, cooldown_h: int = COOLDOWN_H) -> pd.DataFrame:
    if d.empty:
        return d.copy()
    keep, last = [], None
    for t in d.sort_index().index:
        if last is None or t - last >= pd.Timedelta(hours=cooldown_h):
            keep.append(t)
            last = t
    return d.loc[keep].copy()


def events(d: pd.DataFrame, z: float = MAIN_Z, q: int = MAIN_Q) -> pd.DataFrame:
    x = d[(d.oi_z >= z) & (d.oi_pct > 0) & (d.price_1h.abs() >= d[f"q{q}"]) & d.fwd8h.notna()].copy()
    x["signal"] = np.where(x.price_1h > 0, "long_crowding", "short_crowding")
    x["reversal_sign"] = np.where(x.price_1h > 0, -1.0, 1.0)
    return non_overlapping(x)


def boundaries(index: pd.DatetimeIndex):
    span = index.max() - index.min()
    return index.min() + .70 * span, index.min() + .85 * span


def metrics(x: pd.DataFrame, asset: str, split: str, spec: str) -> dict:
    if x.empty:
        return {"asset": asset, "split": split, "spec": spec, "events": 0}
    rev = x.fwd4h * x.reversal_sign
    return {
        "asset": asset, "split": split, "spec": spec, "events": len(x),
        "long_crowding": int((x.signal == "long_crowding").sum()),
        "short_crowding": int((x.signal == "short_crowding").sum()),
        "mean_fwd1h_mark_pct": x.fwd1h.mean() * 100,
        "mean_fwd4h_mark_pct": x.fwd4h.mean() * 100,
        "median_fwd4h_mark_pct": x.fwd4h.median() * 100,
        "mean_fwd8h_mark_pct": x.fwd8h.mean() * 100,
        "mean_expected_reversal_4h_pct": rev.mean() * 100,
        "reversal_hit_4h_pct": (rev > 0).mean() * 100,
    }


def run(data_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((data_dir / "manifest.json").read_text())
    summaries, sensitivity, monthly, main_events, meta = [], [], [], [], {}
    for asset in ("BTC", "ETH"):
        oi_path, mark_path = data_dir / f"{asset}_open_interest_1h.csv", data_dir / f"{asset}_mark_5m.csv"
        oi, mark = load(oi_path), load(mark_path)
        validate_cadence(oi.index, H1, f"{asset} OI")
        validate_cadence(mark.index, M5, f"{asset} mark")
        for path, key in ((oi_path, f"{asset}_{asset}USD_open_interest_1h"), (mark_path, f"{asset}_{asset}USD_mark_5m")):
            expected = manifest["datasets"][key]
            if sha256(path) != expected["sha256"] or len(pd.read_csv(path)) != expected["row_count"]:
                raise ValueError(f"{path.name}: manifest hash/row-count mismatch")
        d = causal_features(oi, mark)
        tr_end, va_end = boundaries(d.index)
        meta[asset] = {
            "oi_rows": len(oi), "mark_rows": len(mark),
            "oi_sha256": sha256(oi_path), "mark_sha256": sha256(mark_path),
            "train_end_available_utc": tr_end.isoformat(),
            "validation_end_available_utc": va_end.isoformat(),
        }
        d.to_csv(out_dir / f"{asset.lower()}_causal_features.csv", index_label="available_time")
        main = events(d)
        main["asset"] = asset
        main["expected_reversal_4h_pct"] = main.fwd4h * main.reversal_sign * 100
        main["month"] = main.index.strftime("%Y-%m")
        main["split"] = np.where(main.index <= tr_end, "train", np.where(main.index <= va_end, "validation", "oos"))
        main_events.append(main.reset_index())
        for split in ("train", "validation", "oos"):
            summaries.append(metrics(main[main.split == split], asset, split, "OI z>=1.5, positive OI change, 1h mark impulse >= prior q95"))
        if not main.empty:
            m = main.groupby("month").agg(events=("fwd4h", "size"),
                mean_expected_reversal_4h_pct=("expected_reversal_4h_pct", "mean"),
                reversal_hit_4h_pct=("expected_reversal_4h_pct", lambda v: (v > 0).mean() * 100)).reset_index()
            m.insert(0, "asset", asset)
            monthly.extend(m.to_dict("records"))
        control = d[(d.price_1h.abs() >= d.q95) & d.fwd8h.notna()].copy()
        control["signal"] = np.where(control.price_1h > 0, "long_crowding", "short_crowding")
        control["reversal_sign"] = np.where(control.price_1h > 0, -1.0, 1.0)
        control = non_overlapping(control)
        control["split"] = np.where(control.index <= tr_end, "train", np.where(control.index <= va_end, "validation", "oos"))
        for split in ("train", "validation", "oos"):
            summaries.append(metrics(control[control.split == split], asset, split, "price-only prior q95 control"))
        for z in (1.0, 1.5, 2.0):
            for q in (90, 95):
                e = events(d, z, q)
                e["split"] = np.where(e.index <= tr_end, "train", np.where(e.index <= va_end, "validation", "oos"))
                for split in ("train", "validation", "oos"):
                    v = e[e.split == split]
                    sensitivity.append({"asset": asset, "oi_z": z, "price_q": q, "split": split,
                        "events": len(v),
                        "mean_expected_reversal_4h_pct": (v.fwd4h * v.reversal_sign).mean() * 100 if len(v) else np.nan,
                        "reversal_hit_4h_pct": ((v.fwd4h * v.reversal_sign) > 0).mean() * 100 if len(v) else np.nan})
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summaries).to_csv(out_dir / "summary.csv", index=False)
    pd.DataFrame(sensitivity).to_csv(out_dir / "sensitivity.csv", index=False)
    pd.DataFrame(monthly).to_csv(out_dir / "monthly.csv", index=False)
    pd.concat(main_events, ignore_index=True).to_csv(out_dir / "main_events.csv", index=False)
    result = {
        "classification": "exploratory event study, not a trade backtest",
        "main_spec": "OI pct change >0 and prior-168h z-score >=1.5; abs 1h mark return >= prior-168h q95; 8h global event cooldown",
        "availability": "OI hourly candle is exposed only at timestamp+1h; mark 5m close at open+5m; last-known mark close only",
        "splits": "chronological 70/15/15 by OI-available timestamp",
        "limitations": ["Mark price is not executable traded-price data; no fee, spread, slippage, funding, stops, R, PF or drawdown.",
            "OI raw units are not interpreted; only percentage changes are used.",
            "Historical OI candle sampling convention still needs exchange confirmation.",
            "Funding is excluded pending historical event-time settlement mapping.",
            "Filtered event samples are small; results are descriptive, not statistically conclusive."],
        "data": meta,
    }
    (out_dir / "study_metadata.json").write_text(json.dumps(result, indent=2))
    return result


def self_test() -> None:
    t0 = pd.Timestamp("2025-01-01T00:00:00Z")
    oi_idx = pd.date_range(t0, periods=220, freq="1h")
    oc = 1000 + np.arange(220) * .5 + 4 * np.sin(np.arange(220) / 5)
    oi = pd.DataFrame({"open": oc*.999, "high": oc*1.002, "low": oc*.998, "close": oc}, index=oi_idx)
    mi = pd.date_range(t0-M5, periods=220*12+8*12+1, freq="5min")
    mc = 50000 + np.arange(len(mi))*2 + 100*np.sin(np.arange(len(mi))/17)
    mark = pd.DataFrame({"open":mc-1,"high":mc+5,"low":mc-5,"close":mc}, index=mi)
    s = pd.Series([100.,110.,120.], index=pd.date_range("2025-01-01T00:05:00Z", periods=3, freq="5min"))
    assert latest_known_close(s, pd.Timestamp("2025-01-01T00:07:00Z")) == 100.
    assert np.isnan(latest_known_close(s, pd.Timestamp("2025-01-01T00:21:00Z")))
    base = causal_features(oi, mark)
    t = oi_idx[180] + H1
    oi2 = oi.copy(); oi2.iloc[181:, :] *= 1.5
    mark2 = mark.copy(); mark2.loc[(mark2.index+M5)>t, ["open","high","low","close"]] *= 1.2
    a, b, c = base, causal_features(oi2, mark), causal_features(oi, mark2)
    for col in ("oi_z","oi_pct","price_1h","q90","q95"):
        assert np.isclose(a.loc[t,col], b.loc[t,col], equal_nan=True)
        assert np.isclose(a.loc[t,col], c.loc[t,col], equal_nan=True)
    assert not np.isclose(a.loc[t,"fwd8h"], c.loc[t,"fwd8h"])
    idx = pd.to_datetime(["2025-01-01T00:00:00Z","2025-01-01T04:00:00Z","2025-01-01T08:00:00Z","2025-01-01T17:00:00Z"])
    x = pd.DataFrame({"signal":["long","short","long","short"]}, index=idx)
    assert list(non_overlapping(x).index) == [idx[0],idx[2],idx[3]]
    e1 = events(base, .5, 90); base2 = base.copy(); base2[["fwd1h","fwd4h","fwd8h"]] = 999.
    assert list(e1.index) == list(events(base2,.5,90).index)
    print("4 OI event-study causality/alignment self-tests passed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test(); return
    if not a.data_dir or not a.output_dir:
        p.error("--data-dir and --output-dir are required unless --self-test is used")
    print(json.dumps(run(a.data_dir, a.output_dir), indent=2))
    print((a.output_dir / "summary.csv").read_text())


if __name__ == "__main__":
    main()
