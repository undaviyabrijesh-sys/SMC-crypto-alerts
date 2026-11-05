"""Deterministic, AI-free multi-strategy candidate generation from closed OHLCV bars.

Scores are rule-quality points, not probabilities or expected win rates. Every
strategy is independent; this module never combines incompatible setups.
"""
import math

import numpy as np
import pandas as pd


TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
REQUIRED_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d", "1w")


def _valid_frame(frame, timeframe, minimum=60, continuity=50):
    if frame is None or len(frame) < minimum:
        return False
    if not isinstance(frame.index, pd.DatetimeIndex):
        return False
    if frame.index.tz is None or not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        return False
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        return False
    values = frame[list(required)].tail(max(minimum, continuity)).to_numpy(dtype=float)
    if not np.isfinite(values).all():
        return False
    prices = frame[["open", "high", "low", "close"]].tail(max(minimum, continuity))
    if (prices <= 0).any().any():
        return False
    if (prices["high"] < prices[["open", "low", "close"]].max(axis=1)).any():
        return False
    if (prices["low"] > prices[["open", "high", "close"]].min(axis=1)).any():
        return False
    step = pd.Timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    recent_index = frame.index[-continuity:]
    return len(recent_index) < 2 or bool((recent_index.to_series().diff().dropna() == step).all())


def _ema(series, span):
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def _atr(frame, period=14):
    previous = frame["close"].shift(1)
    true_range = pd.concat(
        [(frame["high"] - frame["low"]),
         (frame["high"] - previous).abs(),
         (frame["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=period).mean()


def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _bands(series, period=20, deviations=2.0):
    middle = series.rolling(period, min_periods=period).mean()
    sigma = series.rolling(period, min_periods=period).std(ddof=0)
    return middle, middle + deviations * sigma, middle - deviations * sigma


def _trend(frame):
    close = frame["close"]
    fast, slow = _ema(close, 20), _ema(close, 50)
    if any(pd.isna(value) for value in (close.iloc[-1], fast.iloc[-1], slow.iloc[-1], fast.iloc[-4])):
        return 0
    if close.iloc[-1] > fast.iloc[-1] > slow.iloc[-1] and fast.iloc[-1] > fast.iloc[-4]:
        return 1
    if close.iloc[-1] < fast.iloc[-1] < slow.iloc[-1] and fast.iloc[-1] < fast.iloc[-4]:
        return -1
    return 0


def _timeframe_alignment(frames, direction, five_min_confirm):
    aligned = []
    for timeframe in ("1w", "1d", "4h", "1h"):
        if _trend(frames[timeframe]) == direction:
            aligned.append(timeframe)
    fifteen = frames["15m"].iloc[-1]
    if (direction == 1 and fifteen.close > fifteen.open) or (direction == -1 and fifteen.close < fifteen.open):
        aligned.append("15m")
    if five_min_confirm:
        aligned.append("5m")
    return aligned


def _five_min_confirm(frame, direction):
    if len(frame) < 3:
        return False
    current, previous = frame.iloc[-1], frame.iloc[-2]
    if direction == 1:
        return bool(current.close > current.open and current.close > previous.high)
    return bool(current.close < current.open and current.close < previous.low)


def _score(frames, direction, five_min_confirm, volume_confirm, trigger_points=25):
    alignment = _timeframe_alignment(frames, direction, five_min_confirm)
    higher = sum(tf in alignment for tf in ("1w", "1d", "4h", "1h"))
    # Transparent rubric; this is not a probability or a learned win-rate estimate.
    score = 6 * higher + trigger_points + (20 if five_min_confirm else 0)
    score += 8 if volume_confirm else 0
    score += 10  # valid stop/target geometry is checked before candidate creation
    return min(100, int(score)), alignment


def _make_candidate(symbol, frames, strategy_id, setup_type, direction, stop, rationale,
                    trigger_points=25, target=None, invalidation=None):
    m5, m15 = frames["5m"], frames["15m"]
    entry = float(m5.iloc[-1].close)
    atr15 = float(_atr(m15).iloc[-1])
    stop = float(stop)
    if not all(math.isfinite(x) and x > 0 for x in (entry, stop, atr15)) or atr15 <= 0:
        return None
    risk = entry - stop if direction == 1 else stop - entry
    if risk <= 0 or not (0.35 <= risk / atr15 <= 2.5):
        return None
    target = float(target) if target is not None else entry + direction * 2.2 * risk
    reward = target - entry if direction == 1 else entry - target
    rr = reward / risk if risk > 0 else 0
    if not math.isfinite(rr) or rr < 2.0 or target <= 0:
        return None

    five_confirm = _five_min_confirm(m5, direction)
    if not five_confirm:
        return None
    volume = float(m15.iloc[-1].volume)
    volume_median = float(m15.volume.iloc[-21:-1].median())
    volume_confirm = math.isfinite(volume_median) and volume_median > 0 and volume > volume_median
    score, aligned = _score(frames, direction, five_confirm, volume_confirm, trigger_points)
    if score < 75:
        return None
    candle_open = m5.index[-1]
    return {
        "symbol": symbol,
        "strategy_id": strategy_id,
        "setup_type": setup_type,
        "direction": "LONG" if direction == 1 else "SHORT",
        "entry": entry,
        "stop_loss": stop,
        "take_profit": target,
        "rr": round(rr, 4),
        "quality_score": score,
        "score_type": "RULE_QUALITY_POINTS_NOT_PROBABILITY",
        "atr_15m": atr15,
        "stop_atr": round(risk / atr15, 4),
        "signal_candle": candle_open.isoformat(),
        "triggered_at": (candle_open + pd.Timedelta(minutes=5)).isoformat(),
        "timeframes_in_agreement": aligned,
        "bias": "BULLISH" if direction == 1 else "BEARISH",
        "rationale": rationale[:500],
        "invalidation": (invalidation or "Stop-loss beyond the setup invalidation level.")[:240],
        "target_basis": "Fixed 2.2R objective; candidate remains research-only until validated.",
    }


def _trend_pullback(symbol, frames):
    h4, h1, m15, m5 = frames["4h"], frames["1h"], frames["15m"], frames["5m"]
    direction = _trend(h4)
    if direction == 0 or _trend(h1) != direction:
        return None
    if _trend(frames["1d"]) not in (0, direction) or _trend(frames["1w"]) not in (0, direction):
        return None
    ema20 = _ema(m15.close, 20)
    atr = _atr(m15).iloc[-1]
    current = m15.iloc[-1]
    if pd.isna(ema20.iloc[-1]) or pd.isna(atr) or atr <= 0:
        return None
    near = abs(float(current.close) - float(ema20.iloc[-1])) <= 0.45 * float(atr)
    reclaimed = current.close > ema20.iloc[-1] and current.close > current.open if direction == 1 else current.close < ema20.iloc[-1] and current.close < current.open
    if not (near and reclaimed and _five_min_confirm(m5, direction)):
        return None
    swing = float(m5.low.tail(6).min()) if direction == 1 else float(m5.high.tail(6).max())
    stop = swing - 0.12 * float(atr) if direction == 1 else swing + 0.12 * float(atr)
    return _make_candidate(
        symbol, frames, "TREND_PULLBACK", "TREND_PULLBACK", direction, stop,
        "4h and 1h trend agree; 15m price pulled back to and reclaimed its 20 EMA; closed 5m candle confirmed.",
        trigger_points=27,
    )


def _breakout_retest(symbol, frames):
    h1, h4, m15, m5 = frames["1h"], frames["4h"], frames["15m"], frames["5m"]
    direction = _trend(h4)
    if direction == 0 or _trend(h1) != direction:
        return None
    if _trend(frames["1d"]) not in (0, direction):
        return None
    prior = h1.iloc[-21:-1]
    if len(prior) < 20:
        return None
    level = float(prior.high.max()) if direction == 1 else float(prior.low.min())
    last = m15.iloc[-1]
    atr = float(_atr(m15).iloc[-1])
    if not math.isfinite(atr) or atr <= 0:
        return None
    if direction == 1:
        retest = last.low <= level + 0.25 * atr and last.close > level and last.close > last.open
        stop = min(float(m15.low.tail(4).min()), level - 0.15 * atr)
    else:
        retest = last.high >= level - 0.25 * atr and last.close < level and last.close < last.open
        stop = max(float(m15.high.tail(4).max()), level + 0.15 * atr)
    if not retest or not _five_min_confirm(m5, direction):
        return None
    return _make_candidate(
        symbol, frames, "BREAKOUT_RETEST", "BREAKOUT_RETEST", direction, stop,
        f"1h 20-bar range break aligned with 4h trend; 15m retested {level:.8g} and closed back through it; 5m confirmed.",
        trigger_points=27,
    )


def _volatility_expansion(symbol, frames):
    h4, m15, m5 = frames["4h"], frames["15m"], frames["5m"]
    direction = _trend(h4)
    if direction == 0 or _trend(frames["1h"]) != direction:
        return None
    atr_series = _atr(m15)
    prior_median = float(atr_series.iloc[-49:-1].median())
    current_atr = float(atr_series.iloc[-1])
    if not math.isfinite(prior_median) or prior_median <= 0 or current_atr < 1.25 * prior_median:
        return None
    prior = m15.iloc[-21:-1]
    last = m15.iloc[-1]
    if direction == 1:
        breakout = last.close > float(prior.high.max()) and last.close > last.open
        stop = min(float(m5.low.tail(4).min()), float(last.low)) - 0.12 * current_atr
    else:
        breakout = last.close < float(prior.low.min()) and last.close < last.open
        stop = max(float(m5.high.tail(4).max()), float(last.high)) + 0.12 * current_atr
    if not breakout or not _five_min_confirm(m5, direction):
        return None
    return _make_candidate(
        symbol, frames, "VOLATILITY_EXPANSION", "VOLATILITY_EXPANSION", direction, stop,
        "15m ATR expanded at least 25% above its preceding 48-bar median and price broke a 20-bar range in the 4h/1h trend direction.",
        trigger_points=28,
    )


def _liquidity_sweep(symbol, frames):
    m15, m5 = frames["15m"], frames["5m"]
    previous = m15.iloc[-21:-1]
    last = m15.iloc[-1]
    if len(previous) < 20:
        return None
    prior_high, prior_low = float(previous.high.max()), float(previous.low.min())
    atr = float(_atr(m15).iloc[-1])
    if not math.isfinite(atr) or atr <= 0:
        return None
    body = abs(float(last.close) - float(last.open))
    upper_wick = float(last.high) - max(float(last.open), float(last.close))
    lower_wick = min(float(last.open), float(last.close)) - float(last.low)
    if last.low < prior_low and last.close > prior_low and lower_wick >= max(body, 0.05 * atr):
        direction = 1
        stop = float(last.low) - 0.12 * atr
        text = "15m swept below the prior 20-bar low and closed back above it; 5m confirmed upward."
    elif last.high > prior_high and last.close < prior_high and upper_wick >= max(body, 0.05 * atr):
        direction = -1
        stop = float(last.high) + 0.12 * atr
        text = "15m swept above the prior 20-bar high and closed back below it; 5m confirmed downward."
    else:
        return None
    return _make_candidate(
        symbol, frames, "LIQUIDITY_SWEEP_REVERSAL", "LIQUIDITY_SWEEP_REVERSAL",
        direction, stop, text, trigger_points=27,
    )


def _mean_reversion(symbol, frames):
    h1, m15, m5 = frames["1h"], frames["15m"], frames["5m"]
    middle, upper, lower = _bands(h1.close)
    rsi = _rsi(h1.close)
    h4_atr = float(_atr(frames["4h"]).iloc[-1])
    h4_fast, h4_slow = _ema(frames["4h"].close, 20).iloc[-1], _ema(frames["4h"].close, 50).iloc[-1]
    if not all(math.isfinite(float(x)) for x in (middle.iloc[-1], upper.iloc[-1], lower.iloc[-1], rsi.iloc[-1], h4_atr, h4_fast, h4_slow)):
        return None
    # Only trade re-entry from an outer band in a balanced 4h regime.
    if abs(float(h4_fast) - float(h4_slow)) > 0.8 * h4_atr:
        return None
    previous_close, current_close = float(h1.close.iloc[-2]), float(h1.close.iloc[-1])
    if previous_close < float(lower.iloc[-2]) and current_close > float(lower.iloc[-1]) and float(rsi.iloc[-2]) < 35:
        direction = 1
        stop = float(m15.low.tail(4).min()) - 0.15 * float(_atr(m15).iloc[-1])
        target = float(middle.iloc[-1])
        text = "1h closed back inside its lower Bollinger band after an RSI<35 excursion; 4h EMA spread indicates a balanced regime."
    elif previous_close > float(upper.iloc[-2]) and current_close < float(upper.iloc[-1]) and float(rsi.iloc[-2]) > 65:
        direction = -1
        stop = float(m15.high.tail(4).max()) + 0.15 * float(_atr(m15).iloc[-1])
        target = float(middle.iloc[-1])
        text = "1h closed back inside its upper Bollinger band after an RSI>65 excursion; 4h EMA spread indicates a balanced regime."
    else:
        return None
    return _make_candidate(
        symbol, frames, "MEAN_REVERSION", "MEAN_REVERSION", direction, stop, text,
        trigger_points=40, target=target,
    )


def _momentum_continuation(symbol, frames):
    h4, h1, m15, m5 = frames["4h"], frames["1h"], frames["15m"], frames["5m"]
    direction = _trend(h4)
    if direction == 0 or _trend(h1) != direction:
        return None
    roc = float(h1.close.iloc[-1] / h1.close.iloc[-7] - 1.0) * 100
    if direction * roc < 0.8:
        return None
    prior = m15.iloc[-9:-1]
    last = m15.iloc[-1]
    if direction == 1:
        trigger = last.close > float(prior.high.max()) and last.close > last.open
        stop = min(float(m5.low.tail(5).min()), float(last.low)) - 0.12 * float(_atr(m15).iloc[-1])
    else:
        trigger = last.close < float(prior.low.min()) and last.close < last.open
        stop = max(float(m5.high.tail(5).max()), float(last.high)) + 0.12 * float(_atr(m15).iloc[-1])
    if not trigger or not _five_min_confirm(m5, direction):
        return None
    return _make_candidate(
        symbol, frames, "MOMENTUM_CONTINUATION", "MOMENTUM_CONTINUATION",
        direction, stop,
        f"1h six-bar return is {roc:+.2f}% with 4h/1h trend alignment; 15m displacement and 5m follow-through confirmed.",
        trigger_points=26,
    )


STRATEGIES = (
    _trend_pullback,
    _breakout_retest,
    _volatility_expansion,
    _liquidity_sweep,
    _mean_reversion,
    _momentum_continuation,
)


def generate_candidates(symbol, frames):
    """Evaluate every independent strategy against the same latest closed-bar snapshot."""
    for timeframe in REQUIRED_TIMEFRAMES:
        minimum = 70 if timeframe in ("5m", "15m", "1h", "4h") else 55
        if not _valid_frame(frames.get(timeframe), timeframe, minimum=minimum):
            return []
    candidates = []
    for strategy in STRATEGIES:
        try:
            candidate = strategy(symbol, frames)
        except (ArithmeticError, KeyError, TypeError, ValueError, IndexError):
            candidate = None
        if candidate is not None:
            candidates.append(candidate)
    return candidates
