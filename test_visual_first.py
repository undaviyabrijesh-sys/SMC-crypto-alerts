"""Offline tests for independent visual-first analysis and paper lifecycle integration."""
import os
import tempfile

import pandas as pd

import config as C
import discord
import state as state_module
import visual_first_analyst
import visual_worker
import worker


def _frames(now):
    frames = {}
    for timeframe, minutes in visual_worker.data.MINUTES.items():
        last_open = now - pd.Timedelta(minutes=2 * minutes)
        index = pd.date_range(end=last_open, periods=30, freq=f"{minutes}min")
        frames[timeframe] = pd.DataFrame({
            "open": [100.0] * len(index),
            "high": [101.0] * len(index),
            "low": [99.0] * len(index),
            "close": [100.0] * len(index),
            "volume": [1000.0] * len(index),
        }, index=index)
    return frames


def _candidate(candidate_id="trend-long", direction="LONG", quality=82, confidence=85):
    if direction == "LONG":
        stop, target = 98.5, 103.0
    else:
        stop, target = 101.5, 97.0
    return {
        "candidate_id": candidate_id,
        "setup_family": "TREND_PULLBACK",
        "direction": direction,
        "trigger_timeframe": "5m",
        "entry_type": "MARKET",
        "entry_zone": {
            "low": 99.5, "high": 100.5, "timeframe": "5m",
            "evidence": "Price is inside the visually identified execution band.",
        },
        "trigger_condition": "The latest closed 5m candle confirmed the continuation trigger.",
        "higher_timeframe_context": "The 4h and 1h panels show aligned directional context.",
        "supporting_evidence": [
            "1h structure holds higher lows.",
            "15m pullback holds the prior breakout area.",
            "5m close confirms continuation.",
        ],
        "evidence_timeframes": ["4h", "1h", "15m", "5m"],
        "conflicting_evidence": [],
        "timeframes_in_agreement": ["4h", "1h", "15m"],
        "stop_loss": stop,
        "target_1": target,
        "reward_risk": 2.0,
        "target_rationale": "The first target is beyond the nearest opposing swing obstacle.",
        "invalidation": "A close beyond the structural pullback low/high invalidates the thesis.",
        "cancel_if": ["Cancel if the latest price leaves the entry band before the alert is delivered."],
        "confidence": confidence,
        "quality_score": quality,
        "selection_rationale": "This is the cleanest aligned trend-pullback candidate; competing evidence is weaker.",
    }


def _analysis(symbol, now, frames, cycle_id, candidates=None, selected="trend-long", action="TRADE"):
    watermarks = visual_worker._watermarks(frames)
    return {
        "symbol": symbol,
        "as_of_utc": now.isoformat(),
        "chart_watermarks": watermarks,
        "candidates": candidates if candidates is not None else [_candidate()],
        "selected_candidate_id": selected,
        "action": action,
        "comparison_summary": "Trend pullback is clearest; other families lack a confirmed immediate trigger.",
    }


def test_visual_cycle_id_changes_when_chart_image_changes_on_same_candles():
    watermarks = {
        "BTC": {timeframe: f"2026-11-06T00:00:00+00:00" for timeframe in visual_worker.TIMEFRAMES}
    }
    first_hashes = {"BTC": "a" * 64}
    retry_hashes = {"BTC": "b" * 64}

    first_cycle = visual_worker._visual_cycle_id(watermarks, first_hashes)
    retry_cycle = visual_worker._visual_cycle_id(watermarks, retry_hashes)

    assert first_cycle == visual_worker._visual_cycle_id(watermarks, first_hashes)
    assert first_cycle != retry_cycle


def test_visual_cycle_id_rejects_mismatched_chart_evidence_sets():
    watermarks = {"BTC": {timeframe: "2026-11-06T00:00:00+00:00" for timeframe in visual_worker.TIMEFRAMES}}
    try:
        visual_worker._visual_cycle_id(watermarks, {"ETH": "b" * 64})
    except ValueError as exc:
        assert "same non-empty symbols" in str(exc)
    else:
        raise AssertionError("mismatched chart evidence must fail closed")


def test_schema_supports_independent_families_without_dns_fields():
    schema_text = str(visual_first_analyst.OUTPUT_SCHEMA)
    assert "TREND_PULLBACK" in schema_text
    assert "MEAN_REVERSION" in schema_text
    assert "BREAKOUT_RETEST" in schema_text
    assert "demand_zones" not in schema_text
    assert "supply_zones" not in schema_text
    prompt = visual_first_analyst.SYSTEM_PROMPT.lower()
    assert "no mandatory dns anchor" in prompt
    assert "independent candidates" in prompt


def test_independent_trend_candidate_passes_without_dns_zones():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    analysis = _analysis("BTC", now, frames, "cycle")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert reason == "validated"
    assert plan["setup_family"] == "TREND_PULLBACK"
    assert plan["rr"] >= 2.0
    assert plan["stop_atr"] >= 0.35
    assert "primary_zone" not in plan


def test_future_retest_is_not_promoted_to_market_entry():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    candidate = _candidate()
    candidate["entry_type"] = "RETEST"
    analysis = _analysis("BTC", now, frames, "cycle", [candidate])
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "future limit/retest" in reason


def test_risk_gates_reject_sub_two_r_and_stop_outside_atr_band():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    candidate = _candidate()
    candidate["target_1"] = 102.0
    candidate["reward_risk"] = 1.3333333333333333
    analysis = _analysis("BTC", now, frames, "cycle", [candidate])
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "minimum 2.0R" in reason

    candidate = _candidate()
    candidate["stop_loss"] = 99.8
    candidate["target_1"] = 100.4
    candidate["reward_risk"] = 2.0
    analysis = _analysis("BTC", now, frames, "cycle", [candidate])
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "0.35–2.5" in reason


def test_boolean_price_and_duplicate_candidate_ids_fail_closed():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    candidate = _candidate()
    candidate["stop_loss"] = True
    analysis = _analysis("BTC", now, frames, "cycle", [candidate])
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "invalid price levels" in reason

    first, second = _candidate(), _candidate()
    analysis = _analysis("BTC", now, frames, "cycle", [first, second])
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "duplicated" in reason


def test_conflicting_opposite_candidates_with_close_quality_return_no_trade():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    long = _candidate("long", "LONG", 82, 85)
    short = _candidate("short", "SHORT", 78, 80)
    analysis = _analysis("BTC", now, frames, "cycle", [long, short], selected="long")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "opposing actionable candidate" in reason


def test_stronger_opposing_candidate_blocks_the_models_weaker_selection():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    long = _candidate("long", "LONG", 75, 85)
    short = _candidate("short", "SHORT", 85, 90)
    analysis = _analysis("BTC", now, frames, "cycle", [long, short], selected="long")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "opposing actionable candidates" in reason


def test_opposing_candidate_exactly_eight_points_weaker_passes_margin():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    long = _candidate("long", "LONG", 90, 92)
    short = _candidate("short", "SHORT", 82, 85)
    analysis = _analysis("BTC", now, frames, "cycle", [long, short], selected="long")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert reason == "validated"
    assert plan["candidate_id"] == "long"


def test_model_selected_side_passes_when_opposing_candidate_is_clearly_weaker():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    long = _candidate("long", "LONG", 90, 92)
    short = _candidate("short", "SHORT", 70, 75)
    analysis = _analysis("BTC", now, frames, "cycle", [long, short], selected="long")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert reason == "validated"
    assert plan["candidate_id"] == "long"


def test_validator_checks_model_selected_candidate_without_substituting_and_rejects_missing_id():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    selected = _candidate("selected", "LONG", 82, 85)
    other = _candidate("other", "LONG", 90, 91)
    analysis = _analysis("BTC", now, frames, "cycle", [selected, other], selected="selected")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert reason == "validated"
    assert plan["candidate_id"] == "selected"

    analysis = _analysis("BTC", now, frames, "cycle", [_candidate()], selected="missing")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "not present" in reason


def test_stale_chart_watermark_open_position_and_no_trade_are_rejected():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    analysis = _analysis("BTC", now, frames, "cycle")
    stale = dict(analysis["chart_watermarks"])
    stale["1h"] = "2026-11-06T00:00:00+00:00"
    analysis["chart_watermarks"] = stale
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "watermarks" in reason

    analysis = _analysis("BTC", now, frames, "cycle")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames),
        has_open_position=True, now=now
    )
    assert plan is None and "open or pending" in reason

    analysis = _analysis("BTC", now, frames, "cycle", [], selected=None, action="NO_TRADE")
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and reason == "AI selected NO_TRADE"


def test_response_coverage_checks_schema_version_cycle_and_each_symbol_once():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    result = {
        "schema_version": 2,
        "cycle_id": "cycle-1",
        "market_commentary": "",
        "analyses": [_analysis("BTC", now, frames, "cycle-1")],
    }
    by_symbol = visual_first_analyst.validate_response_coverage(result, {"BTC"}, "cycle-1")
    assert set(by_symbol) == {"BTC"}
    try:
        visual_first_analyst.validate_response_coverage(result, {"BTC", "ETH"}, "cycle-1")
    except ValueError as exc:
        assert "coverage mismatch" in str(exc)
    else:
        raise AssertionError("missing symbol analysis must fail closed")


def test_mocked_end_to_end_visual_paper_cycle_and_same_candle_deduplication():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    original_symbols = C.SYMBOLS
    original_path = state_module.PATH
    old_research = os.environ.get("VISUAL_FIRST_RESEARCH_PATH")
    old_chart_dir = os.environ.get("VISUAL_FIRST_CHART_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="salty-visual-first-") as folder:
            C.SYMBOLS = {"BTC": {"delta_symbol": "BTCUSD", "kind": "crypto", "dp": 1}}
            state_module.PATH = os.path.join(folder, "state.json")
            os.environ["VISUAL_FIRST_RESEARCH_PATH"] = os.path.join(folder, "decisions.jsonl")
            os.environ["VISUAL_FIRST_CHART_DIR"] = os.path.join(folder, "charts")
            original_renderer = visual_worker.render_symbol_chart
            original_sender = discord.send_visual_trade
            original_outcome = discord.send_outcome
            try:
                visual_worker.render_symbol_chart = lambda *args, **kwargs: b"mock-png-image"
                sent = []
                discord.send_visual_trade = lambda symbol, trade, fmt: sent.append((symbol, trade.copy())) or True
                discord.send_outcome = lambda *args, **kwargs: True
                calls = []

                def fake_analyser(images, market_context, active_positions=None):
                    calls.append(set(images))
                    cycle = market_context["_visual_first"]["cycle_id"]
                    analysis = _analysis("BTC", now, frames, cycle)
                    return {
                        "schema_version": 2,
                        "cycle_id": cycle,
                        "market_commentary": "Mocked offline contract test.",
                        "analyses": [analysis],
                    }, {"model": "mock-vision", "response_id": "mock-response", "usage": {}}

                loader = lambda cfg, timestamp, symbol: frames
                first = visual_worker.run(
                    now=now, analyzer=fake_analyser, enabled=True, frames_loader=loader
                )
                assert first["status"] == "ok"
                assert first["analyzed"] == 1
                assert first["signals"] == 1
                assert len(sent) == 1
                assert sent[0][1]["setup_family"] == "TREND_PULLBACK"
                saved = state_module.load()
                assert len(saved["positions"]) == 1
                assert saved["last_visual_candle"]["BTC"] == frames["5m"].index[-1].isoformat()
                assert os.path.exists(os.environ["VISUAL_FIRST_RESEARCH_PATH"])
                chart_dir = os.path.join(
                    os.environ["VISUAL_FIRST_CHART_DIR"], sent[0][1]["cycle_id"]
                )
                chart_path = os.path.join(chart_dir, "BTC.png")
                manifest_path = os.path.join(chart_dir, "manifest.json")
                assert open(chart_path, "rb").read() == b"mock-png-image"
                manifest = visual_worker.json.loads(open(manifest_path, encoding="utf-8").read())
                assert manifest["cycle_id"] == sent[0][1]["cycle_id"]
                assert manifest["charts"][0]["sha256"] == visual_worker.hashlib.sha256(
                    b"mock-png-image"
                ).hexdigest()
                assert manifest["charts"][0]["chart_watermarks"] == visual_worker._watermarks(frames)

                second = visual_worker.run(
                    now=now, analyzer=fake_analyser, enabled=True, frames_loader=loader
                )
                assert second["status"] == "no_new_candle"
                assert len(calls) == 1
                assert len(sent) == 1
                assert len(state_module.load()["positions"]) == 1
            finally:
                visual_worker.render_symbol_chart = original_renderer
                discord.send_visual_trade = original_sender
                discord.send_outcome = original_outcome
    finally:
        C.SYMBOLS = original_symbols
        state_module.PATH = original_path
        if old_research is None:
            os.environ.pop("VISUAL_FIRST_RESEARCH_PATH", None)
        else:
            os.environ["VISUAL_FIRST_RESEARCH_PATH"] = old_research
        if old_chart_dir is None:
            os.environ.pop("VISUAL_FIRST_CHART_DIR", None)
        else:
            os.environ["VISUAL_FIRST_CHART_DIR"] = old_chart_dir


def test_visual_worker_is_disabled_without_explicit_paper_opt_in():
    old = os.environ.pop("ENABLE_VISUAL_PAPER", None)
    try:
        result = visual_worker.run(enabled=None)
        assert result["status"] == "disabled"
    finally:
        if old is not None:
            os.environ["ENABLE_VISUAL_PAPER"] = old


def test_visual_discord_alert_is_execution_focused_and_explains_setup():
    captured = {}
    original_post = discord._post
    try:
        discord._post = lambda content: captured.setdefault("content", content) and True
        trade = {
            "signal_id": "VISUAL01", "dir": "long", "setup_family": "TREND_PULLBACK",
            "confidence": 85, "quality_score": 82, "entry_zone": {
                "low": 99.5, "high": 100.5, "timeframe": "5m"
            },
            "entry": 100.0, "sl": 98.5, "tp": 103.0, "rr": 2.0,
            "trigger_timeframe": "5m", "trigger_condition": "Closed 5m confirmation.",
            "higher_timeframe_context": "4h and 1h are aligned.",
            "supporting_evidence": ["1h higher lows", "15m pullback hold"],
            "conflicting_evidence": [], "invalidation": "5m close below the swing low.",
            "target_rationale": "First opposing swing high.", "cancel_if": ["Price leaves the zone."],
        }
        assert discord.send_visual_trade("BTC", trade, lambda value: f"{value:.1f}")
    finally:
        discord._post = original_post
    message = captured["content"]
    assert "TREND_PULLBACK" in message
    assert "Entry:" in message and "Stop-loss:" in message and "Target 1:" in message
    assert "Invalidation:" in message and "Trigger:" in message
    assert "WATCH" not in message and "NO_TRADE" not in message



def test_visual_analyst_builds_a_multimodal_v2_request_without_network():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    analysis = _analysis("BTC", now, frames, "cycle-api-test")
    response_payload = {
        "schema_version": 2,
        "cycle_id": "cycle-api-test",
        "market_commentary": "Mocked chart review.",
        "analyses": [analysis],
    }
    captured = {}
    original_post = visual_first_analyst.requests.post
    original_key = os.environ.get("OPENAI_API_KEY")
    try:
        os.environ["OPENAI_API_KEY"] = "unit-test-key"

        class FakeResponse:
            ok = True
            def json(self):
                return {"id": "resp-mock", "output_text": __import__("json").dumps(response_payload)}

        def fake_post(url, headers, json, timeout):
            captured.update({"url": url, "headers": headers, "body": json, "timeout": timeout})
            return FakeResponse()

        visual_first_analyst.requests.post = fake_post
        parsed, meta = visual_first_analyst.analyse(
            {"BTC": b"raw-chart-image"},
            {"_visual_first": {"cycle_id": "cycle-api-test"}},
            active_positions={},
        )
    finally:
        visual_first_analyst.requests.post = original_post
        if original_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = original_key

    assert parsed["schema_version"] == 2
    assert parsed["analyses"][0]["symbol"] == "BTC"
    assert meta["response_id"] == "resp-mock"
    assert captured["url"].endswith("/v1/responses")
    content = captured["body"]["input"][1]["content"]
    assert any(item.get("type") == "input_image" for item in content)
    assert "data:image/png;base64," in next(
        item["image_url"] for item in content if item.get("type") == "input_image"
    )
    prompt_text = captured["body"]["input"][0]["content"][0]["text"]
    assert "NO MANDATORY DNS ANCHOR" in prompt_text
    assert "timeframes_in_agreement" in prompt_text
    assert "at least two distinct panels" in prompt_text


def test_worker_dispatches_visual_mode_without_changing_default_quant_mode():
    original_mode = worker.WORKER_MODE
    original_run = visual_worker.run
    called = []
    try:
        worker.WORKER_MODE = "visual"
        visual_worker.run = lambda: called.append("visual")
        worker._run_cycle()
    finally:
        worker.WORKER_MODE = original_mode
        visual_worker.run = original_run
    assert called == ["visual"]
    assert original_mode == "quant"



def test_visual_alert_retry_preserves_original_analysis_expiry():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    candle_open = now - pd.Timedelta(minutes=5)
    frames = {
        "BTC": {
            "5m": pd.DataFrame(
                {"close": [100.0]},
                index=pd.DatetimeIndex([candle_open]),
            )
        }
    }
    original_analysis_time = (now - pd.Timedelta(minutes=9)).isoformat()
    signal_id = "VISUAL-PENDING-01"
    state = {
        "positions": {},
        "pending_visual_alerts": {
            signal_id: {
                "sym": "BTC",
                "analysis_time": original_analysis_time,
                "_candidate": {},
            }
        },
    }

    original_validate = visual_worker._validate_candidate
    original_send = discord.send_visual_trade
    original_save = visual_worker.st.save
    try:
        visual_worker._validate_candidate = lambda candidate, price, symbol_frames: (
            {"dir": "long", "setup_family": "TREND_PULLBACK", "rr": 2.0},
            "validated",
        )
        discord.send_visual_trade = lambda *args, **kwargs: False
        visual_worker.st.save = lambda value: None

        first = visual_worker._retry_pending_visual_alerts(state, frames, now)
        assert first == {"delivered": 0, "dropped": 0}
        assert state["pending_visual_alerts"][signal_id]["analysis_time"] == original_analysis_time

        second = visual_worker._retry_pending_visual_alerts(
            state, frames, now + pd.Timedelta(minutes=2)
        )
        assert second == {"delivered": 0, "dropped": 1}
        assert signal_id not in state["pending_visual_alerts"]
    finally:
        visual_worker._validate_candidate = original_validate
        discord.send_visual_trade = original_send
        visual_worker.st.save = original_save


def test_visual_state_schema_adds_dedup_and_pending_delivery_fields():
    original_path = state_module.PATH
    try:
        with tempfile.TemporaryDirectory(prefix="salty-visual-state-") as folder:
            state_module.PATH = os.path.join(folder, "state.json")
            state = state_module.load()
            assert state["last_visual_candle"] == {}
            assert state["pending_visual_alerts"] == {}
            assert state["visual_ai_cooldown_until"] is None
    finally:
        state_module.PATH = original_path


def test_stale_or_future_analysis_timestamp_fails_closed():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    stale = _analysis("BTC", now - pd.Timedelta(minutes=3), frames, "cycle")
    plan, reason = visual_worker.validate_analysis(
        stale, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "timestamp is stale" in reason

    future = _analysis("BTC", now + pd.Timedelta(minutes=3), frames, "cycle")
    plan, reason = visual_worker.validate_analysis(
        future, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "timestamp is stale" in reason


def test_duplicate_candidate_ids_fail_closed_even_for_no_trade():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    duplicate = _candidate()
    analysis = _analysis(
        "BTC", now, frames, "cycle", [duplicate, dict(duplicate)],
        selected=None, action="NO_TRADE"
    )
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "duplicated" in reason


def test_recent_missing_candle_blocks_freshness_and_atr_risk_calculation():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    usable, reason = visual_worker.data.freshness(frames, now)
    assert usable, reason

    gapped = dict(frames)
    gapped["5m"] = frames["5m"].drop(frames["5m"].index[-5])
    usable, reason = visual_worker.data.freshness(gapped, now)
    assert not usable and "5m feed has a gap" in reason
    assert visual_worker._atr(frames["5m"], timeframe="5m") is not None
    assert visual_worker._atr(gapped["5m"], timeframe="5m") is None

    older_gap = dict(frames)
    older_gap["5m"] = frames["5m"].drop(frames["5m"].index[2])
    usable, reason = visual_worker.data.freshness(older_gap, now)
    assert usable, reason


def test_candidate_requires_two_distinct_timeframe_alignment_references():
    now = pd.Timestamp("2026-11-06T02:00:00Z")
    frames = _frames(now)
    candidate = _candidate()
    candidate["timeframes_in_agreement"] = ["4h"]
    analysis = _analysis("BTC", now, frames, "cycle", [candidate])
    plan, reason = visual_worker.validate_analysis(
        analysis, 100.0, frames, visual_worker._watermarks(frames), now=now
    )
    assert plan is None and "at least two distinct" in reason



def test_visual_discord_alert_is_bounded_and_preserves_required_sections():
    captured = {}
    original_post = discord._post
    try:
        discord._post = lambda content: captured.setdefault("content", content) and True
        trade = _candidate()
        trade.update({
            "signal_id": "VISUAL-LONG-01",
            "dir": "long",
            "setup_family": "OTHER_EVIDENCE_SUPPORTED",
            "quality_score": 100,
            "confidence": 100,
            "entry": 100.0,
            "sl": 98.0,
            "tp": 104.0,
            "rr": 2.0,
            "trigger_condition": "T" * 1000,
            "higher_timeframe_context": "H" * 1000,
            "rationale": "R" * 1000,
            "target_rationale": "G" * 1000,
            "invalidation": "I" * 1000,
            "supporting_evidence": ["S" * 1000] * 3,
            "conflicting_evidence": ["C" * 1000] * 2,
            "cancel_if": ["K" * 1000] * 2,
        })
        assert discord.send_visual_trade("BTC", trade, lambda value: f"{value:.2f}")
    finally:
        discord._post = original_post
    message = captured["content"]
    assert len(message) <= 1900
    assert message.endswith("Paper tracking only at the latest closed 5m price; no exchange order is submitted.")
    assert all(section in message for section in (
        "Entry:", "Stop-loss:", "Target 1:", "Invalidation:",
        "Conflicts considered:", "Cancel before entry if:",
    ))


def test_visual_discord_alert_uses_real_line_breaks():
    captured = {}
    original_post = discord._post
    try:
        discord._post = lambda content: captured.setdefault("content", content) and True
        trade = _candidate()
        trade.update({
            "signal_id": "VISUAL-NEWLINE-01",
            "dir": "long",
            "entry": 100.0,
            "sl": 98.5,
            "tp": 103.0,
            "rr": 2.0,
            "rationale": "Aligned trend pullback.",
        })
        assert discord.send_visual_trade("BTC", trade, lambda value: f"{value:.1f}")
    finally:
        discord._post = original_post

    message = captured["content"]
    lines = message.splitlines()
    assert len(lines) >= 10
    assert "\\n" not in message
    assert any(line.startswith("Visual quality:") for line in lines)
    assert any(line.startswith("Entry zone (5m):") for line in lines)
    assert any(line.startswith("Entry:") for line in lines)
    assert any(line.startswith("Stop-loss:") for line in lines)
    assert any(line.startswith("Invalidation:") for line in lines)

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
