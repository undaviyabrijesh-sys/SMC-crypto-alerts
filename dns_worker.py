"""Five-minute local DNS watcher with infrequent AI-authored market-map refreshes."""
import json
import math
import os
import uuid
from pathlib import Path

import pandas as pd

import ai_analyst
import ai_trade_agents
import config as C
import data
import dns_engine
import discord
import main
import state as st
from visual_chart import render_symbol_chart


def _append_dns_event(record):
    """Append map and agent-review events to the same auditable research stream."""
    path = Path(os.environ.get("DNS_RESEARCH_PATH", "research/dns_maps.jsonl"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        print(f"[dns-research-log-error] {type(exc).__name__}: {exc}")


def _reprice_pending_alert(trade, current_price, snapshot):
    """Revalidate a delayed Discord alert against the latest closed price and current AI map."""
    try:
        current = float(current_price)
        original_entry = float(trade["entry"])
        stop = float(trade["sl"])
        target = float(trade["tp"])
        selected = trade["selected_entry_zone"]
        selected_low = float(selected["low"])
        selected_high = float(selected["high"])
        selected_timeframe = str(selected["timeframe"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None

    values = (current, original_entry, stop, target, selected_low, selected_high)
    if not all(math.isfinite(value) and value > 0 for value in values):
        return None
    valid_timeframes = {"1w", "1d", "4h", "1h", "15m", "5m"}
    if not (0 < selected_low < selected_high) or selected_timeframe not in valid_timeframes:
        return None
    if abs(current - original_entry) / original_entry * 100 > C.MAX_MARKET_ENTRY_DEVIATION_PCT:
        return None
    selected_gap = max(selected_low - current, current - selected_high, 0.0)
    if selected_gap / current * 100 > C.MAX_MARKET_ENTRY_DEVIATION_PCT:
        return None

    direction = trade.get("dir")
    if direction == "long":
        if not stop < current < target:
            return None
        expected_side = "DEMAND"
        directional_zones = snapshot.get("demand_zones", []) if isinstance(snapshot, dict) else []
        risk, reward = current - stop, target - current
    elif direction == "short":
        if not target < current < stop:
            return None
        expected_side = "SUPPLY"
        directional_zones = snapshot.get("supply_zones", []) if isinstance(snapshot, dict) else []
        risk, reward = stop - current, current - target
    else:
        return None

    rr = reward / risk if risk > 0 else 0.0
    if not math.isfinite(rr) or rr < C.MIN_AI_RR:
        return None

    primary_zone = None
    for zone in directional_zones if isinstance(directional_zones, list) else []:
        if not isinstance(zone, dict):
            continue
        try:
            low = float(zone["low"])
            high = float(zone["high"])
            quality = int(zone.get("quality", 0))
            timeframe = str(zone["timeframe"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            not math.isfinite(low) or not math.isfinite(high)
            or not (0 < low < high)
            or quality < C.MIN_DNS_ZONE_QUALITY or quality > 5
            or timeframe not in valid_timeframes
        ):
            continue
        if min(selected_high, high) - max(selected_low, low) <= 0:
            continue
        zone_gap = max(low - current, current - high, 0.0)
        if zone_gap / current * 100 > C.MAX_MARKET_ENTRY_DEVIATION_PCT:
            continue
        primary_zone = {
            "side": expected_side,
            "low": low,
            "high": high,
            "timeframe": timeframe,
            "quality": quality,
            "evidence": str(zone.get("evidence", "")),
        }
        break

    if primary_zone is None:
        return None
    return {"entry": current, "rr": rr, "primary_zone": primary_zone}


def run(now=None, fetcher=data.fetch, mapper=None, agent_reviewer=None):
    now = main._utc_now(now)
    state = st.load()
    # Retry confirmed outcomes and pending Discord deliveries before new monitoring.
    for signal_id, outcome in list(state.setdefault("pending_outcomes", {}).items()):
        sym = outcome.get("sym")
        if sym in C.SYMBOLS and discord.send_outcome(outcome, lambda value, s=sym: main._fmt(s, value)):
            del state["pending_outcomes"][signal_id]
    # A corrupt/unreadable DNS map must pause new entries, not prevent the
    # existing paper positions from being checked against fresh market candles.
    try:
        dns_map = dns_engine.load_map()
        dns_map_available = True
    except Exception as exc:
        dns_map = {"schema_version": 1, "symbols": {}, "history": {}}
        dns_map_available = False
        print(
            f"[dns-map-fatal] map unavailable; existing positions will still be managed, "
            f"but new entries are paused: {type(exc).__name__}: {exc}"
        )
    refresh_attempts = state.setdefault("dns_refresh_attempts", {})
    frames_by_symbol = {}
    chart_images = {}
    refresh_due = {}
    # A map that is due for refresh must not keep generating new entries if the
    # AI refresh is throttled, fails, or omits that symbol from its response.
    refresh_blocked_symbols = set()

    # Market data is refreshed locally every worker cycle; no AI request is made here.
    for symbol, cfg in C.SYMBOLS.items():
        try:
            frames = data.fetch_bundle(cfg, now, fetcher=fetcher, symbol=symbol)
            if frames.get("5m") is not None and not frames["5m"].empty:
                main.manage_positions(
                    state, symbol, frames["5m"], now,
                    lambda value, s=symbol: main._fmt(s, value)
                )
            usable, reason = data.freshness(frames, now)
            if not usable:
                print(f"[dns-skip] {symbol}: {reason}")
                continue
            frames_by_symbol[symbol] = frames
            if not dns_map_available:
                refresh_blocked_symbols.add(symbol)
                print(
                    f"[dns-wait] {symbol}: DNS map is unreadable; "
                    "existing paper positions were managed and new entries are paused"
                )
                continue
            try:
                snapshot = dns_map.get("symbols", {}).get(symbol)
                reasons = dns_engine.refresh_reasons(snapshot, now, frames)
            except Exception:
                # A malformed map or failed freshness/invalidation check must
                # fail closed; the detector must not reuse an unverified map.
                refresh_blocked_symbols.add(symbol)
                raise
            if reasons:
                refresh_blocked_symbols.add(symbol)
            last_attempt = refresh_attempts.get(symbol)
            if reasons and last_attempt:
                last_attempt_ts = pd.Timestamp(last_attempt)
                last_attempt_ts = last_attempt_ts.tz_localize("UTC") if last_attempt_ts.tzinfo is None else last_attempt_ts.tz_convert("UTC")
                if now - last_attempt_ts < pd.Timedelta(minutes=30):
                    reasons = []
            if reasons:
                refresh_due[symbol] = reasons
                chart_images[symbol] = render_symbol_chart(
                    f"{symbol} · {cfg['delta_symbol']}", frames, now
                )
        except Exception as exc:
            print(f"[dns-error] {symbol} data: {type(exc).__name__}: {exc}")

    # Batch all due symbols into one cheaper map-only multimodal request.
    if chart_images:
        market_context = main.build_context({
            symbol: frames_by_symbol[symbol] for symbol in chart_images
        })
        market_context["_mapping_refresh_reasons"] = refresh_due
        call_mapper = mapper or ai_analyst.map_dns
        for symbol in chart_images:
            refresh_attempts[symbol] = now.isoformat()
        try:
            result, meta = call_mapper(chart_images, market_context)
            by_symbol = {
                item.get("symbol"): item
                for item in result.get("analyses", [])
                if isinstance(item, dict) and item.get("symbol") in chart_images
            }
            for symbol in chart_images:
                analysis = by_symbol.get(symbol)
                if not isinstance(analysis, dict):
                    print(f"[dns-map-error] {symbol}: refresh response omitted its map; skipping new entries")
                    continue
                price = float(frames_by_symbol[symbol]["5m"].iloc[-1].close)
                snapshot = dns_engine.save_analysis(
                    dns_map, symbol, analysis, now, price
                )
                refresh_blocked_symbols.discard(symbol)
                try:
                    main._save_zone_review_chart(
                        symbol, frames_by_symbol[symbol], analysis, now,
                        raw_png=chart_images[symbol]
                    )
                except Exception as exc:
                    print(f"[dns-warn] {symbol} chart review save failed: {type(exc).__name__}")
                print(
                    f"[dns-map] {symbol} revision={snapshot['revision']} "
                    f"demand={len(snapshot['demand_zones'])} supply={len(snapshot['supply_zones'])} "
                    f"model={meta.get('model')}"
                )
            record = {
                "timestamp": now.isoformat(), "kind": "DNS_MAP_REFRESH",
                "model": meta.get("model"), "response_id": meta.get("response_id"),
                "usage": meta.get("usage"), "refresh_reasons": refresh_due,
                "market_context": market_context, "analysis": result,
            }
            path = os.environ.get("DNS_RESEARCH_PATH", "research/dns_maps.jsonl")
            from pathlib import Path
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:
            # Keep using the last valid map; do not erase it when AI is unavailable.
            print(f"[dns-map-error] refresh failed; retaining last map: {type(exc).__name__}: {exc}")

    # Retry pending execution alerts only after fresh market data and current-map checks.
    # A delayed webhook retry must never publish an entry that has already moved or lost 2R.
    for signal_id, trade in list(state.setdefault("pending_alerts", {}).items()):
        age = now - pd.Timestamp(trade.get("analysis_time", now.isoformat()))
        if age > pd.Timedelta(minutes=10):
            del state["pending_alerts"][signal_id]
            continue
        symbol = trade.get("sym")
        if symbol not in C.SYMBOLS or symbol in refresh_blocked_symbols:
            continue
        frames = frames_by_symbol.get(symbol)
        m5 = frames.get("5m") if isinstance(frames, dict) else None
        if m5 is None or m5.empty:
            continue
        snapshot = dns_map.get("symbols", {}).get(symbol)
        current_price = float(m5.iloc[-1].close)
        revalidated = _reprice_pending_alert(trade, current_price, snapshot)
        if revalidated is None:
            del state["pending_alerts"][signal_id]
            print(f"[dns-expired] {symbol} {signal_id}: delayed alert is no longer actionable")
            continue
        retry_trade = {
            **trade,
            **revalidated,
            "triggered_at": (pd.Timestamp(m5.index[-1]) + pd.Timedelta(minutes=5)).isoformat(),
        }
        if discord.send_ai_trade(
            symbol, retry_trade, lambda value, s=symbol: main._fmt(s, value)
        ):
            state.setdefault("positions", {})[signal_id] = retry_trade
            del state["pending_alerts"][signal_id]

    seen = state.setdefault("seen_dns_events", [])
    seen_set = set(seen)
    for symbol, frames in frames_by_symbol.items():
        if symbol in refresh_blocked_symbols:
            print(f"[dns-wait] {symbol}: required AI DNS refresh is pending; skipping new entries")
            continue
        snapshot = dns_map.get("symbols", {}).get(symbol)
        if not snapshot:
            print(f"[dns-wait] {symbol}: waiting for first successful AI DNS map")
            continue
        try:
            candidates = dns_engine.detect_local_setup(symbol, frames, snapshot, now)
        except Exception as exc:
            print(f"[dns-local-error] {symbol}: {type(exc).__name__}: {exc}")
            continue
        # Keep model cost bounded: debate at most one unseen DNS opportunity
        # per symbol per five-minute cycle, preferring cleaner zones then higher R.
        candidates = sorted(
            candidates or [],
            key=lambda item: (
                -int(item.get("zone_quality", 0)),
                -float(item.get("rr", 0.0)),
                str(item.get("zone_id", "")),
            ),
        )
        for candidate in candidates:
            active_for_symbol = any(
                item.get("sym") == symbol
                for item in list(state.get("positions", {}).values())
                + list(state.get("pending_alerts", {}).values())
            )
            if active_for_symbol:
                continue
            event_key = "|".join([
                symbol, str(candidate["zone_id"]), candidate["setup_type"],
                candidate["event_candle"]
            ])
            if event_key in seen_set:
                continue

            # One debate attempt per local event. API failures are rate-limited so
            # a quota outage cannot trigger a request every five-minute candle.
            reviewer = agent_reviewer or ai_trade_agents.review_candidate
            cooldowns = state.setdefault("ai_review_cooldown_until", {})
            if not isinstance(cooldowns, dict):
                cooldowns = {}
                state["ai_review_cooldown_until"] = cooldowns
            cooldown_raw = cooldowns.get(symbol)
            review = None
            if cooldown_raw:
                try:
                    cooldown_until = pd.Timestamp(cooldown_raw)
                    cooldown_until = (
                        cooldown_until.tz_localize("UTC")
                        if cooldown_until.tzinfo is None else cooldown_until.tz_convert("UTC")
                    )
                    if now < cooldown_until:
                        review = {"status": "COOLDOWN", "reason": "AI review failure cooldown is active"}
                except (TypeError, ValueError):
                    cooldowns.pop(symbol, None)
            if review is None:
                try:
                    review = reviewer(candidate, snapshot, frames)
                    if not isinstance(review, dict):
                        review = {"status": "ERROR", "error": "agent reviewer returned a non-object"}
                except Exception as exc:
                    review = {"status": "ERROR", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}

            if review.get("status") == "ERROR":
                try:
                    cooldown_minutes = max(5, int(os.environ.get("AI_TRADE_REVIEW_FAILURE_COOLDOWN_MINUTES", "30")))
                except (TypeError, ValueError):
                    cooldown_minutes = 30
                cooldowns[symbol] = (now + pd.Timedelta(minutes=cooldown_minutes)).isoformat()

            # Record every review outcome before deciding whether the event can proceed.
            _append_dns_event({
                "timestamp": now.isoformat(),
                "kind": "DNS_AGENT_REVIEW",
                "event_key": event_key,
                "symbol": symbol,
                "map_revision": snapshot.get("revision"),
                "candidate": candidate,
                "review": review,
            })
            seen.append(event_key)
            seen_set.add(event_key)

            if not ai_trade_agents.allows_candidate(review):
                print(
                    f"[dns-agent-veto] {symbol} {candidate['setup_type']}: "
                    f"{review.get('status')} {review.get('reason') or review.get('error') or review.get('decision')}"
                )
                # Do not burn more agent calls debating lower-ranked candidates this cycle.
                break

            signal_id = uuid.uuid4().hex[:12].upper()
            direction = candidate["direction"].lower()
            primary_zone = {
                "side": candidate["zone_side"], "low": candidate["zone_low"],
                "high": candidate["zone_high"], "timeframe": candidate["zone_timeframe"],
                "quality": candidate["zone_quality"], "evidence": "AI visual DNS map",
            }
            trade = {
                **candidate, "signal_id": signal_id, "sym": symbol,
                "dir": direction, "sl": candidate["stop_loss"],
                "tp": candidate["take_profit"], "tp2": None,
                "bias": snapshot.get("bias", "UNCLEAR"),
                "rationale": candidate.get("rationale") or (
                    f"Local 5m {candidate['setup_type']} confirmed at AI-mapped "
                    f"{candidate['zone_side'].lower()} zone Q{candidate['zone_quality']} "
                    f"({candidate['zone_timeframe']})."
                ),
                "invalidation": candidate.get(
                    "invalidation", "The mapped DNS band and structural stop define invalidation."
                ),
                "primary_zone": primary_zone,
                "selected_entry_zone": {
                    "low": candidate["zone_low"], "high": candidate["zone_high"],
                    "timeframe": candidate["zone_timeframe"],
                    "evidence": "AI visual DNS zone; local sweep/reclaim trigger",
                },
                "timeframes_in_agreement": [],
                "triggered_at": (
                    pd.Timestamp(candidate["event_candle"]) + pd.Timedelta(minutes=5)
                ).isoformat(),
                "status": "OPEN", "entry_source": "LOCAL_DNS_PAPER",
                "analysis_time": now.isoformat(),
                "agent_review": {
                    "status": review.get("status"),
                    "decision": review.get("decision"),
                    "bull_stance": (review.get("bull") or {}).get("stance") if isinstance(review.get("bull"), dict) else None,
                    "bear_stance": (review.get("bear") or {}).get("stance") if isinstance(review.get("bear"), dict) else None,
                    "trader_rationale": (review.get("trader") or {}).get("rationale") if isinstance(review.get("trader"), dict) else None,
                },
            }
            if discord.send_ai_trade(symbol, trade, lambda value: main._fmt(symbol, value)):
                state.setdefault("positions", {})[signal_id] = trade
                print(
                    f"[dns-signal] {symbol} {candidate['direction']} "
                    f"{candidate['setup_type']} {candidate['rr']:.2f}R"
                )
            else:
                state.setdefault("pending_alerts", {})[signal_id] = trade
                print(f"[dns-pending] {symbol} {signal_id}: Discord delivery pending")
    state["seen_dns_events"] = seen[-5000:]
    state["last_local_dns_scan_at"] = now.isoformat()
    st.save(state)


if __name__ == "__main__":
    run()
