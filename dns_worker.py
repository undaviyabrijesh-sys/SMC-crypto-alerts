"""Five-minute local DNS watcher with infrequent AI-authored market-map refreshes."""
import json
import os
import uuid

import pandas as pd

import ai_analyst
import config as C
import data
import dns_engine
import discord
import main
import state as st
from visual_chart import render_symbol_chart


def run(now=None, fetcher=data.fetch, mapper=None):
    now = main._utc_now(now)
    state = st.load()
    # Retry confirmed outcomes and pending Discord deliveries before new monitoring.
    for signal_id, outcome in list(state.setdefault("pending_outcomes", {}).items()):
        sym = outcome.get("sym")
        if sym in C.SYMBOLS and discord.send_outcome(outcome, lambda value, s=sym: main._fmt(s, value)):
            del state["pending_outcomes"][signal_id]
    for signal_id, trade in list(state.setdefault("pending_alerts", {}).items()):
        age = now - pd.Timestamp(trade.get("analysis_time", now.isoformat()))
        if age > pd.Timedelta(minutes=10):
            del state["pending_alerts"][signal_id]
            continue
        sym = trade.get("sym")
        if sym in C.SYMBOLS and discord.send_ai_trade(sym, trade, lambda value, s=sym: main._fmt(s, value)):
            state.setdefault("positions", {})[signal_id] = trade
            del state["pending_alerts"][signal_id]
    dns_map = dns_engine.load_map()
    refresh_attempts = state.setdefault("dns_refresh_attempts", {})
    frames_by_symbol = {}
    chart_images = {}
    refresh_due = {}

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
            snapshot = dns_map.get("symbols", {}).get(symbol)
            reasons = dns_engine.refresh_reasons(snapshot, now, frames)
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
            by_symbol = {item.get("symbol"): item for item in result.get("analyses", [])}
            for symbol, analysis in by_symbol.items():
                price = float(frames_by_symbol[symbol]["5m"].iloc[-1].close)
                snapshot = dns_engine.save_analysis(
                    dns_map, symbol, analysis, now, price
                )
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

    seen = state.setdefault("seen_dns_events", [])
    seen_set = set(seen)
    for symbol, frames in frames_by_symbol.items():
        snapshot = dns_map.get("symbols", {}).get(symbol)
        if not snapshot:
            print(f"[dns-wait] {symbol}: waiting for first successful AI DNS map")
            continue
        try:
            candidates = dns_engine.detect_local_setup(symbol, frames, snapshot, now)
        except Exception as exc:
            print(f"[dns-local-error] {symbol}: {type(exc).__name__}: {exc}")
            continue
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
                "confidence": 80, "bias": snapshot.get("bias", "UNCLEAR"),
                "rationale": (
                    f"Local 5m sweep/reclaim confirmed at AI-mapped {candidate['zone_side'].lower()} "
                    f"zone Q{candidate['zone_quality']} ({candidate['zone_timeframe']})."
                ),
                "invalidation": "Stop-loss beyond the sweep extreme.",
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
            seen.append(event_key)
            seen_set.add(event_key)

    state["seen_dns_events"] = seen[-5000:]
    state["last_local_dns_scan_at"] = now.isoformat()
    st.save(state)


if __name__ == "__main__":
    run()
