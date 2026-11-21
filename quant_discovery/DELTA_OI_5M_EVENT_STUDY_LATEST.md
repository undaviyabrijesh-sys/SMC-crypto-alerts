# Delta 5m OI impulse event study — BTC/ETH

Classification: descriptive event study only; not a strategy or executable backtest.

## Main specification
- Absolute 5m OI close-to-close change >=5%; 60-minute cooldown.
- Event timestamp is candle open + 5m (close availability).
- Outcomes: future traded-price and OI changes at 5m/15m/1h/4h; gaps are never filled.
- Matched controls: same split/direction/regime and training-only absolute-return decile; nearest within +/-24h; controls are at least 4h05 from every main event and from other selected controls; post-match invariants are asserted.

## Data quality
- **BTC:** OI5m 210,382; traded price5m 210,384; OI1h 17,530; quarantined non-positive OI5m rows 2; 5m/1h OI match 17511/17529 common hours (99.897%); gaps OI5m 2, price5m 0, OI1h 2.
- **ETH:** OI5m 210,382; traded price5m 210,384; OI1h 17,530; quarantined non-positive OI5m rows 2; 5m/1h OI match 17506/17529 common hours (99.869%); gaps OI5m 2, price5m 0, OI1h 2.

## Event summaries
- BTC train abs-OI>=2.0%: 6150 events; mean 1h forward price 0.004189280255337594; 1h continuation hit 48.74633669814393%; mean 1h OI change 0.8857041535847939%.
- BTC validation abs-OI>=2.0%: 933 events; mean 1h forward price 0.009857454753352804; 1h continuation hit 45.01607717041801%; mean 1h OI change 1.1198633507513807%.
- BTC oos abs-OI>=2.0%: 802 events; mean 1h forward price 0.002217238306023641; 1h continuation hit 44.06991260923846%; mean 1h OI change 0.9776556106083868%.
- BTC train abs-OI>=5.0%: 2385 events; mean 1h forward price 0.0028707594121467127; 1h continuation hit 46.51553316540722%; mean 1h OI change 1.7037433726298705%.
- BTC validation abs-OI>=5.0%: 276 events; mean 1h forward price 0.0005518095734054605; 1h continuation hit 43.11594202898551%; mean 1h OI change 2.093847047993386%.
- BTC oos abs-OI>=5.0%: 204 events; mean 1h forward price 0.040444475494120044; 1h continuation hit 52.450980392156865%; mean 1h OI change 2.1247121548630807%.
- ETH train abs-OI>=2.0%: 6978 events; mean 1h forward price -0.0053740162157145; 1h continuation hit 47.86484543493889%; mean 1h OI change 0.7715833145097816%.
- ETH validation abs-OI>=2.0%: 770 events; mean 1h forward price 0.002340376397017612; 1h continuation hit 46.42392717815345%; mean 1h OI change 0.9149294668452725%.
- ETH oos abs-OI>=2.0%: 738 events; mean 1h forward price 0.0006910127771233752; 1h continuation hit 43.69063772048847%; mean 1h OI change 1.114889126104491%.
- ETH train abs-OI>=5.0%: 2651 events; mean 1h forward price 0.012874029802506709; 1h continuation hit 47.298828862863616%; mean 1h OI change 1.8672332328289665%.
- ETH validation abs-OI>=5.0%: 195 events; mean 1h forward price 0.0004302739696879981; 1h continuation hit 43.005181347150256%; mean 1h OI change 2.5377824679319914%.
- ETH oos abs-OI>=5.0%: 213 events; mean 1h forward price 0.04111412236641021; 1h continuation hit 43.1924882629108%; mean 1h OI change 2.6049507386967887%.

## Matched controls and cross-venue
{
  "BTC_matched_control": {
    "matched_pairs": 685,
    "matching": "same split, same 5m price direction, same prior-24h regime, same training-defined absolute-return decile; nearest within +/-24h; controls at least 4h05 from every main-event timestamp; selected control windows at least 4h05 apart; no control reuse; post-match non-overlap and split-safety invariants asserted",
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
        "ci_low_bps": -8.430059117470101,
        "ci_high_bps": 10.418554220429199,
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
        "ci_low_bps": -8.393221118448345,
        "ci_high_bps": 28.70830446169735,
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
        "ci_low_bps": -17.242632235768337,
        "ci_high_bps": 48.2695829280483,
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
        "ci_low_bps": -2.470103536041816,
        "ci_high_bps": 4.677963082224673,
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
        "ci_low_bps": -9.733856113733802,
        "ci_high_bps": 2.1006010217426185,
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
        "ci_low_bps": -28.55480486155864,
        "ci_high_bps": -5.643569937430045,
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
        "ci_low_bps": -7.1262196839083,
        "ci_high_bps": 10.015355900486195,
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
        "ci_low_bps": -11.719435017437196,
        "ci_high_bps": 14.66410064560466,
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
        "ci_low_bps": -26.772174800442244,
        "ci_high_bps": 15.251903934979696,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      }
    ],
    "bootstrap_note": "UTC event-day cluster bootstrap, 5,000 replicates; descriptive intervals only, not adjusted across the threshold/cooldown grid."
  },
  "BTC_cross_venue": {
    "status": "unavailable",
    "error": "HTTPError: 451 Client Error:  for url: https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&startTime=1792710000000&endTime=1794506400000&limit=500"
  },
  "ETH_matched_control": {
    "matched_pairs": 627,
    "matching": "same split, same 5m price direction, same prior-24h regime, same training-defined absolute-return decile; nearest within +/-24h; controls at least 4h05 from every main-event timestamp; selected control windows at least 4h05 apart; no control reuse; post-match non-overlap and split-safety invariants asserted",
    "minimum_forward_window_separation_minutes": 245,
    "mean_event_minus_control_15m_pct": -0.003644765343347485,
    "event_beats_control_15m_fraction_pct": 49.760765550239235,
    "mean_event_minus_control_1h_pct": -0.04589936342337302,
    "event_beats_control_1h_fraction_pct": 48.963317384370015,
    "mean_event_minus_control_4h_pct": -0.0656392364863764,
    "event_beats_control_4h_fraction_pct": 49.601275917065394,
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
        "ci_low_bps": -19.593462221106105,
        "ci_high_bps": 6.962351293280921,
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
        "ci_low_bps": -35.37462591965794,
        "ci_high_bps": 12.61073655001727,
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
        "ci_low_bps": -63.40377842195238,
        "ci_high_bps": 22.010068127015597,
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
        "ci_low_bps": -4.854416069001929,
        "ci_high_bps": 7.4227466630955234,
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
        "ci_low_bps": -16.09436737345832,
        "ci_high_bps": 5.228454948944729,
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
        "ci_low_bps": -30.310050188793937,
        "ci_high_bps": 8.116662175017881,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "validation",
        "horizon": "15m",
        "pairs": 94,
        "event_days": 64,
        "mean_lift_bps": -1.1665853333510068,
        "median_lift_bps": 3.017188511419966,
        "event_beats_control_pct": 51.06382978723404,
        "ci_low_bps": -11.270500836794529,
        "ci_high_bps": 8.837079687407877,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "validation",
        "horizon": "1h",
        "pairs": 94,
        "event_days": 64,
        "mean_lift_bps": 6.608082376319432,
        "median_lift_bps": 0.7399872784674688,
        "event_beats_control_pct": 51.06382978723404,
        "ci_low_bps": -9.798878875131017,
        "ci_high_bps": 23.900605261295276,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      },
      {
        "asset": "ETH",
        "split": "validation",
        "horizon": "4h",
        "pairs": 94,
        "event_days": 64,
        "mean_lift_bps": 30.596703223899723,
        "median_lift_bps": 4.97725751319511,
        "event_beats_control_pct": 54.25531914893617,
        "ci_low_bps": -4.290259595038356,
        "ci_high_bps": 67.94703539679658,
        "bootstrap_replicates": 5000,
        "cluster": "UTC event day"
      }
    ],
    "bootstrap_note": "UTC event-day cluster bootstrap, 5,000 replicates; descriptive intervals only, not adjusted across the threshold/cooldown grid."
  },
  "ETH_cross_venue": {
    "status": "unavailable",
    "error": "HTTPError: 451 Client Error:  for url: https://fapi.binance.com/futures/data/openInterestHist?symbol=ETHUSDT&period=1h&startTime=1792710000000&endTime=1794506400000&limit=500"
  }
}

## Limitations
- Binance USD-M OI statistics are limited to the latest month in official docs.
- Venue OI series are not interchangeable; cross-venue results are context, not ground truth.
- No net R, win rate, PF, trading drawdown or losing streak: no trade rules were tested.
- No funding cashflows or transaction costs are applied.
