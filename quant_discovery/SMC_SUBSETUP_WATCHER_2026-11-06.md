# DNS-anchored SMC sub-setup watcher — 2026-11-06

## Scope

The visual DNS mapper remains the sole source of demand/supply zones. This update expands the local watcher so multiple technical confirmations can be tested independently at those AI-authored bands. It does not create zones or allow standalone mid-range entries.

## Implemented local families

| Setup ID | Trigger summary |
|---|---|
| `DNS_LIQUIDITY_SWEEP_RECLAIM` | 5m sweep beyond the directional band, reclaim close through the far edge, then confirmation beyond the sweep candle extreme. |
| `DNS_DEMAND_REJECTION` / `DNS_SUPPLY_REJECTION` | Recent 5m touch of the mapped band followed by a directional close back through the band and the prior candle extreme. |
| `DNS_BOS_CHOCH_BULLISH` / `DNS_BOS_CHOCH_BEARISH` | Reaction from the mapped band, then a closed 5m break through the recent local swing high/low. The combined label denotes a structure-shift confirmation, not a claim to distinguish BOS from CHOCH with certainty. |
| `DNS_TREND_PULLBACK` | 15m EMA20/EMA50 trend alignment, a recent 5m pullback into the mapped band, and a 5m EMA20 reclaim with directional follow-through. |
| `DNS_FVG_RETRACE` | Three-candle 5m imbalance whose gap overlaps the AI-mapped band, followed by a mitigation and directional close back through the gap. |
| `DNS_RBS_RETEST` / `DNS_SBR_RETEST` | Price closes decisively through the AI-mapped band, a separate later candle retests and holds it, then a further 5m candle confirms the new role. |

These are separate candidates, not stacked labels. A candidate carries its own setup ID, rationale, invalidation text, zone ID/revision and event-candle timestamp.

## Common mechanical gates

- Only ACTIVE zones with quality >=3 are eligible.
- The candidate direction must match its visual zone: LONG at demand, SHORT at supply.
- The zone's own source timeframe is checked for invalidation.
- Candidate entry is the latest closed 5m close and must be within 0.35% of the mapped band.
- Target is the nearest eligible opposing AI-mapped DNS band; no standalone indicator-derived target is invented.
- Risk/reward must be at least 2R.
- Recent 5m bars must be chronologically ordered, unique and continuous for the pattern lookback. The 15m trend filter also requires a continuous 55-bar context. Gaps are not filled; patterns are skipped when the required interval is discontinuous.
- The worker ranks candidates by zone quality and R multiple, debates at most one unseen candidate per symbol per five-minute cycle, and allows no more than one open or pending paper position per symbol.
- When the optional debate is enabled, Bull Researcher, Bear Researcher and Chief Trader run only after a candidate is detected. Only explicit Chief Trader APPROVE passes; API error, malformed response, REJECT, NO_TRADE and cooldown fail closed.

## Tests

`test_dns_engine.py` includes synthetic OHLCV fixtures for the legacy sweep/reclaim path, separate rejection/BOS/CHOCH/trend-pullback candidates, bullish FVG retrace, RBS, SBR, zone-proximity rejection and worker approval/veto integration. These tests check implementation contracts, not market profitability.

## Known limitations

- The setup families are simple deterministic OHLCV approximations. A wick is not proof of resting liquidity; FVG/structure labels are not discretionary chart truth.
- BOS and CHOCH are grouped as one local confirmation family rather than separately inferred market-structure states.
- Visual DNS map accuracy, API quota, actual webhook delivery and a persistent deployment have not been proven by offline CI.
- The current local watcher does not yet run a full visual candidate-comparison prompt on every candle. That would defeat the credit-saving map-plus-local-watcher architecture. The optional Bull/Bear/Chief debate compares a candidate only when a local DNS trigger appears.
- No strategy is promoted to live or production trading. OOS, walk-forward, parameter-neighbourhood and stressed-cost validation remain mandatory.

## Operational status

This work lives on `ai-quant-rebuild` under draft PR #1. It does not modify `main`, enable a schedule, deploy infrastructure, change secrets or submit exchange orders. `WORKER_MODE=quant` remains the default; the visual DNS lane requires explicit `WORKER_MODE=dns` configuration.
