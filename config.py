"""All tunable settings. Visual SMC zones are inferred by the vision model, not generated here."""

SYMBOLS = {
    "BTC": {"yf": "BTC-USD", "kind": "crypto", "dp": 1},
    "ETH": {"yf": "ETH-USD", "kind": "crypto", "dp": 2},
    # GC=F is COMEX gold futures, not spot XAUUSD; the source is clearly labelled in the chart.
    "XAU": {"yf": "GC=F", "kind": "gold", "dp": 2},
}

# Mechanical post-analysis safety checks only. These do not identify supply/demand or create entries.
MIN_AI_CONFIDENCE = 75
MIN_AI_RR = 2.0
MAX_MARKET_ENTRY_DEVIATION_PCT = 0.35
TRADE_MAX_HOURS = 48

# Rolling OHLCV storage limits live in data.py. This is an initial cache-backed store, not a durable database.
