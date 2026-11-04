"""Delta Exchange instruments and post-analysis validation thresholds."""

SYMBOLS = {
    "BTC": {"delta_symbol": "BTCUSD", "kind": "crypto", "dp": 1},
    "ETH": {"delta_symbol": "ETHUSD", "kind": "crypto", "dp": 2},
    "XAU": {"delta_symbol": "XAUTUSD", "kind": "gold", "dp": 2},
}

# Mechanical post-analysis safety checks only. These do not identify supply/demand or create entries.
MIN_AI_CONFIDENCE = 75
MIN_AI_RR = 2.0
MAX_MARKET_ENTRY_DEVIATION_PCT = 0.35
TRADE_MAX_HOURS = 48

# Rolling OHLCV storage limits live in data.py. This is an initial cache-backed store, not a durable database.
