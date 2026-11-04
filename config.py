"""All tunable settings in one place. Defaults are starting points, not calibrated values."""

SYMBOLS = {
    "BTC": {"yf": "BTC-USD", "kind": "crypto", "okx": "BTC-USDT-SWAP", "news_q": "bitcoin", "dp": 1},
    "ETH": {"yf": "ETH-USD", "kind": "crypto", "okx": "ETH-USDT-SWAP", "news_q": "ethereum", "dp": 2},
    # GC=F is COMEX gold futures (small basis vs spot XAUUSD). Swap in your own spot feed if you have one.
    "XAU": {"yf": "GC=F", "kind": "gold", "okx": None, "news_q": "gold price", "dp": 2},
}

# Market structure: ATR zigzag on 1h candles. A swing tip only counts once price has moved this many ATRs
# away from it, so small wiggles never create zones.
ATR_LEN = 14
ZZ_ATR = 2.0
ZONE_MAX_AGE_BARS = 336    # tips older than this many 1h bars (14 days) are ignored; a zone stays valid until it breaks
ZONE_MAX_WIDTH_ATR = 2.0   # skip very wide tip candles (bad R:R)

# Impulse must leave the tip with a fair value gap (3-candle gap) starting within this many candles of the tip
FVG_MAX_OFFSET = 3
FVG_MIN_ATR = 0.1

# Role reversal: a body close through a zone flips it; the flip needs this much follow-through (in ATR)
FLIP_MIN_ATR = 1.5
IMPULSE_BARS = 3           # candles after the break used to measure follow-through

# Retests: a zone stays tradable after it is touched. Reaction after each retest feeds the score.
REACT_BARS = 6             # 1h candles after a retest used to measure how far price reacted
REARM_ATR = 1.5            # after a watch closes, price must move this far from the zone before the same zone can alert again

# Setup building
WATCH_DIST_ATR = 1.0       # price must be within this many ATRs of the zone edge
SL_BUFFER_ATR = 0.25
MIN_RR_WATCH = 2.5
MIN_RR_TRIGGER = 2.0

# Alert lifecycle
WATCH_MIN_SCORE = 60
WATCH_EXPIRY_HOURS = 24
TRADE_MAX_HOURS = 48       # close still-open paper signals at this horizon
MAX_ACTIVE_PER_SYMBOL = 1

# News / calendar
BLACKOUT_BEFORE_MIN = 60   # no new WATCH / TRIGGER this long before a high-impact USD event
BLACKOUT_AFTER_MIN = 30
NEWS_LOOKBACK_HOURS = 12
FUNDING_CROWDED = 0.0005   # 0.05% per funding interval

# Buy at support, sell at resistance regardless of bias: there is no trend gate.
KRONOS_HARD_FILTER = True  # when a Kronos bias exists for the symbol it must match the trade direction
                           # (flat or opposite = skip). No bias file = filter not applied, alert says so.
