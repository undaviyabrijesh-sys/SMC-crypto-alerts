# ETHUSDT Supertrend — actual funding cashflow audit

- Type: accounting correction only; no parameter optimization and no strategy promotion.
- Parent workflow: 44693535437; parent candle SHA-256: 9f6379bb53003daa04779960095af65065127aa89f9ed46f4016d8cd28c50f59.
- Funding records: 1,483; SHA-256: 23d7d5796e5d5691ff5ee93e8280f18d15c5235bbb7b50533be545c41abb53d6.
- Funding event range: 2025-03-08T00:00:00+00:00 to 2026-07-15T00:00:00.005000+00:00.
- Observed rounded interval histogram (hours): {'8': 1482}.
- Funding mark prices present and positive: yes; duplicate timestamps: no.
- Coverage check: {'first_trade_entry_utc': '2025-03-08T12:30:00+00:00', 'last_trade_exit_close_utc': '2026-04-30T13:30:00+00:00', 'first_funding_event_utc': '2025-03-08T00:00:00+00:00', 'last_funding_event_utc': '2026-07-15T00:00:00.005000+00:00', 'coverage_start_pass': True, 'coverage_end_pass': True}.
- Raw Supertrend flips replayed without fixed-grid exclusion: 1,043.
- Strategy: HL2 Supertrend, Wilder ATR(10) x3, next 15m open, signal-bar line stop, fixed 2R, both sides, all UTC hours, one position, 16-bar maximum hold.
- Funding: actual Binance fundingTime, fundingRate, and associated markPrice; positive rates mean longs pay and shorts receive.
- Boundary handling: events within 1 second of entry are ambiguous; events strictly before TP/SL exit-bar open are definite; events inside TP/SL exit candle are ambiguous; TIME exits remain open through the final candle close.
- Net lower/upper bounds include adverse/favorable ambiguous funding respectively. Transaction cost is assumed 12 bps round trip; 6/20 bps sensitivity is also saved.
- R is normalized by initial stop risk, not account return. OHLC stop-first execution and adverse stop-gap assumptions are inherited from the parent simulator.
- The final 15% holdout is retired and was not evaluated.

## Results at 12 bps

### all_raw_signals/development
- Lower bound: {'trades': 658, 'win_rate_pct': 43.01, 'profit_factor': 0.8824, 'net_R': -26.7718, 'avg_R': -0.04069, 'max_drawdown_R': -36.3054, 'max_losing_streak': 12, 'positive_months': 5, 'active_months': 12, 'positive_month_fraction': 0.4167, 'TP': 48, 'SL': 125, 'TIME': 485}
- Upper bound: {'trades': 658, 'win_rate_pct': 43.01, 'profit_factor': 0.883, 'net_R': -26.6442, 'avg_R': -0.04049, 'max_drawdown_R': -36.2029, 'max_losing_streak': 12, 'positive_months': 5, 'active_months': 12, 'positive_month_fraction': 0.4167, 'TP': 48, 'SL': 125, 'TIME': 485}
- Definite/ambiguous settlements: 269 / 37
- Funding R definite/lower/upper: -0.100756 / -0.168810 / -0.041212
- Definite funding paid/received per ETH: 23.64626904 / 18.54805593

### all_raw_signals/validation
- Lower bound: {'trades': 148, 'win_rate_pct': 36.49, 'profit_factor': 0.7925, 'net_R': -11.9967, 'avg_R': -0.08106, 'max_drawdown_R': -16.8476, 'max_losing_streak': 10, 'positive_months': 1, 'active_months': 3, 'positive_month_fraction': 0.3333, 'TP': 13, 'SL': 29, 'TIME': 106}
- Upper bound: {'trades': 148, 'win_rate_pct': 36.49, 'profit_factor': 0.7929, 'net_R': -11.9627, 'avg_R': -0.08083, 'max_drawdown_R': -16.8217, 'max_losing_streak': 10, 'positive_months': 1, 'active_months': 3, 'positive_month_fraction': 0.3333, 'TP': 13, 'SL': 29, 'TIME': 106}
- Definite/ambiguous settlements: 65 / 7
- Funding R definite/lower/upper: 0.052367 / 0.051161 / 0.085241
- Definite funding paid/received per ETH: 1.99613983 / 3.36170136

### parent_default_grid_subset/development
- Lower bound: {'trades': 332, 'win_rate_pct': 43.07, 'profit_factor': 0.7884, 'net_R': -24.2695, 'avg_R': -0.0731, 'max_drawdown_R': -28.599, 'max_losing_streak': 13, 'positive_months': 2, 'active_months': 12, 'positive_month_fraction': 0.1667, 'TP': 22, 'SL': 58, 'TIME': 252}
- Upper bound: {'trades': 332, 'win_rate_pct': 43.07, 'profit_factor': 0.7888, 'net_R': -24.2146, 'avg_R': -0.07294, 'max_drawdown_R': -28.5494, 'max_losing_streak': 13, 'positive_months': 2, 'active_months': 12, 'positive_month_fraction': 0.1667, 'TP': 22, 'SL': 58, 'TIME': 252}
- Definite/ambiguous settlements: 0 / 16
- Funding R definite/lower/upper: 0.000000 / -0.023025 / 0.031915
- Definite funding paid/received per ETH: 0.00000000 / 0.00000000

### parent_default_grid_subset/validation
- Lower bound: {'trades': 75, 'win_rate_pct': 37.33, 'profit_factor': 0.7479, 'net_R': -8.2598, 'avg_R': -0.11013, 'max_drawdown_R': -18.4183, 'max_losing_streak': 11, 'positive_months': 1, 'active_months': 3, 'positive_month_fraction': 0.3333, 'TP': 6, 'SL': 18, 'TIME': 51}
- Upper bound: {'trades': 75, 'win_rate_pct': 37.33, 'profit_factor': 0.7485, 'net_R': -8.2308, 'avg_R': -0.10974, 'max_drawdown_R': -18.3936, 'max_losing_streak': 11, 'positive_months': 1, 'active_months': 3, 'positive_month_fraction': 0.3333, 'TP': 6, 'SL': 18, 'TIME': 51}
- Definite/ambiguous settlements: 0 / 4
- Funding R definite/lower/upper: 0.000000 / 0.000000 / 0.028982
- Definite funding paid/received per ETH: 0.00000000 / 0.00000000

## Limitations

- The funding history endpoint provides the mark price associated with each funding charge; the audit uses one ETH unit and converts quote cashflow into initial-risk R.
- Actual user fee tier, bid/ask spread, variable slippage, market impact, and account quantity are not available.
- TP/SL intrabar exit times are unknown from 15m OHLC, so funding events in the exit candle are bounded rather than assigned a false point estimate.
- The parent final 15% holdout was contaminated by prior local access and remains retired; no OOS claim is made.
- This is not a strategy validation run. The frozen Supertrend baseline was already negative in development and validation before actual funding accounting.
