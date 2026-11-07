"""EXP-002 fixed-hypothesis expansion for the independent Quant Discovery screen.

This runner adds seven distinct OHLCV-only families to the five EXP-001
baselines. It is research-only: no strategy is promoted or sent to Discord.
Signals are formed from closed bars and replayed at the next contiguous bar open.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import initial_screen as baseline
except ImportError:  # direct script execution from this directory
    import initial_screen as baseline


ASSETS = ("BTC", "ETH", "XAU")
TIMEFRAMES = ("15m", "1h")
EXPERIMENT_ID = "EXP-002"
EXPERIMENT_VERSION = 1
COST_SCENARIOS_BPS = (10.0, 20.0, 40.0)
WALK_FORWARD_FOLDS = (
    ("WF1", 0.50, 0.60),
    ("WF2", 0.60, 0.70),
    ("WF3", 0.70, 0.80),
    ("WF4", 0.80, 0.90),
    ("WF5", 0.90, 1.00),
)

HYPOTHESES = {
    "ema_crossover": "EMA20/EMA50 cross, only in the already-closed higher-timeframe EMA50/EMA200 direction.",
    "adx_dmi_trend": "A +DI/-DI directional cross with ADX >= 20, aligned to the already-closed higher-timeframe trend.",
    "macd_momentum": "MACD(12,26,9) histogram crosses zero, aligned to the already-closed higher-timeframe trend.",
    "bollinger_squeeze_breakout": "A prior 10-bar Bollinger-width squeeze followed by a 20-bar range and Bollinger-band break with above-average volume.",
    "utc_daily_vwap_reclaim": "Price crosses the current UTC-day anchored VWAP with above-average volume and higher-timeframe trend alignment.",
    "stochastic_trend_pullback": "Stochastic(14,3) crosses back out of an oversold/overbought area in the already-closed higher-timeframe trend direction.",
    "supertrend_flip": "Supertrend(14,3) flips direction in agreement with the already-closed higher-timeframe EMA trend.",
}

RESEARCH_RULES = {
    "signal_timing": "Signal is known only after its candle closes; entry is the next contiguous candle open.",
    "timeframes": "15m with closed 1h context; 1h with closed 4h context.",
    "stop": "1.2 x signal-bar ATR(14) for all EXP-002 families; fixed before replay.",
    "target": "2.0R fixed target; maximum hold 24 hours.",
    "overlap": "One position per asset/family/timeframe stream; no overlapping trades.",
    "ambiguous_bar": "If stop and target are touched in the same candle, stop is assumed first.",
    "gap": "A gap cancels a pending entry or exits an open position at the first observed post-gap open.",
    "splits": "Chronological 60% train / 20% validation / 20% untouched OOS.",
    "walk_forward": "Five sequential expanding out-of-sample folds from 50% to 100% of the sample.",
    "costs": "10/20/40 bps round trip plus the existing 1 bp per 8 hours adverse carry stress; carry is a stress assumption, not observed funding.",
    "promotion": "No automatic promotion. Results are descriptive hypotheses only.",
}


def _segment_ids(index: pd.DatetimeIndex, minutes: int) -> pd.Series:
    expected = pd.Timedelta(minutes=int(minutes))
    contiguous = pd.Series(index, index=index).diff().eq(expected)
    return (~contiguous).cumsum()


def _group_transform(values: pd.Series, segments: pd.Series, operation) -> pd.Series:
    return values.groupby(segments, group_keys=False).transform(operation)


def _supertrend_direction(frame: pd.DataFrame, segments: pd.Series, factor: float = 3.0) -> pd.Series:
    """Causal Supertrend direction; state is restarted after every timestamp gap."""
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    atr = frame["atr14"].to_numpy(dtype=float)
    segment_values = segments.to_numpy()
    upper = np.full(len(frame), np.nan, dtype=float)
    lower = np.full(len(frame), np.nan, dtype=float)
    direction = np.zeros(len(frame), dtype=int)

    for i in range(len(frame)):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        midpoint = (high[i] + low[i]) / 2.0
        basic_upper = midpoint + factor * atr[i]
        basic_lower = midpoint - factor * atr[i]
        if (
            i == 0
            or segment_values[i] != segment_values[i - 1]
            or not np.isfinite(upper[i - 1])
            or not np.isfinite(lower[i - 1])
        ):
            upper[i] = basic_upper
            lower[i] = basic_lower
            direction[i] = 1 if close[i] >= midpoint else -1
            continue

        previous_close = close[i - 1]
        upper[i] = (
            basic_upper
            if basic_upper < upper[i - 1] or previous_close > upper[i - 1]
            else upper[i - 1]
        )
        lower[i] = (
            basic_lower
            if basic_lower > lower[i - 1] or previous_close < lower[i - 1]
            else lower[i - 1]
        )
        previous_direction = direction[i - 1]
        if previous_direction < 0 and close[i] > upper[i - 1]:
            direction[i] = 1
        elif previous_direction > 0 and close[i] < lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = previous_direction

    return pd.Series(direction, index=frame.index, name="supertrend_direction")


def add_expanded_features(frame: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Add causal features; rolling and trend state never cross missing-bar gaps."""
    x = baseline.indicators(frame, minutes)
    segments = _segment_ids(x.index, minutes)

    ema12 = _group_transform(
        x["close"], segments,
        lambda values: values.ewm(span=12, adjust=False, min_periods=12).mean(),
    )
    ema26 = _group_transform(
        x["close"], segments,
        lambda values: values.ewm(span=26, adjust=False, min_periods=26).mean(),
    )
    macd = ema12 - ema26
    macd_signal = _group_transform(
        macd, segments,
        lambda values: values.ewm(span=9, adjust=False, min_periods=9).mean(),
    )
    x["macd_hist"] = macd - macd_signal

    # Directional movement index. The first bar of each segment has no prior
    # directional movement and remains NaN rather than being invented as zero.
    contiguous = pd.Series(x.index, index=x.index).diff().eq(pd.Timedelta(minutes=minutes))
    up_move = x["high"].diff().where(contiguous)
    down_move = (-x["low"].diff()).where(contiguous)
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    plus_dm = plus_dm.where(contiguous)
    minus_dm = minus_dm.where(contiguous)
    plus_smoothed = _group_transform(
        plus_dm, segments, lambda values: values.rolling(14, min_periods=14).mean()
    )
    minus_smoothed = _group_transform(
        minus_dm, segments, lambda values: values.rolling(14, min_periods=14).mean()
    )
    denominator = x["atr14"].replace(0, np.nan)
    x["plus_di"] = 100.0 * plus_smoothed / denominator
    x["minus_di"] = 100.0 * minus_smoothed / denominator
    di_sum = (x["plus_di"] + x["minus_di"]).replace(0, np.nan)
    dx = 100.0 * (x["plus_di"] - x["minus_di"]).abs() / di_sum
    x["adx14"] = _group_transform(
        dx, segments, lambda values: values.rolling(14, min_periods=14).mean()
    )

    middle = _group_transform(
        x["close"], segments, lambda values: values.rolling(20, min_periods=20).mean()
    )
    x["bb_width"] = (x["bb_high"] - x["bb_low"]) / middle.replace(0, np.nan)
    width_threshold = _group_transform(
        x["bb_width"], segments,
        lambda values: values.rolling(100, min_periods=50).quantile(0.20).shift(1),
    )
    squeeze_flag = x["bb_width"].le(width_threshold).fillna(False).astype(float)
    x["squeeze_recent"] = _group_transform(
        squeeze_flag, segments,
        lambda values: values.shift(1).rolling(10, min_periods=1).max(),
    ).gt(0.5)

    # UTC-day anchored VWAP. Each data-gap segment starts a fresh accumulator;
    # the first bar of a day cannot be mistaken for a VWAP cross.
    utc_day = pd.Series(x.index.normalize(), index=x.index)
    group_key = pd.MultiIndex.from_arrays([utc_day.to_numpy(), segments.to_numpy()])
    typical = (x["high"] + x["low"] + x["close"]) / 3.0
    cumulative_pv = (typical * x["volume"]).groupby(group_key).cumsum()
    cumulative_volume = x["volume"].groupby(group_key).cumsum().replace(0, np.nan)
    x["daily_vwap"] = cumulative_pv / cumulative_volume
    previous_close = x["close"].groupby(group_key).shift(1)
    previous_vwap = x["daily_vwap"].groupby(group_key).shift(1)
    x["vwap_cross_up"] = previous_close.le(previous_vwap) & x["close"].gt(x["daily_vwap"])
    x["vwap_cross_down"] = previous_close.ge(previous_vwap) & x["close"].lt(x["daily_vwap"])

    # Stochastic oscillator, reset at gaps.
    rolling_low = _group_transform(
        x["low"], segments, lambda values: values.rolling(14, min_periods=14).min()
    )
    rolling_high = _group_transform(
        x["high"], segments, lambda values: values.rolling(14, min_periods=14).max()
    )
    stochastic_range = (rolling_high - rolling_low).replace(0, np.nan)
    x["stoch_k"] = 100.0 * (x["close"] - rolling_low) / stochastic_range
    x["stoch_d"] = _group_transform(
        x["stoch_k"], segments, lambda values: values.rolling(3, min_periods=3).mean()
    )

    x["supertrend_direction"] = _supertrend_direction(x, segments)
    return x


def build_signals_from_frames(
    lower: pd.DataFrame,
    higher: pd.DataFrame,
    timeframe: str,
) -> tuple[pd.DataFrame, dict[str, np.ndarray], int]:
    """Build all seven fixed hypotheses from lower and higher timeframe bars."""
    if timeframe not in baseline.TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    minutes, higher_tf = baseline.TIMEFRAMES[timeframe]
    higher_minutes = baseline.TF_MINUTES[higher_tf]
    x = add_expanded_features(lower, minutes)
    higher_features = baseline.indicators(higher, higher_minutes)
    x = baseline.add_closed_htf_context(x, higher_features, higher_minutes, minutes)

    segments = _segment_ids(x.index, minutes)

    def previous(series: pd.Series) -> pd.Series:
        return series.groupby(segments).shift(1)

    up = x["ema50_y"].gt(x["ema200_y"])
    down = x["ema50_y"].lt(x["ema200_y"])
    prior_close = previous(x["close"])
    prior_ema20 = previous(x["ema20"])
    prior_ema50 = previous(x["ema50"])
    prior_macd_hist = previous(x["macd_hist"])
    prior_plus = previous(x["plus_di"])
    prior_minus = previous(x["minus_di"])
    prior_stoch_k = previous(x["stoch_k"])
    prior_stoch_d = previous(x["stoch_d"])
    prior_supertrend = previous(x["supertrend_direction"])
    prior_bb_high = previous(x["bb_high"])
    volume_confirm = x["volume"].gt(1.2 * x["volume_sma20"])

    ema_cross_up = x["ema20"].gt(x["ema50"]) & prior_ema20.le(prior_ema50)
    ema_cross_down = x["ema20"].lt(x["ema50"]) & prior_ema20.ge(prior_ema50)

    adx_cross_up = (
        x["plus_di"].gt(x["minus_di"])
        & prior_plus.le(prior_minus)
        & x["adx14"].ge(20.0)
    )
    adx_cross_down = (
        x["minus_di"].gt(x["plus_di"])
        & prior_minus.le(prior_plus)
        & x["adx14"].ge(20.0)
    )

    macd_cross_up = x["macd_hist"].gt(0) & prior_macd_hist.le(0)
    macd_cross_down = x["macd_hist"].lt(0) & prior_macd_hist.ge(0)

    squeeze_break_up = (
        x["squeeze_recent"]
        & x["close"].gt(x["bb_high"])
        & prior_close.le(prior_bb_high)
        & x["close"].gt(x["prior_high20"])
        & volume_confirm
    )
    squeeze_break_down = (
        x["squeeze_recent"]
        & x["close"].lt(x["bb_low"])
        & prior_close.ge(previous(x["bb_low"]))
        & x["close"].lt(x["prior_low20"])
        & volume_confirm
    )

    vwap_long = x["vwap_cross_up"] & volume_confirm & x["close"].gt(x["open"])
    vwap_short = x["vwap_cross_down"] & volume_confirm & x["close"].lt(x["open"])

    stochastic_long = (
        x["stoch_k"].gt(x["stoch_d"])
        & prior_stoch_k.le(prior_stoch_d)
        & x["stoch_k"].lt(35.0)
    )
    stochastic_short = (
        x["stoch_k"].lt(x["stoch_d"])
        & prior_stoch_k.ge(prior_stoch_d)
        & x["stoch_k"].gt(65.0)
    )

    supertrend_long = x["supertrend_direction"].eq(1) & prior_supertrend.eq(-1)
    supertrend_short = x["supertrend_direction"].eq(-1) & prior_supertrend.eq(1)

    signals = {
        "ema_crossover": np.where(
            up & ema_cross_up, 1, np.where(down & ema_cross_down, -1, 0)
        ).astype(int),
        "adx_dmi_trend": np.where(
            up & adx_cross_up, 1, np.where(down & adx_cross_down, -1, 0)
        ).astype(int),
        "macd_momentum": np.where(
            up & macd_cross_up, 1, np.where(down & macd_cross_down, -1, 0)
        ).astype(int),
        "bollinger_squeeze_breakout": np.where(
            up & squeeze_break_up, 1, np.where(down & squeeze_break_down, -1, 0)
        ).astype(int),
        "utc_daily_vwap_reclaim": np.where(
            up & vwap_long, 1, np.where(down & vwap_short, -1, 0)
        ).astype(int),
        "stochastic_trend_pullback": np.where(
            up & stochastic_long, 1, np.where(down & stochastic_short, -1, 0)
        ).astype(int),
        "supertrend_flip": np.where(
            up & supertrend_long, 1, np.where(down & supertrend_short, -1, 0)
        ).astype(int),
    }
    return x, signals, minutes


def build_signals(data_dir: Path, asset: str, timeframe: str):
    minutes, higher_tf = baseline.TIMEFRAMES[timeframe]
    lower = baseline.load_frame(data_dir, asset, timeframe)
    higher = baseline.load_frame(data_dir, asset, higher_tf)
    return build_signals_from_frames(lower, higher, timeframe)


def _months(frame: pd.DataFrame, start: int, end: int) -> float:
    if end - start < 2:
        return 0.1
    span = (frame.index[end - 1] - frame.index[start]).total_seconds()
    return max(span / 86400.0 / 30.4375, 0.1)


def run_experiments(data_dir: Path, output_dir: Path) -> dict[str, pd.DataFrame]:
    """Run fixed hypotheses and export auditable chronological result tables."""
    data_dir = Path(data_dir)
    manifest, validation = baseline.validate_archive(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    split_rows = []
    oos_rows = []
    regime_rows = []
    walk_rows = []
    trade_rows = []

    for asset in ASSETS:
        for timeframe in TIMEFRAMES:
            frame, signals, minutes = build_signals(data_dir, asset, timeframe)
            n = len(frame)
            c60 = int(n * 0.60)
            c80 = int(n * 0.80)
            for strategy_id, signal in signals.items():
                for split_name, start, end in (
                    ("TRAIN", 0, c60),
                    ("VALIDATION", c60, c80),
                    ("OOS", c80, n),
                ):
                    trades = baseline.simulate(
                        frame, signal, strategy_id, minutes, start, end
                    )
                    months = _months(frame, start, end)
                    metrics = baseline.summarize(trades, months, 10.0)
                    row = {
                        "experiment_id": EXPERIMENT_ID,
                        "asset": asset,
                        "timeframe": timeframe,
                        "strategy": strategy_id,
                        "split": split_name,
                        **metrics,
                    }
                    split_rows.append(row)
                    if split_name != "OOS":
                        continue

                    oos_rows.append({key: value for key, value in row.items() if key != "split"})
                    for regime in ("UP", "DOWN", "NEUTRAL"):
                        selected = [trade for trade in trades if trade["regime"] == regime]
                        regime_rows.append({
                            "asset": asset, "timeframe": timeframe,
                            "strategy": strategy_id, "regime": regime,
                            **baseline.summarize(selected, months, 10.0),
                        })
                    for regime in ("HIGH", "LOW"):
                        selected = [trade for trade in trades if trade["vol_regime"] == regime]
                        regime_rows.append({
                            "asset": asset, "timeframe": timeframe,
                            "strategy": strategy_id, "volatility_regime": regime,
                            **baseline.summarize(selected, months, 10.0),
                        })
                    for cost_bps in COST_SCENARIOS_BPS:
                        split_rows.append({
                            "experiment_id": EXPERIMENT_ID,
                            "asset": asset,
                            "timeframe": timeframe,
                            "strategy": strategy_id,
                            "split": f"OOS_COST_{int(cost_bps)}BPS",
                            **baseline.summarize(trades, months, cost_bps),
                        })
                    for trade in trades:
                        trade_rows.append({
                            "experiment_id": EXPERIMENT_ID,
                            "asset": asset,
                            "timeframe": timeframe,
                            "strategy": strategy_id,
                            **{
                                key: value.isoformat() if isinstance(value, pd.Timestamp) else value
                                for key, value in trade.items()
                            },
                        })

                for fold_name, start_fraction, end_fraction in WALK_FORWARD_FOLDS:
                    start = int(n * start_fraction)
                    end = min(n, int(n * end_fraction))
                    fold_trades = baseline.simulate(
                        frame, signal, strategy_id, minutes, start, end
                    )
                    walk_rows.append({
                        "experiment_id": EXPERIMENT_ID,
                        "asset": asset,
                        "timeframe": timeframe,
                        "strategy": strategy_id,
                        "fold": fold_name,
                        "test_start": frame.index[start].isoformat() if start < n else None,
                        "test_end": frame.index[end - 1].isoformat() if end > start else None,
                        **baseline.summarize(fold_trades, _months(frame, start, end), 10.0),
                    })

    outputs = {
        "oos_summary": pd.DataFrame(oos_rows),
        "split_and_cost_summary": pd.DataFrame(split_rows),
        "oos_regime_summary": pd.DataFrame(regime_rows),
        "walk_forward_summary": pd.DataFrame(walk_rows),
        "oos_trades": pd.DataFrame(trade_rows),
    }
    for name, table in outputs.items():
        table.to_csv(output_dir / f"exp002_{name}.csv", index=False)

    archive_manifest_path = data_dir / "manifest.json"
    run_manifest = {
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "source_commit": os.environ.get("GITHUB_SHA"),
        "source_archive_manifest_sha256": hashlib.sha256(
            archive_manifest_path.read_bytes()
        ).hexdigest(),
        "archive_validation_status": validation.get("status"),
        "archive_dataset_count": validation.get("actual_dataset_count"),
        "assets": list(ASSETS),
        "timeframes": list(TIMEFRAMES),
        "hypotheses": HYPOTHESES,
        "fixed_rules": RESEARCH_RULES,
        "cost_scenarios_bps_round_trip": list(COST_SCENARIOS_BPS),
        "funding_stress_bps_per_8h": baseline.FUNDING_STRESS_BPS_PER_8H,
        "notes": [
            "The 1 bp per 8h carry component is an adverse stress assumption, not observed funding attribution.",
            "This OHLCV replay does not include measured spread, order-book depth, market impact, or contract settlement conversion.",
            "These results do not validate a live or visual-AI strategy and never change the approved-strategy allowlist.",
        ],
    }
    (output_dir / "exp002_manifest.json").write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return outputs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="historical_data")
    parser.add_argument("--output-dir", default="quant_discovery/results")
    args = parser.parse_args(argv)
    outputs = run_experiments(Path(args.data_dir), Path(args.output_dir))
    print(outputs["oos_summary"].sort_values(
        ["expectancy_net_R", "n"], ascending=[False, False]
    ).to_string(index=False))
    print(f"Saved {len(outputs)} result tables and exp002_manifest.json to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
