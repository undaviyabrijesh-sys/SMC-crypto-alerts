"""EXP-003: research-only prequential selection across independent strategy shadow trades."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd

EXPERIMENT_ID = "EXP-003"
TIMEFRAME_MINUTES = {"15m": 15, "1h": 60}
COST_SCENARIOS_BPS = (10.0, 20.0, 40.0)
CARRY_STRESS_BPS_PER_8H = 1.0  # stress assumption, not observed funding
POLICIES = ("follow_the_winner", "follow_the_loser", "pattern_match", "meta_ensemble")
META_WEIGHTS = {"follow_the_winner": 0.4, "pattern_match": 0.3, "online_hedge": 0.3}
REQUIRED = {"asset", "timeframe", "strategy", "entry_time", "exit_time", "entry",
            "risk", "gross_R", "hold_hours", "outcome", "regime", "vol_regime"}
VALID_OUTCOMES = {"TP", "SL", "TIME", "GAP"}


def validate_trades(raw):
    missing = REQUIRED - set(raw.columns)
    if missing:
        raise ValueError(f"EXP-002 trade file missing columns: {sorted(missing)}")
    x = raw.copy()
    if x.empty:
        raise ValueError("EXP-002 trade file is empty")
    for col in ("asset", "timeframe", "strategy", "regime", "vol_regime", "outcome"):
        if x[col].isna().any() or x[col].astype(str).str.strip().eq("").any():
            raise ValueError(f"Empty {col} in EXP-002 trade file")
        x[col] = x[col].astype(str)
    unsupported = sorted(set(x.timeframe) - set(TIMEFRAME_MINUTES))
    invalid = sorted(set(x.outcome) - VALID_OUTCOMES)
    if unsupported or invalid:
        raise ValueError(f"Unsupported timeframes={unsupported}; outcomes={invalid}")
    for col in ("entry_time", "exit_time"):
        x[col] = pd.to_datetime(x[col], utc=True, errors="raise")
    if (x.exit_time < x.entry_time).any():
        raise ValueError("Trade exit timestamp must not precede entry timestamp")
    for col in ("entry", "risk", "gross_R", "hold_hours"):
        x[col] = pd.to_numeric(x[col], errors="raise")
        if not np.isfinite(x[col].to_numpy(float)).all():
            raise ValueError(f"Non-finite values in {col}")
    if (x.entry <= 0).any() or (x.risk <= 0).any() or (x.hold_hours < 0).any():
        raise ValueError("Entry/risk must be positive and hold_hours nonnegative")
    if x.duplicated(["asset", "timeframe", "strategy", "entry_time"]).any():
        raise ValueError("Duplicate strategy-stream entry timestamp")
    # Input times are candle opens. Outcomes are visible only at exit candle close.
    x["outcome_available_at"] = x.exit_time + pd.to_timedelta(
        x.timeframe.map(TIMEFRAME_MINUTES), unit="m")
    return x.sort_values(["entry_time", "asset", "timeframe", "strategy"],
                         kind="mergesort").reset_index(drop=True)


def net_r(row, cost_bps, carry_bps_per_8h=CARRY_STRESS_BPS_PER_8H):
    if not math.isfinite(cost_bps) or cost_bps < 0 or carry_bps_per_8h < 0:
        raise ValueError("Cost assumptions must be finite and nonnegative")
    drag = cost_bps / 10000 + carry_bps_per_8h * row.hold_hours / 8 / 10000
    return float(row.gross_R) - drag * float(row.entry) / float(row.risk)


def expert_key(row):
    return (str(row.asset), str(row.timeframe), str(row.strategy))


def context_key(row):
    return (str(row.asset), str(row.timeframe), str(row.regime), str(row.vol_regime))


def ewma(values):
    values = np.asarray(values[-50:], dtype=float)
    if not len(values):
        return math.nan
    age = np.arange(len(values) - 1, -1, -1, dtype=float)
    weights = np.power(0.5, age / 12.0)
    return float(np.dot(values, weights) / weights.sum())


def percentile(values):
    valid = [(i, float(v)) for i, v in enumerate(values)
             if v is not None and math.isfinite(float(v))]
    if not valid:
        return [None] * len(values)
    ordered = sorted(value for _, value in valid)
    ranks = {}
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j] == ordered[i]:
            j += 1
        ranks[ordered[i]] = 1.0 if len(ordered) == 1 else ((i + j - 1) / 2) / (len(ordered) - 1)
        i = j
    return [None if v is None or not math.isfinite(float(v)) else ranks[float(v)]
            for v in values]


def candidate_components(candidates, expert_history, context_history):
    result = {key: [] for key in ("follow_the_winner", "follow_the_loser",
                                   "pattern_match", "online_hedge")}
    for row in candidates.itertuples(index=False):
        past = expert_history.get(expert_key(row), [])
        if len(past) >= 3:
            mean = ewma(past) * len(past) / (len(past) + 5.0)
            result["follow_the_winner"].append(mean)
            result["follow_the_loser"].append(-mean)
            result["online_hedge"].append(0.15 * float(np.clip(past, -2, 2).sum()))
        else:
            for key in ("follow_the_winner", "follow_the_loser", "online_hedge"):
                result[key].append(None)
        context = context_history.get(context_key(row), [])
        result["pattern_match"].append(float(np.mean(context[-50:])) if len(context) >= 3 else None)
    return result


def select_one(candidates, policy, expert_history, context_history):
    if candidates.empty:
        return None, None
    components = candidate_components(candidates, expert_history, context_history)
    if policy == "meta_ensemble":
        ranks = {key: percentile(components[key]) for key in META_WEIGHTS}
        scores = []
        for i in range(len(candidates)):
            parts = [(weight, ranks[key][i]) for key, weight in META_WEIGHTS.items()
                     if ranks[key][i] is not None]
            scores.append(sum(w * score for w, score in parts) / sum(w for w, _ in parts)
                          if parts else None)
    elif policy in ("follow_the_winner", "follow_the_loser", "pattern_match"):
        scores = components[policy]
    else:
        raise ValueError(f"Unknown selector policy: {policy}")
    choices = [(i, float(v)) for i, v in enumerate(scores)
               if v is not None and math.isfinite(float(v))]
    if not choices or max(v for _, v in choices) <= 0:
        return None, None
    ranked = candidates.reset_index(drop=True).copy()
    ranked["_score"] = [float("-inf")] * len(ranked)
    for i, score in choices:
        ranked.loc[i, "_score"] = score
    ranked = ranked.sort_values(["_score", "strategy", "timeframe"],
                                ascending=[False, True, True], kind="mergesort")
    chosen = ranked.iloc[0]
    source_index = int(chosen.name)
    if policy == "meta_ensemble" and not any(
        components[key][source_index] is not None and components[key][source_index] > 0
        for key in ("follow_the_winner", "pattern_match")
    ):
        return None, None
    return chosen.drop(labels=["_score"]), float(chosen["_score"])


def simulate_policy(raw, policy, cost_bps):
    if policy not in POLICIES:
        raise ValueError(f"Unknown selector policy: {policy}")
    x = validate_trades(raw)
    x["net_R"] = [net_r(row, cost_bps) for row in x.itertuples(index=False)]
    feedback = x.sort_values(["outcome_available_at", "asset", "timeframe", "strategy"],
                             kind="mergesort")
    feedback_rows, pointer = list(feedback.itertuples(index=False)), 0
    expert_history, context_history, open_until = {}, {}, {}
    selected_rows, decision_rows = [], []
    for timestamp, batch in x.groupby("entry_time", sort=True):
        while pointer < len(feedback_rows) and feedback_rows[pointer].outcome_available_at <= timestamp:
            prior = feedback_rows[pointer]
            value = float(prior.net_R)
            expert_history.setdefault(expert_key(prior), []).append(value)
            context_history.setdefault(context_key(prior), []).append(value)
            pointer += 1
        for asset, candidates in batch.groupby("asset", sort=True):
            prior_exit = open_until.get(str(asset))
            if prior_exit is not None and timestamp < prior_exit:
                decision_rows.append({"policy": policy, "cost_bps": cost_bps,
                    "decision_time": timestamp, "asset": asset, "candidate_count": len(candidates),
                    "selected_strategy": None, "decision": "BLOCKED_OPEN_POSITION"})
                continue
            selected, score = select_one(candidates, policy, expert_history, context_history)
            if selected is None:
                decision_rows.append({"policy": policy, "cost_bps": cost_bps,
                    "decision_time": timestamp, "asset": asset, "candidate_count": len(candidates),
                    "selected_strategy": None, "decision": "NO_TRADE_INSUFFICIENT_OR_NONPOSITIVE_HISTORY"})
                continue
            open_until[str(asset)] = pd.Timestamp(selected.outcome_available_at)
            record = selected.to_dict()
            record.update({"policy": policy, "cost_bps": cost_bps,
                           "selection_score": score, "selected_at": timestamp})
            selected_rows.append(record)
            decision_rows.append({"policy": policy, "cost_bps": cost_bps,
                "decision_time": timestamp, "asset": asset, "candidate_count": len(candidates),
                "selected_strategy": selected.strategy, "selected_timeframe": selected.timeframe,
                "decision": "SELECTED_ONE_EXISTING_EXPERT_TRADE", "selection_score": score})
    return pd.DataFrame(selected_rows), pd.DataFrame(decision_rows)


def summarize(trades, months):
    if trades.empty:
        return {"n": 0, "win_rate_pct": None, "expectancy_net_R": None, "profit_factor": None,
                "max_drawdown_R": None, "max_consecutive_losses": 0, "trades_per_month": 0,
                "mean_hold_hours": None, "TP": 0, "SL": 0, "TIME": 0, "GAP": 0}
    x = trades.sort_values(["outcome_available_at", "asset", "strategy"], kind="mergesort")
    values = x.net_R.to_numpy(float)
    wins, losses = values[values > 0], values[values < 0]
    events = x.groupby("outcome_available_at", sort=True).net_R.sum().to_numpy(float)
    equity = np.cumsum(events)
    drawdown = equity - np.maximum.accumulate(np.r_[0.0, equity])[1:]
    streak = maximum = 0
    for value in events:  # simultaneous exits are one portfolio event
        streak = streak + 1 if value < 0 else 0
        maximum = max(maximum, streak)
    return {"n": len(x), "win_rate_pct": round(float((values > 0).mean() * 100), 2),
        "expectancy_net_R": round(float(values.mean()), 5),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 4)
            if len(losses) and abs(losses.sum()) else None,
        "max_drawdown_R": round(float(drawdown.min()), 4),
        "max_consecutive_losses": int(maximum),
        "trades_per_month": round(len(x) / max(months, 1e-9), 3),
        "mean_hold_hours": round(float(x.hold_hours.mean()), 3),
        **{outcome: int((x.outcome == outcome).sum()) for outcome in ("TP", "SL", "TIME", "GAP")}}


def run_experiment(input_csv, output_dir):
    raw = pd.read_csv(input_csv)
    trades = validate_trades(raw)
    output_dir.mkdir(parents=True, exist_ok=True)
    start, end = trades.entry_time.min(), trades.outcome_available_at.max()
    months = max((end - start).total_seconds() / (30.4375 * 86400), 1 / 30.4375)
    edges = [start + (end - start) * f for f in np.linspace(0, 1, 6)]
    summaries, folds, selected_all, decisions_all = [], [], [], []
    for cost in COST_SCENARIOS_BPS:
        for policy in POLICIES:
            selected, decisions = simulate_policy(trades, policy, cost)
            if not selected.empty:
                # Keep timestamps as datetimes: pandas 3.x may preserve second-resolution
                # values, while Timestamp.value is nanoseconds. Mixing those integer
                # units silently assigns every selected trade to a null walk-forward fold.
                selected["fold"] = pd.cut(
                    pd.to_datetime(selected["entry_time"], utc=True),
                    bins=pd.DatetimeIndex(edges),
                    labels=[f"WF{i}" for i in range(1, 6)],
                    include_lowest=True,
                ).astype("string")
            selected_all.append(selected)
            decisions_all.append(decisions)
            for asset in ["ALL", *sorted(trades.asset.unique())]:
                subset = selected if asset == "ALL" else selected[selected.asset == asset]
                summaries.append({"experiment_id": EXPERIMENT_ID, "policy": policy,
                    "asset": asset, "cost_bps_round_trip": cost, **summarize(subset, months)})
                for fold in (f"WF{i}" for i in range(1, 6)):
                    part = subset[subset.fold == fold] if not subset.empty else subset
                    folds.append({"experiment_id": EXPERIMENT_ID, "policy": policy, "asset": asset,
                        "cost_bps_round_trip": cost, "fold": fold, **summarize(part, months / 5)})
    outputs = {"summary": pd.DataFrame(summaries), "walk_forward": pd.DataFrame(folds),
        "selected_trades": pd.concat(selected_all, ignore_index=True),
        "decisions": pd.concat(decisions_all, ignore_index=True)}
    for name, table in outputs.items():
        table.to_csv(output_dir / f"exp003_{name}.csv", index=False)
    manifest_path = input_csv.parent / "exp002_manifest.json"
    manifest = {"experiment_id": EXPERIMENT_ID, "version": 1,
        "source_commit": __import__("os").environ.get("GITHUB_SHA"),
        "source_exp002_trade_sha256": hashlib.sha256(input_csv.read_bytes()).hexdigest(),
        "source_exp002_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            if manifest_path.is_file() else None,
        "policies": list(POLICIES), "round_trip_cost_bps": list(COST_SCENARIOS_BPS),
        "adverse_carry_stress_bps_per_8h": CARRY_STRESS_BPS_PER_8H,
        "controls": [
            "EXP-002 OOS shadow trades only; no result feeds back into EXP-002.",
            "Outcome becomes visible only when the exit candle closes.",
            "One selected position per asset and policy until the prior exit candle closes.",
            "Independent strategy streams are full-information shadow experts.",
            "Select one existing candidate only; never blend directions or create a setup.",
            "Three prior expert trades and three exact-context matches are required.",
            "Five chronological slices carry forward only previously completed outcomes.",
            "Carry is a stress assumption, not verified realized funding P&L.",
            "Historical spread, depth and executable market impact are unavailable.",
            "Research-only; no allowlist, alert, paper-position or order changes.",
        ]}
    (output_dir / "exp003_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-dir", default="quant_discovery/results/exp003")
    args = parser.parse_args(argv)
    results = run_experiment(Path(args.input_csv), Path(args.output_dir))
    print(results["summary"][(results["summary"].asset == "ALL") &
          (results["summary"].cost_bps_round_trip == 10.0)].to_string(index=False))


if __name__ == "__main__":
    main()
