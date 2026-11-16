"""Defined-risk option-selling research: bull put/bear call credit spreads and iron condors.

No naked option selling is simulated. Trades require synchronous traded candles for
all legs, use conservative OHLC-based spread-cost proxies, risk-size from max loss,
and flag exits caused by sparse option prints as indicative only.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _common_entry(short: dict[str, Any], long: dict[str, Any],
                  earliest: pd.Timestamp, latest: pd.Timestamp):
    common = short["bars"].index.intersection(long["bars"].index)
    common = common[(common >= earliest) & (common <= latest)]
    if len(common) == 0:
        return None
    return common[0]


def _select_vertical(option_data, option_type, side, spot, signal_time, cfg,
                     short_otm_pct=0.03, wing_pct=0.05):
    """Select same-expiry, defined-risk vertical using only synchronized traded bars."""
    earliest = signal_time + pd.Timedelta(hours=1)
    latest = earliest + pd.Timedelta(hours=cfg.max_entry_delay_hours)
    contracts = [x for x in option_data.values() if x["option_type"] == option_type]
    choices = []
    for short in contracts:
        dte = (short["expiry"] - signal_time).total_seconds() / 86400.0
        if not cfg.min_dte_days <= dte <= cfg.max_dte_days:
            continue
        k_short = float(short["strike"])
        if side == "PUT":
            if k_short > spot * (1.0 - short_otm_pct):
                continue
            hedge_candidates = [
                x for x in contracts
                if x["expiry"] == short["expiry"]
                and float(x["strike"]) <= k_short - spot * wing_pct
            ]
            hedge_candidates.sort(key=lambda x: float(x["strike"]), reverse=True)
        else:
            if k_short < spot * (1.0 + short_otm_pct):
                continue
            hedge_candidates = [
                x for x in contracts
                if x["expiry"] == short["expiry"]
                and float(x["strike"]) >= k_short + spot * wing_pct
            ]
            hedge_candidates.sort(key=lambda x: float(x["strike"]))
        for hedge in hedge_candidates:
            entry_time = _common_entry(short, hedge, earliest, latest)
            if entry_time is None:
                continue
            width = abs(float(hedge["strike"]) - k_short)
            distance = abs(k_short / spot - (1.0 - short_otm_pct if side == "PUT" else 1.0 + short_otm_pct))
            choices.append((distance, dte, width, short, hedge, entry_time))
            break
    if not choices:
        return None
    _, _, _, short, hedge, entry_time = min(choices, key=lambda x: (x[0], x[1], x[2]))
    return short, hedge, entry_time


def _spread_debit(short_bar, hedge_bar, mode="close"):
    """Conservative debit to close: buy short at ask proxy, sell hedge at bid proxy."""
    if mode == "high":
        return max(0.0, float(short_bar["high"]) - float(hedge_bar["low"]))
    if mode == "low":
        return max(0.0, float(short_bar["low"]) - float(hedge_bar["high"]))
    return max(0.0, float(short_bar["close"]) - float(hedge_bar["close"]))


def _simulate_vertical(asset, strategy_id, signal_time, direction, spot,
                       short, hedge, entry_time, cfg, equity, split):
    short_entry = short["bars"].loc[entry_time]
    hedge_entry = hedge["bars"].loc[entry_time]
    cost_rate = (cfg.spread_bps_per_side + cfg.slippage_bps_per_side) / 10_000.0
    fee_rate = cfg.fee_bps_per_side / 10_000.0

    # Sell the short option at its observed low; buy the hedge at its observed high.
    short_sell = float(short_entry["low"]) * (1.0 - cost_rate)
    hedge_buy = float(hedge_entry["high"]) * (1.0 + cost_rate)
    credit = short_sell - hedge_buy
    width = abs(float(short["strike"]) - float(hedge["strike"]))
    max_loss_per_contract = width - credit
    if credit <= 0 or max_loss_per_contract <= 0:
        return None, equity

    risk_budget = equity * cfg.risk_fraction
    qty_step = 0.01
    qty = math.floor((risk_budget / max_loss_per_contract) / qty_step) * qty_step
    if qty < 0.01:
        return None, equity

    entry_fees = (short_sell + hedge_buy) * qty * fee_rate
    entry_credit_cash = credit * qty - entry_fees
    target_debit = credit * 0.50  # take profit after retaining 50% of initial credit
    stop_debit = credit * 2.00   # stop if repurchase cost reaches 2x initial credit
    previous_time = entry_time
    exit_time = None
    exit_reason = None
    exit_debit_raw = None
    gap_hours = 0.0
    same_bar_ambiguous = False
    max_gap_hours = max(6.0, float(cfg.max_hold_hours) * 2.0)
    max_exit_time = entry_time + pd.Timedelta(hours=cfg.max_hold_hours)

    common = short["bars"].index.intersection(hedge["bars"].index)
    future = common[common > entry_time]
    # Opening candle can itself have an adverse/favourable spread excursion after entry.
    future = common[common >= entry_time]
    for ts in future:
        sb, hb = short["bars"].loc[ts], hedge["bars"].loc[ts]
        if ts > entry_time:
            gap_hours = max(0.0, (ts - previous_time).total_seconds() / 3600.0 - 1.0)
            if gap_hours > max_gap_hours:
                prior_s, prior_h = short["bars"].loc[previous_time], hedge["bars"].loc[previous_time]
                exit_debit_raw = _spread_debit(prior_s, prior_h, "high")
                exit_time = previous_time + pd.Timedelta(hours=1)
                exit_reason = "GAP_GUARD_EXIT"
                break

        # Entry is modeled at this candle's observed low/high proxies; do not reuse
        # the same bar's full range as if its price path were known after the fill.
        if ts == entry_time:
            previous_time = ts
            continue
        worst_debit = _spread_debit(sb, hb, "high")
        best_debit = _spread_debit(sb, hb, "low")
        stop_hit = worst_debit >= stop_debit
        target_hit = best_debit <= target_debit
        if stop_hit and target_hit:
            # Intrabar sequence is unknowable; resolve against the short-spread seller.
            exit_debit_raw = worst_debit
            exit_time = ts + pd.Timedelta(hours=1)
            exit_reason = "SL_SAME_BAR_AMBIGUITY"
            same_bar_ambiguous = True
            break
        if stop_hit:
            exit_debit_raw = worst_debit
            exit_time = ts + pd.Timedelta(hours=1)
            exit_reason = "SL"
            break
        if target_hit and ts > entry_time:
            exit_debit_raw = worst_debit
            exit_time = ts + pd.Timedelta(hours=1)
            exit_reason = "TP_50pct_CREDIT"
            break
        if ts > entry_time and ts + pd.Timedelta(hours=1) >= max_exit_time:
            exit_debit_raw = _spread_debit(sb, hb, "high")
            exit_time = ts + pd.Timedelta(hours=1)
            exit_reason = "TIME_EXIT"
            break
        previous_time = ts

    if exit_debit_raw is None:
        if len(future) == 0:
            return None, equity
        last_time = future[-1]
        last_s, last_h = short["bars"].loc[last_time], hedge["bars"].loc[last_time]
        exit_debit_raw = _spread_debit(last_s, last_h, "high")
        exit_time = last_time + pd.Timedelta(hours=1)
        exit_reason = "END_OF_DATA"

    exit_cost = cost_rate + (cfg.gap_penalty_bps / 10_000.0 if exit_reason == "GAP_GUARD_EXIT" else 0.0)
    exit_debit = exit_debit_raw * (1.0 + exit_cost)
    exit_fees = (float(short["bars"].loc[previous_time]["high"]) +
                 float(hedge["bars"].loc[previous_time]["low"])) * qty * fee_rate
    # If a position was closed at a later bar, charge fees on the actual modeled closing spread debit.
    exit_fees = exit_debit * qty * 2.0 * fee_rate
    pnl = entry_credit_cash - exit_debit * qty - exit_fees
    max_risk_cash = max_loss_per_contract * qty
    net_r = pnl / max(max_risk_cash, 1e-12)
    equity_after = equity + pnl

    trade = {
        "asset": asset, "strategy_id": strategy_id, "direction": direction,
        "signal_time": signal_time.isoformat(), "entry_time": entry_time.isoformat(),
        "exit_time": pd.Timestamp(exit_time).isoformat(),
        "short_option_symbol": short["symbol"], "hedge_option_symbol": hedge["symbol"],
        "short_strike": float(short["strike"]), "hedge_strike": float(hedge["strike"]),
        "expiry": short["expiry"].isoformat(), "spot_at_signal": float(spot),
        "short_leg_entry_bid_proxy": short_sell, "hedge_leg_entry_ask_proxy": hedge_buy,
        "entry_credit_per_contract": credit, "spread_width": width,
        "max_loss_per_contract_before_fees": max_loss_per_contract,
        "exit_debit_per_contract": exit_debit,
        "quantity_contracts_model": qty, "max_risk_model": max_risk_cash,
        "gross_pnl_model": (credit - exit_debit_raw) * qty,
        "net_pnl_model": pnl, "fees_model": entry_fees + exit_fees,
        "net_return_on_max_risk_pct": 100.0 * pnl / max(max_risk_cash, 1e-12),
        "net_r": net_r, "equity_before": equity, "equity_after": equity_after,
        "exit_reason": exit_reason, "same_bar_ambiguous": same_bar_ambiguous,
        "data_quality_flag": "GAP_GUARD_EXIT" if exit_reason == "GAP_GUARD_EXIT" else "TRADED_CANDLES_ONLY",
        "split": split,
        "signal_to_entry_delay_hours": (entry_time - (signal_time + pd.Timedelta(hours=1))).total_seconds()/3600.0,
        "cost_assumptions_bps_per_side": {
            "fee": cfg.fee_bps_per_side, "spread_proxy": cfg.spread_bps_per_side,
            "slippage": cfg.slippage_bps_per_side,
        },
    }
    return trade, equity_after


def _metrics(frame: pd.DataFrame, initial_equity: float):
    if frame.empty:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate_pct": None,
                "net_pnl_model": 0.0, "expectancy_r": None, "profit_factor": None,
                "max_drawdown_pct": 0.0, "max_consecutive_losses": 0,
                "gap_guard_exits": 0, "status": "NO_SYNCHRONIZED_TRADES"}
    pnl = pd.to_numeric(frame["net_pnl_model"], errors="coerce").fillna(0.0)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    curve = pd.Series([initial_equity] + list(initial_equity + pnl.cumsum()), dtype=float)
    dd = curve / curve.cummax() - 1.0
    streak = best = 0
    for value in pnl:
        streak = streak + 1 if value < 0 else 0
        best = max(best, streak)
    return {
        "trades": int(len(frame)), "wins": int(len(wins)), "losses": int(len(losses)),
        "win_rate_pct": round(100.0 * len(wins) / len(frame), 4),
        "net_pnl_model": round(float(pnl.sum()), 8),
        "return_on_initial_equity_pct": round(100.0 * float(pnl.sum()) / initial_equity, 6),
        "expectancy_r": round(float(frame["net_r"].mean()), 6),
        "profit_factor": round(float(wins.sum() / -losses.sum()), 6) if len(losses) else None,
        "max_drawdown_pct": round(float(dd.min() * 100.0), 6),
        "max_consecutive_losses": best,
        "gap_guard_exits": int((frame["exit_reason"] == "GAP_GUARD_EXIT").sum()),
        "same_bar_ambiguous_exits": int(frame["same_bar_ambiguous"].fillna(False).astype(bool).sum()),
        "ending_equity_model": round(float(curve.iloc[-1]), 8),
        "status": "INDICATIVE" if (frame["data_quality_flag"] == "GAP_GUARD_EXIT").any() else "TRADED_CANDLE_REPLAY",
        "caution": "All prices use OHLC spread proxies; no historical bid/ask/depth, assignment, margin or liquidation replay.",
    }


def run_credit_spread_research(asset, underlying, option_data, signal_sets, cfg):
    """Run bullish put-credit, bearish call-credit and compression iron-condor studies."""
    all_trades = []
    strategy_specs = [
        ("OPT-06_BULL_PUT_CREDIT", "PUT", "LONG", ["OPT-01_MOMENTUM", "OPT-03_EMA_PULLBACK"]),
        ("OPT-07_BEAR_CALL_CREDIT", "CALL", "SHORT", ["OPT-01_MOMENTUM", "OPT-03_EMA_PULLBACK"]),
    ]
    # Use train/validation/test boundaries consistent with the long-options research split.
    n = len(underlying.index)
    train_end_i = max(0, min(n - 1, int(n * 0.60) - 1))
    validation_end_i = max(train_end_i, min(n - 1, int(n * 0.80) - 1))
    validation_start_i = min(n - 1, train_end_i + 2)
    test_start_i = min(n - 1, validation_end_i + 2)
    train_end = underlying.index[train_end_i]
    validation_start = underlying.index[validation_start_i]
    validation_end = underlying.index[validation_end_i]
    test_start = underlying.index[test_start_i]

    def split_for(ts):
        if ts <= train_end:
            return "train"
        if validation_start <= ts <= validation_end:
            return "validation"
        if ts >= test_start:
            return "test"
        return "purged_boundary_bar"

    for strategy_id, option_type, direction, signal_ids in strategy_specs:
        events = []
        for signal_id in signal_ids:
            frame = signal_sets.get(signal_id)
            if frame is None or frame.empty:
                continue
            desired = "LONG" if direction == "LONG" else "SHORT"
            for ts, row in frame.iterrows():
                if row["direction"] == desired:
                    events.append((ts, row))
        events.sort(key=lambda x: x[0])
        equity = cfg.initial_equity
        busy_until = pd.Timestamp.min.tz_localize("UTC")
        for signal_time, signal in events:
            if signal_time < busy_until or signal_time not in underlying.index:
                continue
            spot = float(underlying.loc[signal_time, "close"])
            selected = _select_vertical(option_data, option_type, "PUT" if option_type == "PUT" else "CALL",
                                        spot, signal_time, cfg)
            if not selected:
                continue
            short, hedge, entry_time = selected
            trade, equity = _simulate_vertical(
                asset, strategy_id, signal_time, direction, spot,
                short, hedge, entry_time, cfg, equity, split_for(signal_time)
            )
            if trade:
                all_trades.append(trade)
                busy_until = pd.Timestamp(trade["exit_time"])

    # A defined-risk iron condor is entered only on new compression events; both wings must trade synchronously.
    cond_signals = signal_sets.get("OPT-04_LONG_STRADDLE")
    if cond_signals is not None and not cond_signals.empty:
        equity = cfg.initial_equity
        busy_until = pd.Timestamp.min.tz_localize("UTC")
        for signal_time, signal in cond_signals.iterrows():
            if signal_time < busy_until or signal_time not in underlying.index:
                continue
            spot = float(underlying.loc[signal_time, "close"])
            put_pair = _select_vertical(option_data, "PUT", "PUT", spot, signal_time, cfg,
                                        short_otm_pct=0.05, wing_pct=0.05)
            call_pair = _select_vertical(option_data, "CALL", "CALL", spot, signal_time, cfg,
                                         short_otm_pct=0.05, wing_pct=0.05)
            if not put_pair or not call_pair:
                continue
            ps, ph, pt = put_pair
            cs, ch, ct = call_pair
            entry_time = max(pt, ct)
            if entry_time > signal_time + pd.Timedelta(hours=1+cfg.max_entry_delay_hours):
                continue
            # All four traded legs must print on the exact same hour.
            if any(entry_time not in x["bars"].index for x in (ps, ph, cs, ch)):
                continue
            put_credit = float(ps["bars"].loc[entry_time]["low"]) - float(ph["bars"].loc[entry_time]["high"])
            call_credit = float(cs["bars"].loc[entry_time]["low"]) - float(ch["bars"].loc[entry_time]["high"])
            credit = put_credit + call_credit
            width = abs(float(ps["strike"])-float(ph["strike"])) + abs(float(cs["strike"])-float(ch["strike"]))
            max_loss = width - credit
            if credit <= 0 or max_loss <= 0:
                continue
            risk_budget = equity * cfg.risk_fraction
            qty = math.floor((risk_budget / max_loss) / 0.01) * 0.01
            if qty < 0.01:
                continue
            # Close when either wing breaches its stop or the max holding time is reached.
            common = ps["bars"].index.intersection(ph["bars"].index).intersection(cs["bars"].index).intersection(ch["bars"].index)
            future = common[common >= entry_time]
            target_debit, stop_debit = credit * 0.5, credit * 2.0
            prev = entry_time
            exit_raw = None
            reason = None
            exit_time = None
            for ts in future:
                if ts == entry_time:
                    prev = ts
                    continue
                pdebit_hi = _spread_debit(ps["bars"].loc[ts], ph["bars"].loc[ts], "high")
                cdebit_hi = _spread_debit(cs["bars"].loc[ts], ch["bars"].loc[ts], "high")
                combined_hi = pdebit_hi + cdebit_hi
                if ts > entry_time and (ts - prev).total_seconds()/3600.0 > max(6.0, cfg.max_hold_hours*2.0):
                    reason = "GAP_GUARD_EXIT"
                    exit_raw = combined_hi
                    exit_time = prev + pd.Timedelta(hours=1)
                    break
                if combined_hi >= stop_debit:
                    reason, exit_raw, exit_time = "SL", combined_hi, ts + pd.Timedelta(hours=1)
                    break
                if ts > entry_time:
                    pdebit_lo = _spread_debit(ps["bars"].loc[ts], ph["bars"].loc[ts], "low")
                    cdebit_lo = _spread_debit(cs["bars"].loc[ts], ch["bars"].loc[ts], "low")
                    if pdebit_lo + cdebit_lo <= target_debit:
                        reason, exit_raw, exit_time = "TP_50pct_CREDIT", combined_hi, ts + pd.Timedelta(hours=1)
                        break
                    if ts + pd.Timedelta(hours=1) >= entry_time + pd.Timedelta(hours=cfg.max_hold_hours):
                        reason, exit_raw, exit_time = "TIME_EXIT", combined_hi, ts + pd.Timedelta(hours=1)
                        break
                prev = ts
            if exit_raw is None:
                if len(future) == 0:
                    continue
                last = future[-1]
                exit_raw = (_spread_debit(ps["bars"].loc[last], ph["bars"].loc[last], "high") +
                            _spread_debit(cs["bars"].loc[last], ch["bars"].loc[last], "high"))
                exit_time, reason = last + pd.Timedelta(hours=1), "END_OF_DATA"
            cost_rate = (cfg.spread_bps_per_side + cfg.slippage_bps_per_side) / 10000.0
            fee_rate = cfg.fee_bps_per_side / 10000.0
            exit_debit = exit_raw * (1+cost_rate+(cfg.gap_penalty_bps/10000.0 if reason=="GAP_GUARD_EXIT" else 0))
            fees = (credit + exit_debit) * qty * 2*fee_rate
            pnl = credit * qty - exit_debit*qty - fees
            max_risk_cash = max_loss*qty
            eq_after = equity+pnl
            all_trades.append({
                "asset":asset,"strategy_id":"OPT-08_IRON_CONDOR","direction":"RANGE",
                "signal_time":signal_time.isoformat(),"entry_time":entry_time.isoformat(),
                "exit_time":pd.Timestamp(exit_time).isoformat(),
                "short_option_symbol":f"{ps['symbol']} + {cs['symbol']}",
                "hedge_option_symbol":f"{ph['symbol']} + {ch['symbol']}",
                "short_strike":f"{ps['strike']}P / {cs['strike']}C",
                "hedge_strike":f"{ph['strike']}P / {ch['strike']}C",
                "expiry":ps["expiry"].isoformat(),"spot_at_signal":spot,
                "entry_credit_per_contract":credit,"spread_width":width,
                "max_loss_per_contract_before_fees":max_loss,"exit_debit_per_contract":exit_debit,
                "quantity_contracts_model":qty,"max_risk_model":max_risk_cash,
                "gross_pnl_model":(credit-exit_raw)*qty,"net_pnl_model":pnl,"fees_model":fees,
                "net_return_on_max_risk_pct":100*pnl/max(max_risk_cash,1e-12),
                "net_r":pnl/max(max_risk_cash,1e-12),"equity_before":equity,"equity_after":eq_after,
                "exit_reason":reason,"same_bar_ambiguous":False,
                "data_quality_flag":"GAP_GUARD_EXIT" if reason=="GAP_GUARD_EXIT" else "TRADED_CANDLES_ONLY",
                "split":split_for(signal_time),"signal_to_entry_delay_hours":(entry_time-(signal_time+pd.Timedelta(hours=1))).total_seconds()/3600,
            })
            equity=eq_after
            busy_until=pd.Timestamp(exit_time)

    trades = pd.DataFrame(all_trades)
    if not trades.empty:
        trades = trades.sort_values(["signal_time", "strategy_id"]).reset_index(drop=True)
    summary = {}
    for strategy_id in ("OPT-06_BULL_PUT_CREDIT", "OPT-07_BEAR_CALL_CREDIT", "OPT-08_IRON_CONDOR"):
        frame = trades[trades["strategy_id"] == strategy_id] if not trades.empty else pd.DataFrame()
        summary[strategy_id] = {
            "all": _metrics(frame, cfg.initial_equity),
            "train": _metrics(frame[frame["split"] == "train"], cfg.initial_equity) if not frame.empty else _metrics(frame,cfg.initial_equity),
            "validation": _metrics(frame[frame["split"] == "validation"], cfg.initial_equity) if not frame.empty else _metrics(frame,cfg.initial_equity),
            "test": _metrics(frame[frame["split"] == "test"], cfg.initial_equity) if not frame.empty else _metrics(frame,cfg.initial_equity),
        }
    return {"trades": trades, "strategies": summary, "execution_model": {
        "position_types": "Defined-risk vertical credit spreads and four-leg iron condor only; no naked shorts.",
        "bullish": "Sell OTM put; buy farther OTM put, same expiry.",
        "bearish": "Sell OTM call; buy farther OTM call, same expiry.",
        "entry": "Synchronous traded option candles after the underlying signal close; short sold at low and hedge bought at high.",
        "risk": "Position size is based on vertical strike width minus credit; fixed 1% equity risk budget.",
        "exit": "50% credit capture target, 2x-credit stop, maximum holding time; stop-first ambiguity.",
        "liquidity": "Only same-hour traded candles are accepted. Sparse observations invoke a flagged gap guard, not an assumed clean fill.",
        "costs": "Fee, spread proxy and slippage applied to both legs.",
        "limitations": [
            "OHLC extremes are conservative proxies, not historical bid/ask quotes or executable order-book fills.",
            "Contract settlement, assignment, margin, liquidation and portfolio offsets are not modeled.",
            "Sparse option trading can create a very small sample; zero/insufficient fills are not evidence of edge.",
        ],
    }}
