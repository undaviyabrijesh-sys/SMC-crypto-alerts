#!/usr/bin/env python3
"""Frozen train-only BTC/ETH Engle-Granger and hedge-ratio stability diagnostic.

This is a statistical diagnostic, not a strategy, backtest, or trade signal.
It downloads no validation/OOS data and creates no positions or PnL.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import statsmodels
from statsmodels.tsa.stattools import adfuller, coint

from btc_eth_pairs_mean_reversion_backtest import (
    BAR,
    align_pair,
    feature_frame,
    load_ohlcv,
)

START = pd.Timestamp("2025-09-08T12:00:00Z")
TRAIN_END_EXCLUSIVE = pd.Timestamp("2026-07-12T04:45:00Z")
EXPECTED_ROWS = 29_443
BLOCK_COUNT = 4
FAMILY_ALPHA = 0.05
BETA_LOOKBACKS = (960, 2880)
RESIDUAL_LOOKBACK = 288


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def holm_adjust(p_values) -> np.ndarray:
    """Holm step-down adjusted p-values, returned in original input order."""
    p = np.asarray(p_values, dtype=float)
    if p.ndim != 1 or p.size == 0:
        raise ValueError("p_values must be a non-empty one-dimensional sequence")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("p-values must be finite and within [0, 1]")
    order = np.argsort(p, kind="mergesort")
    adjusted = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, original_index in enumerate(order):
        running = max(running, (m - rank) * p[original_index])
        adjusted[original_index] = min(1.0, running)
    return adjusted


def chronological_blocks(n: int, count: int = BLOCK_COUNT) -> list[np.ndarray]:
    if n < count * 1000:
        raise ValueError(f"need at least {count * 1000} rows for {count} blocks")
    blocks = [x for x in np.array_split(np.arange(n, dtype=int), count)]
    joined = np.concatenate(blocks)
    if not np.array_equal(joined, np.arange(n, dtype=int)):
        raise AssertionError("blocks are not contiguous, exhaustive and non-overlapping")
    return blocks


def adf_row(name: str, values: np.ndarray, transform: str) -> dict:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) < 1000 or not np.isfinite(values).all():
        raise ValueError(f"{name} {transform}: invalid or insufficient observations")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = adfuller(values, regression="c", autolag="AIC")
    stat, pvalue, usedlag, nobs, critical, _ = result
    return {
        "series": name,
        "transform": transform,
        "observations": int(len(values)),
        "adf_statistic": float(stat),
        "p_value": float(pvalue),
        "used_lag": int(usedlag),
        "test_observations": int(nobs),
        "critical_1pct": float(critical["1%"]),
        "critical_5pct": float(critical["5%"]),
        "critical_10pct": float(critical["10%"]),
        "warnings": " | ".join(str(x.message) for x in caught),
    }


def eg_row(label: str, frame: pd.DataFrame) -> dict:
    x = np.log(frame.btc_close.to_numpy(dtype=float))
    y = np.log(frame.eth_close.to_numpy(dtype=float))
    if len(x) < 1000 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError(f"{label}: invalid or insufficient log-price observations")
    design = np.column_stack([np.ones(len(x)), x])
    alpha, beta = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - (alpha + beta * x)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        statistic, pvalue, critical = coint(
            y, x, trend="c", maxlag=None, autolag="aic"
        )
    if not np.isfinite([statistic, pvalue, *critical]).all():
        raise ValueError(f"{label}: Engle-Granger returned non-finite statistics")
    return {
        "test_id": label,
        "observations": int(len(frame)),
        "start_utc": frame.index[0].isoformat(),
        "end_candle_close_utc": (frame.index[-1] + BAR).isoformat(),
        "regression": "log(ETH) = alpha + beta * log(BTC) + residual",
        "deterministic": "constant_only",
        "autolag": "AIC",
        "statistic": float(statistic),
        "p_value_raw": float(pvalue),
        "critical_1pct": float(critical[0]),
        "critical_5pct": float(critical[1]),
        "critical_10pct": float(critical[2]),
        "alpha_ols": float(alpha),
        "beta_ols": float(beta),
        "residual_std": float(np.std(residual, ddof=1)),
        "warnings": " | ".join(str(x.message) for x in caught),
    }


def rolling_beta_rows(pair: pd.DataFrame) -> list[dict]:
    rows = []
    for lookback in BETA_LOOKBACKS:
        # Reuse the exact lagged rolling OLS implementation from the pair study.
        features = feature_frame(pair, lookback, RESIDUAL_LOOKBACK)
        beta = features.beta.replace([np.inf, -np.inf], np.nan).dropna()
        corr = features["corr"].replace([np.inf, -np.inf], np.nan).dropna()
        if beta.empty:
            raise ValueError(f"no valid rolling beta observations for lookback {lookback}")
        rows.append({
            "beta_lookback_bars": lookback,
            "beta_lookback_days": lookback / 96.0,
            "residual_warmup_bars": RESIDUAL_LOOKBACK,
            "non_null_beta_observations": int(len(beta)),
            "beta_min": float(beta.min()),
            "beta_p05": float(beta.quantile(0.05)),
            "beta_median": float(beta.median()),
            "beta_p95": float(beta.quantile(0.95)),
            "beta_max": float(beta.max()),
            "beta_iqr": float(beta.quantile(0.75) - beta.quantile(0.25)),
            "positive_beta_fraction": float((beta > 0).mean()),
            "strategy_range_0_25_to_4_fraction": float(beta.between(0.25, 4.0).mean()),
            "rolling_return_corr_median": float(corr.median()) if len(corr) else None,
            "rolling_return_corr_min": float(corr.min()) if len(corr) else None,
        })
    return rows


def package_versions() -> dict:
    return {
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "statsmodels": statsmodels.__version__,
        "statsmodels_distribution": importlib.metadata.version("statsmodels"),
    }


def run(btc_path: Path, eth_path: Path, manifest_path: Path | None, out: Path) -> dict:
    btc = load_ohlcv(btc_path, "BTC", as_of=TRAIN_END_EXCLUSIVE)
    eth = load_ohlcv(eth_path, "ETH", as_of=TRAIN_END_EXCLUSIVE)
    expected_index = pd.date_range(
        START, TRAIN_END_EXCLUSIVE - BAR, freq=BAR, tz="UTC"
    )
    btc = btc.loc[(btc.index >= START) & (btc.index < TRAIN_END_EXCLUSIVE)]
    eth = eth.loc[(eth.index >= START) & (eth.index < TRAIN_END_EXCLUSIVE)]
    if not btc.index.equals(expected_index):
        raise ValueError(
            f"BTC training coverage mismatch: got {len(btc)} rows; "
            f"expected {len(expected_index)} exact contiguous rows"
        )
    if not eth.index.equals(expected_index):
        raise ValueError(
            f"ETH training coverage mismatch: got {len(eth)} rows; "
            f"expected {len(expected_index)} exact contiguous rows"
        )
    pair = align_pair(btc, eth)
    if not pair.index.equals(expected_index) or len(pair) != EXPECTED_ROWS:
        raise ValueError(
            f"aligned training coverage mismatch: got {len(pair)}; expected {EXPECTED_ROWS}"
        )
    if pair.segment.nunique() != 1:
        raise ValueError("unexpected data segment break in frozen training interval")

    log_btc = np.log(pair.btc_close.to_numpy(dtype=float))
    log_eth = np.log(pair.eth_close.to_numpy(dtype=float))
    unit_rows = [
        adf_row("BTC", log_btc, "log_level"),
        adf_row("ETH", log_eth, "log_level"),
        adf_row("BTC", np.diff(log_btc), "first_difference_of_log_level"),
        adf_row("ETH", np.diff(log_eth), "first_difference_of_log_level"),
    ]
    unit = pd.DataFrame(unit_rows)
    unit_map = {(r["series"], r["transform"]): r["p_value"] for r in unit_rows}
    i1_precondition = (
        unit_map[("BTC", "log_level")] >= FAMILY_ALPHA
        and unit_map[("ETH", "log_level")] >= FAMILY_ALPHA
        and unit_map[("BTC", "first_difference_of_log_level")] < FAMILY_ALPHA
        and unit_map[("ETH", "first_difference_of_log_level")] < FAMILY_ALPHA
    )

    block_indices = chronological_blocks(len(pair), BLOCK_COUNT)
    test_frames = [("full_train", pair)]
    for i, indices in enumerate(block_indices, start=1):
        test_frames.append((f"train_block_{i}", pair.iloc[indices]))
    tests = pd.DataFrame([eg_row(label, frame) for label, frame in test_frames])
    tests["p_value_holm_adjusted"] = holm_adjust(tests.p_value_raw.to_numpy(float))
    tests["holm_family_size"] = len(tests)
    tests["significant_holm_5pct"] = tests.p_value_holm_adjusted < FAMILY_ALPHA

    full = tests.loc[tests.test_id == "full_train"].iloc[0]
    fold_rows = tests[tests.test_id.str.startswith("train_block_")]
    stable_folds = int(fold_rows.significant_holm_5pct.sum())
    persistent = bool(
        i1_precondition
        and bool(full.significant_holm_5pct)
        and stable_folds >= 3
    )
    if not i1_precondition:
        classification = "inconclusive_i1_precondition_failed"
    elif persistent:
        classification = "persistent_train_only_cointegration_evidence"
    elif not bool(full.significant_holm_5pct):
        classification = "no_full_train_cointegration_evidence"
    else:
        classification = "cointegration_evidence_not_stable_across_blocks"

    beta_rows = rolling_beta_rows(pair)
    out.mkdir(parents=True, exist_ok=True)
    tests.to_csv(out / "cointegration_tests.csv", index=False)
    unit.to_csv(out / "unit_root_diagnostics.csv", index=False)
    pd.DataFrame(beta_rows).to_csv(out / "rolling_beta_stability.csv", index=False)

    manifest = {}
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    meta = {
        "classification": classification,
        "persistent_train_only_cointegration_evidence": persistent,
        "i1_precondition_pass": bool(i1_precondition),
        "full_train_p_value_raw": float(full.p_value_raw),
        "full_train_p_value_holm_adjusted": float(full.p_value_holm_adjusted),
        "significant_stability_blocks_holm_5pct": stable_folds,
        "stability_blocks_required": 3,
        "holm_family_size": 5,
        "train_only": True,
        "validation_data_downloaded": False,
        "oos_data_downloaded": False,
        "validation_evaluated": False,
        "oos_evaluated": False,
        "start_utc": pair.index[0].isoformat(),
        "train_end_exclusive_utc": TRAIN_END_EXCLUSIVE.isoformat(),
        "last_included_candle_close_utc": (pair.index[-1] + BAR).isoformat(),
        "btc_rows": int(len(btc)),
        "eth_rows": int(len(eth)),
        "aligned_rows": int(len(pair)),
        "btc_sha256": sha256_file(btc_path),
        "eth_sha256": sha256_file(eth_path),
        "btc_gap_count": int((btc.index.to_series().diff().dropna() != BAR).sum()),
        "eth_gap_count": int((eth.index.to_series().diff().dropna() != BAR).sum()),
        "aligned_gap_count": int((pair.index.to_series().diff().dropna() != BAR).sum()),
        "source": "Delta Exchange India public traded-price OHLCV",
        "bar_interval": "15m UTC candle-open timestamps",
        "regression": "log(ETH) on constant + log(BTC), fixed orientation",
        "engle_granger": "statsmodels coint, trend=c, autolag=AIC, one full-train test plus four contiguous blocks",
        "multiple_testing": "Holm-Bonferroni across exactly five Engle-Granger p-values",
        "unit_root_precondition": "ADF regression=c, autolag=AIC; levels should fail to reject and first differences should reject at 5%",
        "rolling_beta": beta_rows,
        "package_versions": package_versions(),
        "manifest_dataset_metadata": manifest.get("datasets", {}),
        "trading_metrics": None,
        "costs_funding_spread_slippage": "not applicable: no trades or positions are simulated",
        "decision_scope": "statistical train-only diagnostic; does not validate a trading strategy or reverse the prior rejected pair matrix",
        "next_step": "if cointegration evidence is absent or unstable, close the pair-mean-reversion premise; if present, require a separately preregistered prospective study before any strategy work",
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    lines = [
        "# BTC/ETH train-only cointegration diagnostic",
        "",
        f"- Classification: **{classification}**",
        f"- I(1) precondition: **{i1_precondition}**",
        f"- Full-train raw p-value: {float(full.p_value_raw):.8g}",
        f"- Full-train Holm-adjusted p-value: {float(full.p_value_holm_adjusted):.8g}",
        f"- Significant chronological blocks after Holm adjustment: {stable_folds}/4",
        f"- Dataset: {len(pair):,} aligned 15m rows, {pair.index[0].isoformat()} to {(pair.index[-1] + BAR).isoformat()}",
        "- Validation/OOS data: not downloaded or evaluated.",
        "",
        "## Engle-Granger family",
        "",
        tests[["test_id", "observations", "statistic", "p_value_raw",
               "p_value_holm_adjusted", "critical_1pct", "critical_5pct",
               "critical_10pct", "significant_holm_5pct"]].to_markdown(index=False),
        "",
        "## ADF I(1) precondition diagnostics",
        "",
        unit[["series", "transform", "adf_statistic", "p_value",
              "used_lag", "test_observations"]].to_markdown(index=False),
        "",
        "## Lagged rolling hedge-ratio stability",
        "",
        pd.DataFrame(beta_rows).to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "This is a train-only statistical diagnostic, not a trading backtest. No PnL, trade count, win rate, profit factor, drawdown, funding or transaction-cost result is applicable. A positive cointegration result would not reverse the previously rejected pair strategy or establish executable profitability.",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(meta, indent=2, sort_keys=True))
    print("\nENGLE-GRANGER FAMILY")
    print(tests.to_string(index=False))
    print("\nADF PRECONDITION")
    print(unit.to_string(index=False))
    return meta


def self_test() -> None:
    expected = np.array([0.03, 0.06, 0.06, 0.008])
    assert np.allclose(holm_adjust([0.01, 0.04, 0.03, 0.002]), expected)
    blocks = chronological_blocks(29_443, 4)
    assert [len(x) for x in blocks] == [7_361, 7_361, 7_361, 7_360]
    assert blocks[0][0] == 0 and blocks[-1][-1] == 29_442

    rng = np.random.default_rng(20261120)
    n = 3_000
    x = np.cumsum(rng.normal(size=n))
    noise = rng.normal(scale=0.5, size=n)
    stationary = np.zeros(n)
    for i in range(1, n):
        stationary[i] = 0.6 * stationary[i - 1] + noise[i]
    y_cointegrated = 1.25 * x + stationary
    _, p_cointegrated, _ = coint(y_cointegrated, x, trend="c", autolag="aic")
    assert p_cointegrated < 0.01

    rng = np.random.default_rng(20261121)
    x_independent = np.cumsum(rng.normal(size=n))
    y_independent = np.cumsum(rng.normal(size=n))
    _, p_independent, _ = coint(y_independent, x_independent, trend="c", autolag="aic")
    assert p_independent > 0.05

    # Reused rolling features must not change when only future prices change.
    rng = np.random.default_rng(20261122)
    n = 900
    idx = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    bx = 10.0 + np.cumsum(rng.normal(0, 0.002, n))
    ey = 8.0 + 1.1 * (bx - 10.0) + rng.normal(0, 0.01, n)
    frame = pd.DataFrame({
        "btc_open": np.exp(bx), "btc_high": np.exp(bx + 0.002),
        "btc_low": np.exp(bx - 0.002), "btc_close": np.exp(bx),
        "eth_open": np.exp(ey), "eth_high": np.exp(ey + 0.002),
        "eth_low": np.exp(ey - 0.002), "eth_close": np.exp(ey),
        "segment": np.zeros(n, dtype=int),
    }, index=idx)
    altered = frame.copy()
    altered.loc[idx[700]:, "btc_close"] *= 1.2
    altered.loc[idx[700]:, "eth_close"] *= 0.8
    f1 = feature_frame(frame, 96, 48)
    f2 = feature_frame(altered, 96, 48)
    for column in ("beta", "alpha", "resid_mean", "resid_std", "z", "corr"):
        assert np.allclose(
            f1[column].iloc[:700].to_numpy(),
            f2[column].iloc[:700].to_numpy(),
            equal_nan=True,
        )
    print("5 cointegration, Holm, chronological-block and future-perturbation self-tests passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--btc-csv", type=Path)
    parser.add_argument("--eth-csv", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results/btc-eth-cointegration"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.btc_csv or not args.eth_csv:
        parser.error("provide --btc-csv and --eth-csv")
    run(args.btc_csv, args.eth_csv, args.manifest, args.output_dir)


if __name__ == "__main__":
    main()
