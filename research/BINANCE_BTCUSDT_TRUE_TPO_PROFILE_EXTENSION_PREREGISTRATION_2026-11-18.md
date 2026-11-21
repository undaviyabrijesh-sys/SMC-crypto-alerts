# BTCUSDT September 2026 true TPO profile extension — frozen specification

Date: 2026-11-18 UTC  
Parent study: `BINANCE_BTCUSDT_TRUE_FOOTPRINT_FEATURE_STUDY_PREREGISTRATION_2026-11-18.md`  
Status: descriptive profile reconstruction only; no strategy parameter search.

## Definitions
- Use exact trade prices from the verified September USD-M BTCUSDT aggTrades archive (0.1 USDT tick).
- A TPO bracket is one UTC 30-minute interval, aligned to 00:00 UTC: bracket_ms = floor(transact_time_ms / 1,800,000) * 1,800,000.
- A price tick receives one TPO for a bracket if at least one aggTrade occurred at that exact price during that bracket. Multiple prints and multiple 5m bars in the same bracket count once.
- Daily TPO count at a price is the number of distinct 30-minute brackets during that UTC day in which that exact price traded.
- Daily volume profile at a price sums exact aggTrade base quantity across the UTC day; keep taker-buy and taker-sell quantities separate and compute delta = buy - sell.
- Daily volume POC is the price with maximum total volume; ties choose the lower price. Daily TPO POC is the price with maximum TPO count; ties choose the lower price.
- For each profile, construct a contiguous 70% value area by starting at POC and expanding one 0.1 USDT tick at a time toward the side with larger next-level profile value; ties choose the lower side. Empty price ticks count as zero while expanding.
- Validate that each day has the expected 48 UTC 30-minute brackets represented; any missing bracket must be reported, not imputed.
- Report daily profile rows, TPO bracket-price keys, total volume, total buy/sell/delta, volume POC/VAH/VAL, TPO POC/VAH/VAL, and value-area coverage. This is a descriptive reconstruction, not a predictive test.
- Do not claim the TPO profile is exchange-native official data; it is reconstructed from verified exchange aggTrades using the explicit 30-minute TPO definition above.
