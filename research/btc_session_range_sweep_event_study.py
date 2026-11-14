#!/usr/bin/env python3
"""Preregistered BTC session-range sweep/re-entry forward-return event study.

Research-only. Delta BTCUSD traded-price 5m OHLCV. Asia range: 00:00-06:00 UTC.
A qualifying event is the first 06:00-18:00 UTC candle that sweeps one range
edge and closes back inside. Entry is next 5m open. Both-edge sweeps are ignored.
One event per UTC day. Forward returns are compared with a deterministic
same-day, same-side random-time control outside the signal neighbourhood.
No stop/target optimization or executable-PnL claim is made in this phase.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

URL = "https://api.india.delta.exchange/v2/history/candles"
SYMBOL = "BTCUSD"
STEP = pd.Timedelta(minutes=5)
ASIA_BARS = 72
HORIZONS = {"15m": 3, "1h": 12, "4h": 48, "8h": 96}
COSTS_BPS = (6.0, 12.0, 20.0)
CONTROL_SEED = 20261114
CONTROL_EXCLUSION_BARS = 6  # +/- 30m around signal; controls are not signal bars

class StudyError(RuntimeError):
    pass

def fetch_data(days: int = 730, delay: float = 0.12) -> pd.DataFrame:
    end = int(pd.Timestamp.now(tz="UTC").floor("5min").timestamp())
    start = end - days * 86400
    span = 300 * 1800 - 1
    rows = []
    session = requests.Session()
    cursor = start
    while cursor < end:
        stop = min(end - 1, cursor + span)
        response = session.get(URL, params={"resolution":"5m","symbol":SYMBOL,
            "start":str(cursor),"end":str(stop)},
            headers={"Accept":"application/json","User-Agent":"SaltyQuantSessionSweep/1.1"},
            timeout=40)
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") is not True:
            raise StudyError(f"Delta API unsuccessful response: {payload}")
        part = payload.get("result") or []
        if not isinstance(part, list) or len(part) > 1800:
            raise StudyError("Delta returned malformed candle list or exceeded 1800-row cap")
        rows.extend(part)
        cursor = stop + 1
        time.sleep(delay)
    if not rows:
        raise StudyError("No BTCUSD candles returned")
    data = pd.DataFrame(rows)
    if not {"time","open","high","low","close"}.issubset(data.columns):
        raise StudyError("Missing OHLC columns")
    data["timestamp"] = pd.to_datetime(pd.to_numeric(data.time,errors="raise"),unit="s",utc=True)
    for col in ("open","high","low","close","volume"):
        if col not in data:
            data[col] = 0.0
        data[col] = pd.to_numeric(data[col],errors="coerce")
    duplicate_count = int(data.timestamp.duplicated().sum())
    data = data.drop_duplicates("timestamp",keep="last").sort_values("timestamp").set_index("timestamp")
    values = data[["open","high","low","close","volume"]].to_numpy(float)
    if not np.isfinite(values).all():
        raise StudyError("Non-finite OHLCV")
    if (data[["open","high","low","close"]] <= 0).any().any():
        raise StudyError("Non-positive price")
    invalid = ((data.high < data[["open","close","low"]].max(axis=1))
               | (data.low > data[["open","close","high"]].min(axis=1)))
    if invalid.any():
        raise StudyError(f"Invalid OHLC rows: {int(invalid.sum())}")
    data = data[data.index + STEP <= pd.Timestamp.now(tz="UTC").floor("5min")]
    data["segment"] = data.index.to_series().diff().ne(STEP).cumsum().to_numpy()
    data.attrs["duplicate_count"] = duplicate_count
    if data.empty:
        raise StudyError("No valid closed BTCUSD candles")
    return data

def _is_sweep(row, range_high: float, range_low: float) -> tuple[bool,bool]:
    high_sweep = float(row.high) > range_high and float(row.close) < range_high
    low_sweep = float(row.low) < range_low and float(row.close) > range_low
    return high_sweep, low_sweep

def detect_events(data: pd.DataFrame) -> pd.DataFrame:
    x = data.copy()
    x["day"] = x.index.floor("D")
    x["minute"] = x.index.hour * 60 + x.index.minute
    rows = []
    for day, group in x.groupby("day",sort=True):
        asia = group[(group.minute >= 0) & (group.minute < 360)]
        expected = pd.date_range(day,periods=ASIA_BARS,freq=STEP,tz="UTC")
        # The full 6h range is mandatory: never calculate from a partial Asia session.
        if len(asia) != ASIA_BARS or not asia.index.equals(expected):
            continue
        if asia.segment.nunique() != 1:
            continue
        range_high = float(asia.high.max())
        range_low = float(asia.low.min())
        window = group[(group.minute >= 360) & (group.minute < 1080)]
        for signal_time, row in window.iterrows():
            high_sweep, low_sweep = _is_sweep(row,range_high,range_low)
            if high_sweep and low_sweep:
                continue
            if not (high_sweep or low_sweep):
                continue
            signal_i = data.index.get_indexer([signal_time])[0]
            entry_i = signal_i + 1
            if entry_i >= len(data):
                break
            entry_time = data.index[entry_i]
            if entry_time - signal_time != STEP or data.segment.iloc[entry_i] != row.segment:
                break
            side = -1 if high_sweep else 1
            rows.append({"signal_time":signal_time.isoformat(),
                "entry_time":entry_time.isoformat(),"day":str(day.date()),
                "side":"short" if side < 0 else "long","side_sign":side,
                "range_high":range_high,"range_low":range_low,
                "entry":float(data.open.iloc[entry_i]),
                "sweep_edge":"high" if high_sweep else "low"})
            break  # first qualifying event per UTC day; avoids event clustering
    return pd.DataFrame(rows)

def build_controls(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """One deterministic same-day/same-side non-sweep random-time control per event."""
    if events.empty:
        return pd.DataFrame()
    rng = np.random.default_rng(CONTROL_SEED)
    rows = []
    for event_id, event in enumerate(events.to_dict("records")):
        day = pd.Timestamp(event["day"],tz="UTC")
        start_i = data.index.searchsorted(day,side="left")
        end_i = data.index.searchsorted(day + pd.Timedelta(days=1),side="left")
        candidates = []
        signal_i = data.index.get_indexer([pd.Timestamp(event["signal_time"])])[0]
        for i in range(start_i,end_i):
            ts = data.index[i]
            minute = ts.hour * 60 + ts.minute
            if not (360 <= minute < 1080):
                continue
            if abs(i - signal_i) <= CONTROL_EXCLUSION_BARS:
                continue
            if i + max(HORIZONS.values()) - 1 >= len(data):
                continue
            if data.segment.iloc[i:i+max(HORIZONS.values())].nunique() != 1:
                continue
            row = data.iloc[i]
            high_sweep, low_sweep = _is_sweep(row,float(event["range_high"]),float(event["range_low"]))
            if high_sweep or low_sweep:
                continue
            candidates.append(i)
        if not candidates:
            continue
        chosen = int(rng.choice(candidates))
        rows.append({"event_id":event_id,"control_time":data.index[chosen].isoformat(),
            "day":event["day"],"side":event["side"],"side_sign":event["side_sign"],
            "entry":float(data.open.iloc[chosen])})
    return pd.DataFrame(rows)

def evaluate(data: pd.DataFrame, rows: pd.DataFrame, time_col: str,
             prefix: str) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    index = data.index
    output = []
    for item in rows.to_dict("records"):
        entry_time = pd.Timestamp(item[time_col])
        i = index.get_indexer([entry_time])[0]
        if i < 0:
            continue
        for horizon,bars in HORIZONS.items():
            j = i + bars - 1  # close at exactly entry + horizon, using 5m bar closes
            if j >= len(data) or data.segment.iloc[i:j+1].nunique() != 1:
                continue
            exit_price = float(data.close.iloc[j])
            gross = (exit_price / float(item["entry"]) - 1.0) * int(item["side_sign"]) * 100.0
            record = {**item,"horizon":horizon,"exit_time":index[j].isoformat(),
                "exit":exit_price,"gross_return_pct":gross}
            for bps in COSTS_BPS:
                record[f"net_{int(bps)}bps_pct"] = gross - 2*bps/100.0
            output.append(record)
    return pd.DataFrame(output)

def summarize_pair(event_returns: pd.DataFrame, control_returns: pd.DataFrame) -> dict:
    summary = {}
    for horizon in HORIZONS:
        e = event_returns[event_returns.horizon == horizon]
        c = control_returns[control_returns.horizon == horizon]
        if e.empty or c.empty:
            summary[horizon] = {"event_n":int(len(e)),"control_n":int(len(c)),
                "status":"insufficient paired observations"}
            continue
        # Pair by event_id so each event is compared with its own same-day/same-side control.
        paired = e.merge(c[["event_id","net_12bps_pct"]].rename(
            columns={"net_12bps_pct":"control_net_12bps_pct"}),on="event_id",how="inner")
        if paired.empty:
            summary[horizon] = {"event_n":int(len(e)),"control_n":int(len(c)),
                "status":"no paired observations"}
            continue
        delta = paired.net_12bps_pct - paired.control_net_12bps_pct
        summary[horizon] = {"paired_n":int(len(paired)),
            "event_mean_gross_pct":round(float(paired.gross_return_pct.mean()),5),
            "event_mean_net_12bps_pct":round(float(paired.net_12bps_pct.mean()),5),
            "control_mean_net_12bps_pct":round(float(paired.control_net_12bps_pct.mean()),5),
            "paired_mean_lift_pct":round(float(delta.mean()),5),
            "event_positive_fraction_net_12bps":round(float((paired.net_12bps_pct > 0).mean()),4),
            "control_positive_fraction_net_12bps":round(float((paired.control_net_12bps_pct > 0).mean()),4),
            "event_long_n":int((paired.side == "long").sum()),
            "event_short_n":int((paired.side == "short").sum()),
            "positive_event_month_fraction":round(float((paired.assign(
                month=pd.to_datetime(paired.entry_time,utc=True).dt.to_period("M"))
                .groupby("month").net_12bps_pct.mean() > 0).mean()),4)}
    return summary

def walk_forward(event_returns: pd.DataFrame, control_returns: pd.DataFrame) -> list[dict]:
    if event_returns.empty:
        return []
    dates = pd.to_datetime(event_returns.entry_time,utc=True)
    first = dates.min().floor("D")
    last = dates.max().floor("D")
    cursor = first + pd.DateOffset(months=6)
    folds = []
    while cursor <= last:
        end = cursor + pd.DateOffset(months=2)
        for horizon in HORIZONS:
            e = event_returns[(event_returns.horizon == horizon)
                & (pd.to_datetime(event_returns.entry_time,utc=True) >= cursor)
                & (pd.to_datetime(event_returns.entry_time,utc=True) < end)]
            c = control_returns[(control_returns.horizon == horizon)
                & (pd.to_datetime(control_returns.control_time,utc=True) >= cursor)
                & (pd.to_datetime(control_returns.control_time,utc=True) < end)]
            paired = e.merge(c[["event_id","net_12bps_pct"]].rename(
                columns={"net_12bps_pct":"control_net_12bps_pct"}),on="event_id",how="inner")
            folds.append({"validation_start":cursor.isoformat(),"validation_end":end.isoformat(),
                "horizon":horizon,"paired_n":int(len(paired)),
                "event_mean_net_12bps_pct":round(float(paired.net_12bps_pct.mean()),5) if len(paired) else None,
                "control_mean_net_12bps_pct":round(float(paired.control_net_12bps_pct.mean()),5) if len(paired) else None,
                "mean_lift_pct":round(float((paired.net_12bps_pct-paired.control_net_12bps_pct).mean()),5) if len(paired) else None})
        cursor = end
    return folds

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",type=int,default=730)
    parser.add_argument("--output-dir",default="research/results/session_sweep")
    args = parser.parse_args()
    if args.days < 240:
        raise SystemExit("--days must be at least 240 for the frozen 6m/2m evaluation blocks")
    output = Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=True)
    data = fetch_data(args.days)
    events = detect_events(data)
    if events.empty:
        raise StudyError("No qualifying events found; no performance result can be reported")
    controls = build_controls(data,events)
    event_returns = evaluate(data,events,"entry_time","event")
    control_returns = evaluate(data,controls,"control_time","control")
    if control_returns.empty:
        raise StudyError("No eligible same-day matched controls; cannot make an edge comparison")
    events.to_csv(output/"events.csv",index=False)
    controls.to_csv(output/"controls.csv",index=False)
    event_returns.to_csv(output/"event_forward_returns.csv",index=False)
    control_returns.to_csv(output/"control_forward_returns.csv",index=False)
    digest = hashlib.sha256(pd.util.hash_pandas_object(data,index=True).values.tobytes()).hexdigest()
    report = {"status":"completed","symbol":SYMBOL,"timeframe":"5m","bars":int(len(data)),
        "first_bar_utc":data.index.min().isoformat(),"last_bar_utc":data.index.max().isoformat(),
        "gap_count":int((data.index.to_series().diff() > STEP*1.5).sum()),
        "duplicate_count":int(data.attrs.get("duplicate_count",0)),
        "data_hash_pandas_object_sha256":digest,"event_count":int(len(events)),
        "matched_control_count":int(len(controls)),
        "definition":{"asia_utc":"00:00-06:00; all 72 five-minute candles required",
            "trade_window_utc":"06:00-18:00","entry":"next 5m open after sweep/re-entry close",
            "event_limit":"first qualifying event per UTC day","both_edges_same_bar":"ignored",
            "control":"one deterministic same-day, same-side random-time non-sweep bar per event; exclude +/-30m around signal",
            "horizons_bars":HORIZONS,"cost_sensitivity_round_trip_bps":COSTS_BPS,
            "control_rng_seed":CONTROL_SEED},
        "paired_summary":summarize_pair(event_returns,control_returns),
        "walk_forward_2m_blocks_after_6m_initial_period":walk_forward(event_returns,control_returns),
        "limitations":["This is a directional event study, not a stop/target trade backtest; no win-rate/PF/R/DD claim is appropriate.",
            "5m bars cannot resolve intrabar execution ambiguity for future stop/target designs.",
            "Round-trip cost values are sensitivity assumptions, not verified fees, spread, slippage or funding.",
            "The same-day random-time control is a descriptive matched benchmark, not a randomized causal experiment.",
            "No regime stratification or final separately sequestered holdout is included in this phase."]}
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__ == "__main__":
    main()
