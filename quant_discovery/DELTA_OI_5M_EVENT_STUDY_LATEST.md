# Delta 5m OI impulse event study — BTC/ETH

Classification: descriptive event study only; not a strategy or executable backtest.

## Main specification
- Absolute 5m OI close-to-close change >=5%; 60-minute cooldown.
- Event timestamp is candle open + 5m (close availability).
- Outcomes: future traded-price and OI changes at 5m/15m/1h/4h; gaps are never filled.
- Matched controls: same split/direction/regime and training-only absolute-return decile; nearest within +/-24h.

## Data quality
- **BTC:** OI5m 210,382; traded price5m 210,384; OI1h 17,530; quarantined non-positive OI5m rows 2; 5m/1h OI match 17511/17529 common hours (99.897%); gaps OI5m 2, price5m 0, OI1h 2.
- **ETH:** OI5m 210,382; traded price5m 210,384; OI1h 17,530; quarantined non-positive OI5m rows 2; 5m/1h OI match 17506/17529 common hours (99.869%); gaps OI5m 2, price5m 0, OI1h 2.

## Event summaries
- BTC train abs-OI>=2.0%: 6150 events; mean 1h forward price 0.004374133592130499; 1h continuation hit 48.762618039726476%; mean 1h OI change 0.8831542082263062%.
- BTC validation abs-OI>=2.0%: 935 events; mean 1h forward price 0.009845136344170648; 1h continuation hit 44.81283422459893%; mean 1h OI change 1.0961971188649107%.
- BTC oos abs-OI>=2.0%: 799 events; mean 1h forward price 0.004622771146568663; 1h continuation hit 44.11027568922306%; mean 1h OI change 0.9890838407131859%.
- BTC train abs-OI>=5.0%: 2386 events; mean 1h forward price 0.0032727610364170633; 1h continuation hit 46.49601342845153%; mean 1h OI change 1.7248665837751609%.
- BTC validation abs-OI>=5.0%: 276 events; mean 1h forward price 0.0015602476853580618; 1h continuation hit 42.7536231884058%; mean 1h OI change 2.0594278808700364%.
- BTC oos abs-OI>=5.0%: 203 events; mean 1h forward price 0.03820110878672358; 1h continuation hit 52.70935960591133%; mean 1h OI change 2.156392176895959%.
- ETH train abs-OI>=2.0%: 6979 events; mean 1h forward price -0.005380045143015633; 1h continuation hit 47.901092581943644%; mean 1h OI change 0.7712573050859718%.
- ETH validation abs-OI>=2.0%: 772 events; mean 1h forward price 0.0031597261348745454; 1h continuation hit 46.43320363164721%; mean 1h OI change 0.8886997515044874%.
- ETH oos abs-OI>=2.0%: 736 events; mean 1h forward price 0.004103234112866732; 1h continuation hit 43.673469387755105%; mean 1h OI change 1.1131683408109132%.
- ETH train abs-OI>=5.0%: 2650 events; mean 1h forward price 0.012826275824882216; 1h continuation hit 47.27891156462585%; mean 1h OI change 1.8666770220822388%.
- ETH validation abs-OI>=5.0%: 196 events; mean 1h forward price -0.0036834443959970022; 1h continuation hit 42.78350515463917%; mean 1h OI change 2.433838923612589%.
- ETH oos abs-OI>=5.0%: 211 events; mean 1h forward price 0.04038915732095048; 1h continuation hit 43.127962085308056%; mean 1h OI change 2.6122480356662767%.

## Matched controls and cross-venue
{
  "BTC_matched_control": {
    "matched_pairs": 685,
    "matching": "same split, same 5m price direction, same prior-24h regime, same training-defined absolute-return decile; nearest within +/-24h; controls at least 4h05 from every main-event timestamp; selected control windows at least 4h05 apart; no control reuse",
    "minimum_forward_window_separation_minutes": 245,
    "mean_event_minus_control_15m_pct": 0.012155556283276622,
    "event_beats_control_15m_fraction_pct": 52.846715328467155,
    "mean_event_minus_control_1h_pct": -0.010042694743053696,
    "event_beats_control_1h_fraction_pct": 47.88321167883212,
    "mean_event_minus_control_4h_pct": -0.1101885667674939,
    "event_beats_control_4h_fraction_pct": 46.56934306569343,
    "cluster_bootstrap": [
      {
        "asset": "BTC",
        "split": "oos",
        "horizon": "15m",
        "pairs": 89,
        "event_days": 64,
        "mean_lift_bps": 1.078000664273567,
        "median_lift_bps": 0.07336946600156047,
        "event_beats_control_pct": 51.68539325842697,
        "ci_low_bps": -8.812794284640523,
        "ci_high_bps": 10.555386072703849,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "BTC",
        "split": "oos",
        "horizon": "1h",
        "pairs": 89,
        "event_days": 64,
        "mean_lift_bps": 10.575602155942509,
        "median_lift_bps": 0.9380154909077731,
        "event_beats_control_pct": 50.56179775280899,
        "ci_low_bps": -7.893834255389887,
        "ci_high_bps": 29.163238723913615,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "BTC",
        "split": "oos",
        "horizon": "4h",
        "pairs": 89,
        "event_days": 64,
        "mean_lift_bps": 14.100363816597335,
        "median_lift_bps": -1.010636439566781,
        "event_beats_control_pct": 49.43820224719101,
        "ci_low_bps": -16.932114005893194,
        "ci_high_bps": 49.542165053172894,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "BTC",
        "split": "train",
        "horizon": "15m",
        "pairs": 476,
        "event_days": 324,
        "mean_lift_bps": 1.0987369753101435,
        "median_lift_bps": 0.6496105378317463,
        "event_beats_control_pct": 51.05042016806722,
        "ci_low_bps": -2.4722358635751727,
        "ci_high_bps": 4.6460050882127835,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "BTC",
        "split": "train",
        "horizon": "1h",
        "pairs": 476,
        "event_days": 324,
        "mean_lift_bps": -3.8437755637473154,
        "median_lift_bps": -4.35901076281664,
        "event_beats_control_pct": 46.42857142857143,
        "ci_low_bps": -9.624931686954566,
        "ci_high_bps": 2.1577702720528045,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "BTC",
        "split": "train",
        "horizon": "4h",
        "pairs": 476,
        "event_days": 324,
        "mean_lift_bps": -17.045150109475564,
        "median_lift_bps": -9.026523351967075,
        "event_beats_control_pct": 45.79831932773109,
        "ci_low_bps": -28.35008889312008,
        "ci_high_bps": -5.72554901051544,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "BTC",
        "split": "validation",
        "horizon": "15m",
        "pairs": 120,
        "event_days": 77,
        "mean_lift_bps": 1.7809562169706084,
        "median_lift_bps": 4.474365548310377,
        "event_beats_control_pct": 60.83333333333333,
        "ci_low_bps": -6.969301529806722,
        "ci_high_bps": 10.08262544564327,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "BTC",
        "split": "validation",
        "horizon": "1h",
        "pairs": 120,
        "event_days": 77,
        "mean_lift_bps": 1.6706998880471706,
        "median_lift_bps": 2.4223253093397235,
        "event_beats_control_pct": 51.66666666666667,
        "ci_low_bps": -11.265307943948685,
        "ci_high_bps": 15.213384409673928,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "BTC",
        "split": "validation",
        "horizon": "4h",
        "pairs": 120,
        "event_days": 77,
        "mean_lift_bps": -5.744647926167726,
        "median_lift_bps": -11.174660410621652,
        "event_beats_control_pct": 47.5,
        "ci_low_bps": -25.85465726531524,
        "ci_high_bps": 15.581463672016207,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      }
    ],
    "bootstrap_note": "UTC event-day cluster bootstrap, 5,000 replicates; descriptive intervals only, not adjusted across the threshold/cooldown grid."
  },
  "BTC_cross_venue": {
    "status": "unavailable",
    "error": "HTTPError: 451 Client Error:  for url: https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&startTime=1792695600000&endTime=1794492000000&limit=500"
  },
  "ETH_matched_control": {
    "matched_pairs": 627,
    "matching": "same split, same 5m price direction, same prior-24h regime, same training-defined absolute-return decile; nearest within +/-24h; controls at least 4h05 from every main-event timestamp; selected control windows at least 4h05 apart; no control reuse",
    "minimum_forward_window_separation_minutes": 245,
    "mean_event_minus_control_15m_pct": -0.003871525393534209,
    "event_beats_control_15m_fraction_pct": 49.601275917065394,
    "mean_event_minus_control_1h_pct": -0.04664267011694411,
    "event_beats_control_1h_fraction_pct": 48.963317384370015,
    "mean_event_minus_control_4h_pct": -0.06860352498100594,
    "event_beats_control_4h_fraction_pct": 49.441786283891545,
    "cluster_bootstrap": [
      {
        "asset": "ETH",
        "split": "oos",
        "horizon": "15m",
        "pairs": 100,
        "event_days": 68,
        "mean_lift_bps": -5.896580221703018,
        "median_lift_bps": -0.9850666960786736,
        "event_beats_control_pct": 47.0,
        "ci_low_bps": -20.29088444135984,
        "ci_high_bps": 7.465797431686602,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "oos",
        "horizon": "1h",
        "pairs": 100,
        "event_days": 68,
        "mean_lift_bps": -11.953894831972235,
        "median_lift_bps": -8.499539128468125,
        "event_beats_control_pct": 48.0,
        "ci_low_bps": -36.279833719645346,
        "ci_high_bps": 12.453829239549608,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "oos",
        "horizon": "4h",
        "pairs": 100,
        "event_days": 68,
        "mean_lift_bps": -22.645326520449878,
        "median_lift_bps": -10.082710650224925,
        "event_beats_control_pct": 47.0,
        "ci_low_bps": -64.10582502526884,
        "ci_high_bps": 18.937339908211083,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "train",
        "horizon": "15m",
        "pairs": 433,
        "event_days": 298,
        "mean_lift_bps": 1.0872754191164178,
        "median_lift_bps": 0.19526539173808644,
        "event_beats_control_pct": 50.11547344110855,
        "ci_low_bps": -5.097516110839,
        "ci_high_bps": 7.229813403225892,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "train",
        "horizon": "1h",
        "pairs": 433,
        "event_days": 298,
        "mean_lift_bps": -5.320231747857486,
        "median_lift_bps": -2.175048854968775,
        "event_beats_control_pct": 48.72979214780601,
        "ci_low_bps": -15.804863755507444,
        "ci_high_bps": 5.459959135921759,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "train",
        "horizon": "4h",
        "pairs": 433,
        "event_days": 298,
        "mean_lift_bps": -10.917176856114057,
        "median_lift_bps": -2.017046001325795,
        "event_beats_control_pct": 49.19168591224018,
        "ci_low_bps": -28.97922199190471,
        "ci_high_bps": 7.908213036524031,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "validation",
        "horizon": "15m",
        "pairs": 94,
        "event_days": 65,
        "mean_lift_bps": -1.3178391115074704,
        "median_lift_bps": 0.9315601400439188,
        "event_beats_control_pct": 50.0,
        "ci_low_bps": -11.188565995071047,
        "ci_high_bps": 8.61598685821562,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "validation",
        "horizon": "1h",
        "pairs": 94,
        "event_days": 65,
        "mean_lift_bps": 6.1122809966714815,
        "median_lift_bps": 0.7399872784674688,
        "event_beats_control_pct": 51.06382978723404,
        "ci_low_bps": -10.229018884327722,
        "ci_high_bps": 23.081767699540155,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "validation",
        "horizon": "4h",
        "pairs": 94,
        "event_days": 65,
        "mean_lift_bps": 28.61945972801385,
        "median_lift_bps": 2.8532711221945783,
        "event_beats_control_pct": 53.191489361702125,
        "ci_low_bps": -4.855926391263911,
        "ci_high_bps": 65.51775175454951,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      }
    ],
    "bootstrap_note": "UTC event-day cluster bootstrap, 5,000 replicates; descriptive intervals only, not adjusted across the threshold/cooldown grid."
  },
  "ETH_cross_venue": {
    "status": "unavailable",
    "error": "HTTPError: 451 Client Error:  for url: https://fapi.binance.com/futures/data/openInterestHist?symbol=ETHUSDT&period=1h&startTime=1792695600000&endTime=1794492000000&limit=500"
  }
}

## Limitations
- Binance USD-M OI statistics are limited to the latest month in official docs.
- Venue OI series are not interchangeable; cross-venue results are context, not ground truth.
- No net R, win rate, PF, trading drawdown or losing streak: no trade rules were tested.
- No funding cashflows or transaction costs are applied.
