# Delta 5m OI impulse event study — BTC/ETH

Classification: descriptive event study only; not a strategy or executable backtest.

## Main specification
- Absolute 5m OI close-to-close change >=5%; 60-minute cooldown.
- Event timestamp is candle open + 5m (close availability).
- Outcomes: future traded-price and OI changes at 5m/15m/1h/4h; gaps are never filled.
- Matched controls: same split/direction/regime and training-only absolute-return decile; nearest within +/-24h.

## Data quality
- **BTC:** OI5m 210,374; traded price5m 210,384; OI1h 17,530; quarantined non-positive OI5m rows 2; 5m/1h OI match 17510/17526 common hours (99.909%); gaps OI5m 4, price5m 0, OI1h 2.
- **ETH:** OI5m 210,381; traded price5m 210,384; OI1h 17,530; quarantined non-positive OI5m rows 2; 5m/1h OI match 17505/17528 common hours (99.869%); gaps OI5m 3, price5m 0, OI1h 2.

## Event summaries
- BTC train abs-OI>=2.0%: 6151 events; mean 1h forward price 0.004535267839341787; 1h continuation hit 48.737990555284156%; mean 1h OI change 0.8856573648154495%.
- BTC validation abs-OI>=2.0%: 937 events; mean 1h forward price 0.009786415356017; 1h continuation hit 44.930629669156886%; mean 1h OI change 1.0876411918465807%.
- BTC oos abs-OI>=2.0%: 798 events; mean 1h forward price 0.007012997508006195; 1h continuation hit 44.165621079046424%; mean 1h OI change 0.9909639246270014%.
- BTC train abs-OI>=5.0%: 2385 events; mean 1h forward price 0.004145010934701606; 1h continuation hit 46.42857142857143%; mean 1h OI change 1.7236864877639138%.
- BTC validation abs-OI>=5.0%: 279 events; mean 1h forward price 0.0007009796435016411; 1h continuation hit 43.36917562724014%; mean 1h OI change 1.9238851326286321%.
- BTC oos abs-OI>=5.0%: 203 events; mean 1h forward price 0.04569381844834355; 1h continuation hit 52.70935960591133%; mean 1h OI change 2.1649082193855884%.
- ETH train abs-OI>=2.0%: 6977 events; mean 1h forward price -0.005373418958808638; 1h continuation hit 47.907378110168274%; mean 1h OI change 0.7698360246205405%.
- ETH validation abs-OI>=2.0%: 773 events; mean 1h forward price 0.003890083349011146; 1h continuation hit 46.373056994818654%; mean 1h OI change 0.8933783718197764%.
- ETH oos abs-OI>=2.0%: 734 events; mean 1h forward price 0.008130582119432074; 1h continuation hit 43.519781718963166%; mean 1h OI change 1.1286235598961978%.
- ETH train abs-OI>=5.0%: 2649 events; mean 1h forward price 0.01282724309099682; 1h continuation hit 47.314674735249625%; mean 1h OI change 1.8654686660193962%.
- ETH validation abs-OI>=5.0%: 196 events; mean 1h forward price -0.0036834443959970022; 1h continuation hit 42.78350515463917%; mean 1h OI change 2.433838923612589%.
- ETH oos abs-OI>=5.0%: 210 events; mean 1h forward price 0.05165499047044943; 1h continuation hit 42.38095238095238%; mean 1h OI change 2.6237775259418004%.

## Matched controls and cross-venue
{
  "BTC_matched_control": {
    "matched_pairs": 2753,
    "matching": "same split, same 5m price direction, same prior-24h regime, same training-defined absolute-return decile; nearest within +/-24h; controls without replacement",
    "mean_event_minus_control_15m_pct": 0.01151792430740077,
    "event_beats_control_15m_fraction_pct": 51.18053033054849,
    "mean_event_minus_control_1h_pct": 0.002067912405102054,
    "event_beats_control_1h_fraction_pct": 50.708318198329096,
    "mean_event_minus_control_4h_pct": 0.0016528665432962413,
    "event_beats_control_4h_fraction_pct": 50.52669814747548
  },
  "BTC_cross_venue": {
    "status": "unavailable",
    "error": "HTTPError: 451 Client Error:  for url: https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&startTime=1792684800000&endTime=1794481200000&limit=500"
  },
  "ETH_matched_control": {
    "matched_pairs": 2965,
    "matching": "same split, same 5m price direction, same prior-24h regime, same training-defined absolute-return decile; nearest within +/-24h; controls without replacement",
    "mean_event_minus_control_15m_pct": 0.016664437084314,
    "event_beats_control_15m_fraction_pct": 51.36593591905565,
    "mean_event_minus_control_1h_pct": 0.02074666482446683,
    "event_beats_control_1h_fraction_pct": 51.70320404721753,
    "mean_event_minus_control_4h_pct": 0.0348246203302527,
    "event_beats_control_4h_fraction_pct": 52.54637436762226
  },
  "ETH_cross_venue": {
    "status": "unavailable",
    "error": "HTTPError: 451 Client Error:  for url: https://fapi.binance.com/futures/data/openInterestHist?symbol=ETHUSDT&period=1h&startTime=1792684800000&endTime=1794481200000&limit=500"
  }
}

## Limitations
- Binance USD-M OI statistics are limited to the latest month in official docs.
- Venue OI series are not interchangeable; cross-venue results are context, not ground truth.
- No net R, win rate, PF, trading drawdown or losing streak: no trade rules were tested.
- No funding cashflows or transaction costs are applied.
