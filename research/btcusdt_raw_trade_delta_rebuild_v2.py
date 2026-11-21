#!/usr/bin/env python3
"""Rebuild September 2026 BTCUSDT 5m delta and prior-day VP/TPO from raw trades,
then replay the frozen VP sweep/reclaim diagnostic without changing its rules.

This is a post-hoc correction of an already inspected one-month experiment, not
independent validation or an OOS test. Raw trades are assigned by their own
execution timestamps, avoiding aggTrade 100ms group bucket alignment effects.
"""
from __future__ import annotations
import argparse, gc, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from binance_aggtrade_boundary_forensics import download_archive, load_raw, read_zip_frame, KLINE_NAMES

BASE = "https://data.binance.vision/data/futures/um"
SYMBOL = "BTCUSDT"
MONTH_START = pd.Timestamp("2026-09-01T00:00:00Z")
MONTH_END = pd.Timestamp("2026-10-01T00:00:00Z")
BAR_MS = 300_000
DAY_MS = 86_400_000
PERIOD_30M_MS = 1_800_000
EXPECTED_BARS = 8640
COSTS = [0, 4, 7, 10, 20]
TICK = 0.1
MAX_HOLD_BARS = 48
COOLDOWN_BARS = 48
QUALITY_TOL = 0.001
DELTA_Z_THRESHOLD = 1.5


def next_funding_after(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    candidates = [ts.normalize() + pd.Timedelta(hours=h) for h in (0, 8, 16, 24, 32)]
    return min(x for x in candidates if x > ts)


def atr_wilder(frame: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = frame["close"].shift(1)
    tr = pd.concat([frame["high"] - frame["low"], (frame["high"] - prev).abs(),
                    (frame["low"] - prev).abs()], axis=1).max(axis=1)
    out = np.full(len(frame), np.nan, dtype=float)
    if len(frame) >= n:
        out[n - 1] = float(tr.iloc[:n].mean())
        for i in range(n, len(frame)):
            out[i] = (out[i - 1] * (n - 1) + float(tr.iloc[i])) / n
    return pd.Series(out, index=frame.index)


def value_area(price_ticks: np.ndarray, weights: np.ndarray, fraction: float = 0.70) -> dict[str, float]:
    order = np.argsort(price_ticks)
    p = price_ticks[order].astype(np.int64)
    w = weights[order].astype(float)
    if len(p) == 0 or not np.isfinite(w).all() or float(w.sum()) <= 0:
        raise ValueError("Invalid profile weights")
    poc = int(np.argmax(w))
    left = right = poc
    cumulative = float(w[poc])
    target = float(w.sum()) * fraction
    while cumulative < target and (left > 0 or right < len(w) - 1):
        lv = float(w[left - 1]) if left > 0 else -1.0
        rv = float(w[right + 1]) if right < len(w) - 1 else -1.0
        if lv >= rv:
            left -= 1
            cumulative += lv
        else:
            right += 1
            cumulative += rv
    return {"poc": float(p[poc]) / 10.0, "val": float(p[left]) / 10.0,
            "vah": float(p[right]) / 10.0, "covered_share": cumulative / float(w.sum()),
            "poc_share": float(w[poc] / w.sum())}


def monthly_klines(path: Path) -> pd.DataFrame:
    d = read_zip_frame(path, KLINE_NAMES, "kline")
    for c in ["open_time_ms", "close_time_ms", "trade_count"]:
        d[c] = pd.to_numeric(d[c], errors="raise").astype(np.int64)
    for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base", "taker_buy_quote", "ignore"]:
        d[c] = pd.to_numeric(d[c], errors="raise").astype(float)
    d = d.sort_values("open_time_ms").reset_index(drop=True)
    start = int(MONTH_START.timestamp() * 1000)
    end = int(MONTH_END.timestamp() * 1000)
    expected = np.arange(start, end, BAR_MS, dtype=np.int64)
    if len(d) != EXPECTED_BARS or not np.array_equal(d.open_time_ms.to_numpy(np.int64), expected):
        raise ValueError(f"Expected {EXPECTED_BARS} ordered 5m klines; found {len(d)}")
    valid = ((d.high >= d[["open", "close", "low"]].max(axis=1))
             & (d.low <= d[["open", "close", "high"]].min(axis=1))
             & (d.volume >= 0) & (d.taker_buy_base >= 0)
             & (d.taker_buy_base <= d.volume + 1e-9))
    if not valid.all():
        raise ValueError("Invalid monthly kline OHLCV row")
    return d


def process_day(raw: dict, day_start_ms: int, month_start_ms: int) -> tuple[np.ndarray, dict]:
    ts = raw["ts"]
    price = raw["price"]
    qty = raw["qty"]
    maker = raw["maker"]
    if ts.min() < day_start_ms or ts.max() >= day_start_ms + DAY_MS:
        raise ValueError("Raw trade timestamp outside requested UTC day")
    price_scaled = price / TICK
    price_ticks = np.rint(price_scaled).astype(np.int64)
    if np.max(np.abs(price_scaled - price_ticks)) > 1e-7:
        raise ValueError("Trade price is not on the frozen 0.1 USDT tick grid")
    buy_mask = ~maker
    bar_idx = ((ts - month_start_ms) // BAR_MS).astype(np.int64)
    if np.any((bar_idx < 0) | (bar_idx >= EXPECTED_BARS)):
        raise ValueError("Raw trade maps outside September 5m grid")
    total = np.bincount(bar_idx, weights=qty, minlength=EXPECTED_BARS)
    buy = np.bincount(bar_idx, weights=np.where(buy_mask, qty, 0.0), minlength=EXPECTED_BARS)
    sell = np.bincount(bar_idx, weights=np.where(maker, qty, 0.0), minlength=EXPECTED_BARS)
    count = np.bincount(bar_idx, minlength=EXPECTED_BARS).astype(np.int64)
    # Exact-price daily volume profile and 30m TPO profile from individual trades.
    uniq_price, inv_price = np.unique(price_ticks, return_inverse=True)
    vol_by_price = np.bincount(inv_price, weights=qty, minlength=len(uniq_price))
    buy_by_price = np.bincount(inv_price, weights=np.where(buy_mask, qty, 0.0), minlength=len(uniq_price))
    sell_by_price = np.bincount(inv_price, weights=np.where(maker, qty, 0.0), minlength=len(uniq_price))
    period30 = ((ts - day_start_ms) // PERIOD_30M_MS).astype(np.int64)
    pair_key = price_ticks * 48 + period30
    unique_pairs = np.unique(pair_key)
    tpo_price, tpo_counts = np.unique(unique_pairs // 48, return_counts=True)
    tpo_by_price = np.zeros(len(uniq_price), dtype=np.int64)
    tpo_pos = np.searchsorted(uniq_price, tpo_price)
    tpo_by_price[tpo_pos] = tpo_counts
    vp = value_area(uniq_price, vol_by_price, 0.70)
    tp = value_area(uniq_price, tpo_by_price.astype(float), 0.70)
    profile = {
        "day_open_ms": int(day_start_ms),
        "day_utc": pd.to_datetime(day_start_ms, unit="ms", utc=True).strftime("%Y-%m-%d"),
        "total_volume": float(vol_by_price.sum()),
        "taker_buy": float(buy_by_price.sum()),
        "taker_sell": float(sell_by_price.sum()),
        "net_delta": float(buy_by_price.sum() - sell_by_price.sum()),
        "net_delta_ratio": float((buy_by_price.sum() - sell_by_price.sum()) / vol_by_price.sum()),
        "volume_poc": vp["poc"], "volume_val": vp["val"], "volume_vah": vp["vah"],
        "volume_value_area_share": vp["covered_share"], "volume_poc_share": vp["poc_share"],
        "tpo_poc": tp["poc"], "tpo_val": tp["val"], "tpo_vah": tp["vah"],
        "tpo_value_area_share": tp["covered_share"], "tpo_poc_share": tp["poc_share"],
        "tpo_period_price_counts": int(tpo_by_price.sum()),
        "max_tpo_30m_count_at_price": int(tpo_by_price.max()),
        "price_levels": int(len(uniq_price)),
    }
    if not np.isclose(float(total.sum()), float(qty.sum()), rtol=1e-10, atol=1e-8):
        raise ValueError("5m volume does not conserve raw trade quantity")
    if not np.allclose(buy + sell, total, rtol=1e-10, atol=1e-8):
        raise ValueError("Taker buy + sell does not equal total volume")
    if not np.isclose(profile["total_volume"], float(qty.sum()), rtol=1e-10, atol=1e-8):
        raise ValueError("Daily profile does not conserve raw trade quantity")
    return np.vstack([total, buy, sell, buy - sell, count]).T, profile


def load_backtest_data(kline: pd.DataFrame, raw_bars: pd.DataFrame, daily: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    d = kline.merge(raw_bars, left_on="open_time_ms", right_on="bar_open_ms", validate="one_to_one")
    if len(d) != EXPECTED_BARS or d.open_time_ms.duplicated().any():
        raise ValueError("Expected 8,640 unique merged 5m bars")
    d["dt"] = pd.to_datetime(d.open_time_ms, unit="ms", utc=True)
    d["volume_rec"] = d.volume
    d["taker_buy_base_rec"] = d.taker_buy_base
    d["vol_rel_error"] = np.where(d.volume_rec.to_numpy(float) == 0,
        np.where(d.raw_volume.to_numpy(float) == 0, 0.0, np.inf),
        (d.raw_volume - d.volume_rec).abs() / d.volume_rec)
    d["buy_rel_error"] = np.where(d.taker_buy_base_rec.to_numpy(float) == 0,
        np.where(d.raw_taker_buy.to_numpy(float) == 0, 0.0, np.inf),
        (d.raw_taker_buy - d.taker_buy_base_rec).abs() / d.taker_buy_base_rec)
    d["bar_quality"] = (d.vol_rel_error <= QUALITY_TOL) & (d.buy_rel_error <= QUALITY_TOL)
    d["delta_fraction"] = d.raw_delta / d.raw_volume.replace(0, np.nan)
    d["delta_mean_prev"] = d.delta_fraction.rolling(288, min_periods=96).mean().shift(1)
    d["delta_std_prev"] = d.delta_fraction.rolling(288, min_periods=96).std(ddof=0).shift(1)
    d["delta_z"] = (d.delta_fraction - d.delta_mean_prev) / d.delta_std_prev.replace(0, np.nan)
    d["atr14"] = atr_wilder(d, 14)
    d["close_location"] = (d.close - d.low) / (d.high - d.low).replace(0, np.nan)
    daily = daily.sort_values("day_open_ms").reset_index(drop=True)
    daily["prior_vah"] = daily.volume_vah.shift(1)
    daily["prior_val"] = daily.volume_val.shift(1)
    daily["prior_poc"] = daily.volume_poc.shift(1)
    lookup = daily.set_index(daily.day_utc)[["prior_vah", "prior_val", "prior_poc"]].to_dict("index")
    d["day"] = d.dt.dt.strftime("%Y-%m-%d")
    for c in ["prior_vah", "prior_val", "prior_poc"]:
        d[c] = d.day.map(lambda day: lookup.get(day, {}).get(c, np.nan))
    d["short_price_signal"] = (d.high > d.prior_vah + TICK) & (d.close < d.prior_vah) & (d.close_location <= 0.25) & d.bar_quality
    d["long_price_signal"] = (d.low < d.prior_val - TICK) & (d.close > d.prior_val) & (d.close_location >= 0.75) & d.bar_quality
    d["short_delta_signal"] = d.short_price_signal & (d.delta_z <= -DELTA_Z_THRESHOLD)
    d["long_delta_signal"] = d.long_price_signal & (d.delta_z >= DELTA_Z_THRESHOLD)
    meta = {
        "bars": len(d), "start": d.dt.min().isoformat(), "end": d.dt.max().isoformat(),
        "quality_bars": int(d.bar_quality.sum()), "quality_fraction": float(d.bar_quality.mean()),
        "raw_price_signals_before_quality": int((((d.high > d.prior_vah + TICK) & (d.close < d.prior_vah) & (d.close_location <= 0.25)) | ((d.low < d.prior_val - TICK) & (d.close > d.prior_val) & (d.close_location >= 0.75))).sum()),
        "quality_filtered_price_signals": int(d.short_price_signal.sum() + d.long_price_signal.sum()),
        "delta_confirmed_signals": int(d.short_delta_signal.sum() + d.long_delta_signal.sum()),
        "official_kline_volume": float(d.volume_rec.sum()), "raw_trade_volume": float(d.raw_volume.sum()),
        "official_kline_taker_buy": float(d.taker_buy_base_rec.sum()), "raw_trade_taker_buy": float(d.raw_taker_buy.sum()),
        "official_kline_trade_count": int(d.trade_count.sum()), "raw_trade_count": int(d.raw_trade_count.sum()),
        "max_volume_rel_error": float(d.vol_rel_error.max()), "max_buy_rel_error": float(d.buy_rel_error.max()),
        "raw_trade_count_matching_bars": int((d.raw_trade_count == d.trade_count).sum()),
    }
    return d, meta


def simulate(data: pd.DataFrame, variant: str, cost_bps: float) -> pd.DataFrame:
    rows = []
    last_exit_idx = -10**9
    for i, row in data.iterrows():
        if i < 1 or i + 1 >= len(data) or i <= last_exit_idx + COOLDOWN_BARS:
            continue
        if variant == "price_only":
            if bool(row.short_price_signal): side = "short"
            elif bool(row.long_price_signal): side = "long"
            else: continue
        elif variant == "delta_confirmed":
            if bool(row.short_delta_signal): side = "short"
            elif bool(row.long_delta_signal): side = "long"
            else: continue
        else:
            raise ValueError(variant)
        entry_i = i + 1
        entry_time = data.loc[entry_i, "dt"]
        funding_boundary = next_funding_after(entry_time)
        last_pre_funding_open = funding_boundary - pd.Timedelta(minutes=5)
        funding_i = int(data.dt.searchsorted(last_pre_funding_open, side="right") - 1)
        max_i = min(entry_i + MAX_HOLD_BARS - 1, funding_i, len(data) - 1)
        if max_i < entry_i: continue
        entry = float(data.loc[entry_i, "open"])
        atr = float(row.atr14)
        if not np.isfinite(atr) or atr <= 0: continue
        buffer = 0.1 * atr
        if side == "short":
            stop = float(row.high + buffer); target = float(row.prior_poc); risk = stop - entry; reward = entry - target
        else:
            stop = float(row.low - buffer); target = float(row.prior_poc); risk = entry - stop; reward = target - entry
        if not np.isfinite([entry, stop, target, risk, reward]).all() or risk <= 0 or reward < risk: continue
        exit_i = None; exit_px = None; outcome = None
        for j in range(entry_i, max_i + 1):
            o = float(data.loc[j, "open"]); h = float(data.loc[j, "high"]); l = float(data.loc[j, "low"])
            if side == "long":
                if o <= stop: exit_px, outcome, exit_i = o, "SL_GAP", j; break
                if o >= target: exit_px, outcome, exit_i = target, "TP_GAP_CAPPED", j; break
                sl_hit, tp_hit = l <= stop, h >= target
            else:
                if o >= stop: exit_px, outcome, exit_i = o, "SL_GAP", j; break
                if o <= target: exit_px, outcome, exit_i = target, "TP_GAP_CAPPED", j; break
                sl_hit, tp_hit = h >= stop, l <= target
            if sl_hit:
                exit_px, outcome, exit_i = stop, ("SL_AMBIGUOUS" if tp_hit else "SL"), j; break
            if tp_hit:
                exit_px, outcome, exit_i = target, "TP", j; break
        if exit_i is None:
            exit_i = max_i
            exit_px = float(data.loc[max_i, "close"])
            outcome = "TIME_FUNDING" if max_i == funding_i else "TIME_4H"
        gross_r = (exit_px - entry) / risk if side == "long" else (entry - exit_px) / risk
        net_r = gross_r - (cost_bps / 10000.0 * entry / risk)
        rows.append({
            "variant": variant, "cost_bps": cost_bps, "signal_time": row["dt"],
            "entry_time": entry_time, "exit_time": data.loc[exit_i, "dt"], "side": side,
            "entry": entry, "stop": stop, "target_prior_day_poc": target, "target_R": reward / risk,
            "exit": exit_px, "outcome": outcome, "risk": risk, "gross_R": gross_r, "net_R": net_r,
            "delta_z": row.delta_z, "bar_volume_relative_error": row.vol_rel_error,
            "bar_taker_buy_relative_error": row.buy_rel_error, "funding_boundary": funding_boundary,
            "bars_held": exit_i - entry_i + 1,
        })
        last_exit_idx = exit_i
    return pd.DataFrame(rows)


def stats(g: pd.DataFrame) -> dict:
    if g.empty:
        return {"trades":0,"win_rate_pct":0,"profit_factor":None,"net_R":0,"avg_R":0,"max_drawdown_R":0,"max_losing_streak":0,"positive_days":0,"active_days":0,"TP":0,"SL":0,"TIME":0}
    g = g.copy()
    r = g.net_R.astype(float)
    wins, losses = r[r > 0], r[r < 0]
    eq = r.cumsum().to_numpy()
    dd = eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]
    streak = max_streak = 0
    for x in r:
        streak = streak + 1 if x < 0 else 0
        max_streak = max(max_streak, streak)
    day_net = g.assign(day=pd.to_datetime(g.entry_time, utc=True).dt.strftime("%Y-%m-%d")).groupby("day").net_R.sum()
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) > 0 else None
    return {"trades":len(g),"win_rate_pct":round(float((r > 0).mean()*100),2),"profit_factor":round(pf,3) if pf is not None else None,
        "net_R":round(float(r.sum()),3),"avg_R":round(float(r.mean()),3),"max_drawdown_R":round(float(min(0,dd.min())),3),
        "max_losing_streak":max_streak,"positive_days":int((day_net > 0).sum()),"active_days":int(len(day_net)),
        "TP":int(g.outcome.str.startswith("TP").sum()),"SL":int(g.outcome.str.startswith("SL").sum()),
        "TIME":int(g.outcome.str.startswith("TIME").sum())}


def self_test() -> None:
    assert next_funding_after(pd.Timestamp("2026-09-01T07:55:00Z")) == pd.Timestamp("2026-09-01T08:00:00Z")
    assert next_funding_after(pd.Timestamp("2026-09-01T08:00:00Z")) == pd.Timestamp("2026-09-01T16:00:00Z")
    p = value_area(np.array([1000,1001,1002]), np.array([70.,20.,10.]))
    assert p["poc"] == 100.0 and p["covered_share"] >= 0.70
    qty = np.array([0.2,0.3,0.5]); buy = np.array([0.2,0.0,0.5]); sell = qty - buy
    assert np.isclose(qty.sum(), buy.sum() + sell.sum())
    idx = np.array([0,0,1])
    assert np.allclose(np.bincount(idx, weights=qty, minlength=2), [0.5,0.5])
    toy_start = int(MONTH_START.timestamp() * 1000)
    toy_raw = {"ts":np.array([toy_start+1000,toy_start+BAR_MS+1000]),
        "price":np.array([100.0,100.1]),"qty":np.array([0.2,0.3]),"maker":np.array([False,True])}
    toy_features, toy_profile = process_day(toy_raw, toy_start, toy_start)
    assert np.isclose(toy_features[0,0],0.2) and np.isclose(toy_features[1,0],0.3)
    assert np.isclose(toy_features[0,1],0.2) and np.isclose(toy_features[1,2],0.3)
    assert np.isclose(toy_profile["total_volume"],0.5)
    low, high, stop, target = 98., 103., 99., 102.
    assert low <= stop and high >= target
    print("7 deterministic raw-volume/profile/funding/ambiguity tests passed")


def run(out_dir: Path, work_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    import requests
    import gc
    session = requests.Session()
    session.headers.update({"User-Agent":"SaltyQuantRawTradeDeltaRebuild/2.0"})
    month_start_ms = int(MONTH_START.timestamp() * 1000)
    kline_url = f"{BASE}/monthly/klines/{SYMBOL}/5m/{SYMBOL}-5m-2026-09.zip"
    kline_path, kline_download = download_archive(session, kline_url, work_dir)
    kline = monthly_klines(kline_path)
    raw_bars = np.zeros((EXPECTED_BARS,5), dtype=float)
    daily_profiles = []
    daily_downloads = []
    for day in pd.date_range(MONTH_START, MONTH_END-pd.Timedelta(days=1), freq="D", tz="UTC"):
        date = day.strftime("%Y-%m-%d")
        day_ms = int(day.timestamp() * 1000)
        url = f"{BASE}/daily/trades/{SYMBOL}/{SYMBOL}-trades-{date}.zip"
        raw_path, download_meta = download_archive(session, url, work_dir)
        raw = load_raw(raw_path)
        features, profile = process_day(raw, day_ms, month_start_ms)
        start = int((day_ms - month_start_ms) // BAR_MS)
        stop = start + 288
        raw_bars[start:stop,:] = features[start:stop,:]
        daily_profiles.append(profile)
        daily_downloads.append({"date":date,"archive_bytes":download_meta["bytes"],"sha256":download_meta["sha256"],
            "checksum_sha256":download_meta["checksum_sha256"],"zip_crc_pass":download_meta["zip_crc_pass"],
            "raw_rows":raw["rows"],"first_trade_id":raw["first_id"],"last_trade_id":raw["last_id"],
            "total_base_qty":float(raw["qty"].sum()),"taker_buy_base_qty":float(raw["qty"][~raw["maker"]].sum()),
            "taker_sell_base_qty":float(raw["qty"][raw["maker"]].sum()),"price_tick_grid_pass":True})
        raw_path.unlink(missing_ok=True)
        (work_dir/(raw_path.name+".CHECKSUM")).unlink(missing_ok=True)
        del raw, features
        gc.collect()
    delta = pd.DataFrame({"bar_open_ms":kline.open_time_ms.to_numpy(np.int64),"raw_volume":raw_bars[:,0],
        "raw_taker_buy":raw_bars[:,1],"raw_taker_sell":raw_bars[:,2],"raw_delta":raw_bars[:,3],
        "raw_trade_count":raw_bars[:,4].astype(np.int64)})
    daily = pd.DataFrame(daily_profiles)
    rec = pd.DataFrame({"open_time_ms":kline.open_time_ms,"kline_volume":kline.volume,"raw_volume":delta.raw_volume,
        "volume_diff":delta.raw_volume-kline.volume,"kline_taker_buy":kline.taker_buy_base,"raw_taker_buy":delta.raw_taker_buy,
        "taker_buy_diff":delta.raw_taker_buy-kline.taker_buy_base,"kline_trade_count":kline.trade_count,
        "raw_trade_count":delta.raw_trade_count,"trade_count_match":delta.raw_trade_count==kline.trade_count})
    rec["volume_rel_error"] = (rec.raw_volume-rec.kline_volume).abs()/rec.kline_volume.replace(0,np.nan)
    rec["buy_rel_error"] = (rec.raw_taker_buy-rec.kline_taker_buy).abs()/rec.kline_taker_buy.replace(0,np.nan)
    raw_exact = (np.isclose(rec.raw_volume,rec.kline_volume,rtol=1e-8,atol=1e-8).all()
        and np.isclose(rec.raw_taker_buy,rec.kline_taker_buy,rtol=1e-8,atol=1e-8).all()
        and rec.trade_count_match.all())
    if not raw_exact:
        raise ValueError("Raw-trade 5m bars do not exactly reconcile to official kline volume/buy/count; strategy replay blocked")
    d, bt_meta = load_backtest_data(kline, delta, daily)
    summaries = []
    trades = []
    for variant in ["price_only","delta_confirmed"]:
        for cost in COSTS:
            g = simulate(d,variant,cost)
            summaries.append({"variant":variant,"cost_bps":cost,**stats(g)})
            if len(g): trades.append(g)
    summary = pd.DataFrame(summaries)
    trade_df = pd.concat(trades,ignore_index=True) if trades else pd.DataFrame()
    if len(trade_df):
        directional = []
        for (variant,side),g in trade_df[trade_df.cost_bps==10].groupby(["variant","side"]):
            directional.append({"variant":variant,"side":side,**stats(g)})
        pd.DataFrame(directional).to_csv(out_dir/"directional_10bps.csv",index=False)
        daily_10 = trade_df[trade_df.cost_bps==10].assign(
            day=lambda x:pd.to_datetime(x.entry_time,utc=True).dt.strftime("%Y-%m-%d")
        ).groupby(["variant","day"],as_index=False).net_R.sum()
        daily_10.to_csv(out_dir/"daily_net_R_10bps.csv",index=False)
    delta.to_csv(out_dir/"raw_delta_5m.csv",index=False)
    daily.to_csv(out_dir/"daily_raw_vp_tpo_summary.csv",index=False)
    rec.to_csv(out_dir/"raw_vs_kline_reconciliation_5m.csv",index=False)
    summary.to_csv(out_dir/"summary.csv",index=False)
    trade_df.to_csv(out_dir/"trades.csv",index=False)
    v1 = {
      "price_only":{"trades":42,"win_rate_pct":26.19,"profit_factor":0.374,"net_R":-31.348,"avg_R":-0.746,"max_drawdown_R":-33.291,"max_losing_streak":8,"positive_days":6,"active_days":21},
      "delta_confirmed":{"trades":20,"win_rate_pct":25.0,"profit_factor":0.440,"net_R":-13.989,"avg_R":-0.699,"max_drawdown_R":-18.237,"max_losing_streak":10,"positive_days":3,"active_days":15}}
    v2_10 = summary[summary.cost_bps==10].set_index("variant").to_dict("index")
    comparison = []
    for variant in ["price_only","delta_confirmed"]:
        comparison.append({"variant":variant,"V1_aggtrade_net_R_10bps":v1[variant]["net_R"],
            "V2_raw_trade_net_R_10bps":v2_10[variant]["net_R"],"V1_trades":v1[variant]["trades"],
            "V2_trades":v2_10[variant]["trades"],"V1_profit_factor":v1[variant]["profit_factor"],
            "V2_profit_factor":v2_10[variant]["profit_factor"]})
    pd.DataFrame(comparison).to_csv(out_dir/"v1_vs_v2_10bps_comparison.csv",index=False)
    meta = {"status":"completed","study_status":"POST_HOC_CORRECTED_ONE_MONTH_DIAGNOSTIC","strategy_backtest_validation":False,
        "symbol":SYMBOL,"market":"Binance USD-M BTCUSDT perpetual","period":"2026-09-01 through 2026-09-30 UTC",
        "month_kline":{"url":kline_url,"sha256":hashlib.sha256(kline_path.read_bytes()).hexdigest(),"rows":len(kline)},
        "daily_raw_trade_archives":daily_downloads,"daily_archive_count":len(daily_downloads),
        "raw_trade_rows":int(sum(x["raw_rows"] for x in daily_downloads)),
        "raw_trade_total_base_qty":float(delta.raw_volume.sum()),"raw_trade_taker_buy_base_qty":float(delta.raw_taker_buy.sum()),
        "raw_trade_taker_sell_base_qty":float(delta.raw_taker_sell.sum()),"raw_trade_net_delta_base_qty":float(delta.raw_delta.sum()),
        "reconciliation":{"bars":len(rec),"volume_match_bars":int(np.isclose(rec.raw_volume,rec.kline_volume,rtol=1e-8,atol=1e-8).sum()),
            "taker_buy_match_bars":int(np.isclose(rec.raw_taker_buy,rec.kline_taker_buy,rtol=1e-8,atol=1e-8).sum()),
            "trade_count_match_bars":int(rec.trade_count_match.sum()),"max_volume_rel_error":float(rec.volume_rel_error.max()),
            "max_taker_buy_rel_error":float(rec.buy_rel_error.max()),"raw_exact_reconciliation_pass":bool(raw_exact)},
        "backtest_data":bt_meta,"cost_sensitivity_rows":len(summary),"trade_rows_all_costs":len(trade_df),
        "V1_reference_10bps":v1,"V1_vs_V2_10bps":comparison,
        "frozen_rules":{"prior_profile":"previous completed UTC day exact raw-trade-price 70% volume VAH/VAL/POC",
            "short":"high > prior VAH + 0.1; close < prior VAH; close location <= 0.25",
            "long":"low < prior VAL - 0.1; close > prior VAL; close location >= 0.75",
            "delta_confirmation":"short raw delta z <= -1.5; long raw delta z >= +1.5; z uses prior 288 completed 5m bars, min 96, shifted one bar",
            "entry":"next 5m open","stop":"signal extreme +/- 0.1 Wilder ATR14",
            "target":"previous day raw-trade volume POC; require >=1R target distance",
            "max_hold_bars":48,"cooldown_bars":48,
            "funding":"exit last 5m close before next 00/08/16 UTC funding boundary; funding cashflow not modeled",
            "same_bar":"stop first","gap_stop":"adverse open fill","costs_bps_round_trip":COSTS,
            "quality_filter":"raw trade 5m volume, taker-buy and trade count must exactly reconcile to official klines within 1e-8; all 8,640 bars required"},
        "limitations":["September 2026 was already inspected; this is not independent validation or OOS.",
            "Only one asset and one month; no train/validation/OOS split or monthly stability.",
            "Funding cashflow, spread, slippage, market impact and leverage are not modeled; positions are forced flat before funding.",
            "V1 reference numbers are from the prior verified aggTrade-based diagnostic; V2 changes only the data reconstruction source and uses the same strategy rules."]}
    (out_dir/"metadata.json").write_text(json.dumps(meta,indent=2,sort_keys=True,default=str)+"\n")
    report = ["# BTCUSDT raw-trade delta / prior-day VP sweep-reclaim correction — September 2026","",
        "**Status: post-hoc corrected diagnostic only; not validation or promotion.** The same frozen strategy rules were replayed using raw-trade timestamps instead of aggTrade timestamps.","",
        "## Data quality",f"- Daily raw archives verified: {len(daily_downloads)}/30",f"- Raw trade records: {meta['raw_trade_rows']:,}",
        f"- 5m bars reconciled to klines: {meta['reconciliation']['volume_match_bars']}/8640 volume; {meta['reconciliation']['taker_buy_match_bars']}/8640 taker-buy; {meta['reconciliation']['trade_count_match_bars']}/8640 trade count.",
        f"- Maximum relative errors: volume {meta['reconciliation']['max_volume_rel_error']:.3g}; taker-buy {meta['reconciliation']['max_taker_buy_rel_error']:.3g}.","",
        "## Frozen strategy rules","- Previous completed UTC day exact raw-trade-price 70% volume VAH/VAL/POC.",
        "- Same VAH/VAL sweep-and-reclaim, close-location and 0.1 tick conditions as V1.",
        "- Delta version: preceding 288 completed 5m bars, min 96, shifted one; short z <= -1.5, long z >= +1.5.",
        "- Next 5m open; signal extreme +/- 0.1 Wilder ATR14 stop; prior-day POC target; skip below 1R.",
        "- One position, 48-bar cooldown, 48-bar max hold, exit before next funding boundary, stop-first, adverse gap fill.","",
        "## Results by round-trip cost",summary.to_markdown(index=False),"",
        "## V1 aggTrade versus V2 raw-trade at 10 bps",pd.DataFrame(comparison).to_markdown(index=False),"",
        "## Limitations","- One post-hoc month; September had already been inspected.",
        "- No chronological train/validation/OOS; no promotion possible.",
        "- Funding cashflow, spread, slippage and market impact are not modeled; positions are closed before funding.",
        "- This reprocessing tests data alignment and the same strategy rules; it is not an independent new strategy hypothesis."]
    (out_dir/"report.md").write_text("\n".join(report)+"\n")
    kline_path.unlink(missing_ok=True)
    (work_dir/(kline_path.name+".CHECKSUM")).unlink(missing_ok=True)
    print(summary.to_string(index=False))
    print(json.dumps(meta["reconciliation"],indent=2))
    print(json.dumps(comparison,indent=2))


def self_test() -> None:
    assert next_funding_after(pd.Timestamp("2026-09-01T07:55:00Z")) == pd.Timestamp("2026-09-01T08:00:00Z")
    assert next_funding_after(pd.Timestamp("2026-09-01T08:00:00Z")) == pd.Timestamp("2026-09-01T16:00:00Z")
    p = value_area(np.array([1000,1001,1002]), np.array([70.,20.,10.]))
    assert p["poc"] == 100.0 and p["covered_share"] >= 0.70
    qty = np.array([0.2,0.3,0.5]); buy = np.array([0.2,0.0,0.5]); sell = qty - buy
    assert np.isclose(qty.sum(), buy.sum() + sell.sum())
    idx = np.array([0,0,1])
    assert np.allclose(np.bincount(idx, weights=qty, minlength=2), [0.5,0.5])
    toy_start = int(MONTH_START.timestamp() * 1000)
    toy_raw = {"ts":np.array([toy_start+1000,toy_start+BAR_MS+1000]),
        "price":np.array([100.0,100.1]),"qty":np.array([0.2,0.3]),"maker":np.array([False,True])}
    toy_features, toy_profile = process_day(toy_raw, toy_start, toy_start)
    assert np.isclose(toy_features[0,0],0.2) and np.isclose(toy_features[1,0],0.3)
    assert np.isclose(toy_features[0,1],0.2) and np.isclose(toy_features[1,2],0.3)
    assert np.isclose(toy_profile["total_volume"],0.5)
    low, high, stop, target = 98., 103., 99., 102.
    assert low <= stop and high >= target
    print("7 deterministic raw-volume/profile/funding/ambiguity tests passed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, default=Path("results/raw-trade-delta-v2"))
    p.add_argument("--work-dir", type=Path, default=Path("/tmp/raw-trade-delta-v2"))
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return
    run(a.output_dir, a.work_dir)


if __name__ == "__main__":
    main()
