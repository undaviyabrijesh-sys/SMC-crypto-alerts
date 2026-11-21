
# TradingAgents-inspired architecture for Salty Quant

## Objective

Reuse the useful coordination ideas from [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) without importing its stock/fundamental-data assumptions or replacing Salty Quant's local SMC and risk logic.

The integration is event-driven. Models do not analyse every five-minute candle.

## Role mapping

| Trading desk role | Salty Quant component | Work |
|---|---|---|
| Market structure analyst | `ai_analyst.map_dns` | Visually maps demand/supply bands, timeframe, quality, structure and observations from synchronized six-timeframe charts. |
| Liquidity analyst | `ai_analyst.map_dns` + `dns_engine` | The visual map records EQH/EQL and swing liquidity; local OHLCV checks test the configured DNS trigger. Wick sweeps remain proxies, not proof of resting orders. |
| Technical analyst | `dns_engine.detect_local_setup` | Independently checks closed 5m candles for sweep/reclaim, demand/supply rejection, BOS/CHOCH confirmation, trend pullback, FVG retrace and RBS/SBR role-reversal retests at an active mapped zone. It does not create or widen AI zones. |
| Bull researcher | `ai_trade_agents.py` | Independently argues for the exact candidate using only the supplied map and closed OHLCV evidence. |
| Bear researcher | `ai_trade_agents.py` | Independently tries to disprove it, including invalidation, opposing zones, conflicting context and poor reward space. |
| Chief trader | `ai_trade_agents.py` | Reviews both reports and returns APPROVE, REJECT or NO_TRADE. |
| Risk manager | `dns_engine` + existing deterministic validators | Price ordering, DNS quality/location, entry proximity, minimum R:R, latest-price revalidation and one open paper position per symbol remain mechanical gates. The model cannot waive them or edit levels. |
| Portfolio / memory | `state.py`, `trade_lifecycle.py`, DNS map history and JSONL research log | Tracks paper positions, confirmed TP/SL/TIME outcomes, map revisions and agent decisions for later evaluation. |

## Credit-control design

1. The DNS map is refreshed only when absent, older than `DNS_MAP_REFRESH_HOURS` (default four hours), or invalidated by a confirmed close through a mapped zone. Due symbols are batched into one visual request.
2. The local watcher checks fresh closed candles on each five-minute worker cycle. No model request is made for a candle that produces no DNS candidate.
3. If `AI_TRADE_DEBATE_ENABLED=true`, a newly detected candidate triggers exactly three sequential Responses API calls: Bull Researcher, Bear Researcher, then Chief Trader. The event is recorded once; provider failures activate a per-symbol cooldown (default 30 minutes).
4. When debate is enabled, only an explicit Chief Trader APPROVE can continue to the deterministic gates and paper-alert path. API errors, malformed responses, REJECT and NO_TRADE fail closed.
5. When debate is disabled (the default), the DNS lane remains map-plus-local-watcher and follows its existing deterministic candidate rules.

This is deliberately smaller than a full TradingAgents clone. It keeps the useful adversarial review while avoiding repeated analyst debates on every bar.

## Runtime selection

The persistent `worker.py` supports two modes:

- `WORKER_MODE=quant` (default): the deterministic six-family OHLCV research lane. It makes no AI calls and does not consume the DNS map.
- `WORKER_MODE=dns`: the visual DNS mapping and local DNS watcher lane. DNS map refresh requires `OPENAI_API_KEY`; the Bull/Bear/Chief review is separately optional.

For the DNS lane, configure in the private `.env` file:

`WORKER_MODE=dns`

`OPENAI_API_KEY=<your key>`

`OPENAI_MODEL=gpt-6-luna`

`OPENAI_REASONING_EFFORT=low`

To enable the additional three-call debate:

`AI_TRADE_DEBATE_ENABLED=true`

The key must never be committed or pasted into a chat. Keep one persistent worker instance. Do not enable both a local worker and a scheduled workflow for the same state/Discord stream.

## Safety and evidence boundaries

- Both lanes are paper-only. No exchange order endpoint is used.
- The default worker mode remains `quant`; changing code does not enable schedules, deployments or live trading.
- The agent team is advisory. It can veto a candidate but cannot manufacture an entry, stop, target, DNS band or liquidity level.
- The visual map's zone evidence is preserved with map revisions. New zones are not inferred by a deterministic zone algorithm.
- The local DNS watcher now checks six independent, DNS-anchored families: liquidity sweep/reclaim, zone rejection, BOS/CHOCH confirmation, trend pullback, FVG retrace and RBS/SBR retest. Each requires an active AI-authored directional zone, a latest closed 5m confirmation, a nearby entry (<=0.35% from the band), an active opposing mapped DNS target and at least 2R. These are deterministic OHLCV proxies and triggers, not proof of institutional order flow.
- A successful API response or green unit test is not evidence of a profitable strategy. The strategy allowlist, historical OOS and walk-forward promotion requirements remain unchanged.
- Missing historical spread/depth and unresolved funding attribution remain explicit research limitations.

## Validation

Offline contract coverage lives in `test_ai_trade_agents.py`. The main CI workflow also runs `test_dns_engine.py`, which exercises map persistence, refresh failure handling, local event detection and paper-alert safety. Live model access, API quota, Discord delivery and any persistent deployment must be verified separately before enabling the DNS lane.
