"use client";

import { useEffect, useState } from "react";

const navigation = [
  { label: "Overview", group: "Workspace", icon: "⌂" },
  { label: "Live Markets", group: "Workspace", icon: "◫" },
  { label: "AI Scanner", group: "Workspace", icon: "⌕" },
  { label: "Strategy Research", group: "Research", icon: "◈" },
  { label: "Backtesting", group: "Research", icon: "⌁" },
  { label: "Paper Trading", group: "Execution", icon: "⇄" },
  { label: "Portfolio", group: "Execution", icon: "▤" },
  { label: "Trade History", group: "Execution", icon: "◷" },
  { label: "AI Analyst", group: "Intelligence", icon: "✳" },
  { label: "Risk Management", group: "Intelligence", icon: "⛨" }
];

type MarketRecord = {
  symbol: string;
  instrument?: string;
  kind?: string;
  venue?: string;
  status: string;
  reason?: string | null;
  last_price?: number | null;
  last_volume?: number | null;
  last_closed_5m_candle_open?: string | null;
  age_minutes?: number | null;
  timeframes?: Record<string, { status: string; age_minutes?: number | null }>;
};

type HealthSnapshot = {
  status: string;
  api_version?: string;
  approved_strategy_count?: number;
  checks?: Record<string, string>;
  as_of?: string;
};

type MarketSnapshot = {
  status: string;
  as_of?: string;
  source?: string;
  markets?: MarketRecord[];
};

type ScannerCandidate = {
  strategy_id?: string | null;
  setup_type?: string | null;
  direction?: string | null;
  entry?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  rr?: number | null;
  quality_score?: number | null;
  score_type?: string | null;
  rationale?: string | null;
  invalidation?: string | null;
  target_basis?: string | null;
  timeframes_in_agreement?: string[];
};

type ScannerSymbol = {
  symbol: string;
  status?: string;
  timestamp?: string | null;
  latest_closed_5m_candle?: string | null;
  latest_closed_5m_price?: number | null;
  decision_status?: string | null;
  decision_reason?: string | null;
  selected_strategy?: string | null;
  research_preview_strategy?: string | null;
  candidates?: ScannerCandidate[];
  rejected_candidates?: Array<{ strategy_id?: string | null; reason?: string | null }>;
  has_open_position?: boolean | null;
};

type ScannerSnapshot = {
  status: string;
  reason?: string | null;
  as_of?: string;
  source?: string;
  malformed_lines_in_tail?: number;
  symbols?: ScannerSymbol[];
};

type PaperPosition = {
  signal_id?: string | null;
  sym?: string | null;
  dir?: string | null;
  entry?: number | null;
  sl?: number | null;
  tp?: number | null;
  rr?: number | null;
  setup_type?: string | null;
  strategy_id?: string | null;
  quality_score?: number | null;
  score_type?: string | null;
  triggered_at?: string | null;
  status?: string | null;
  entry_source?: string | null;
};

type PositionsSnapshot = {
  status: string;
  source?: string;
  as_of?: string;
  reason?: string | null;
  position_count?: number | null;
  pending_outcome_count?: number | null;
  positions?: PaperPosition[] | null;
};

type PaperTrade = {
  signal_id?: string | null;
  sym?: string | null;
  dir?: string | null;
  entry?: number | null;
  exit?: number | null;
  sl?: number | null;
  tp?: number | null;
  rr?: number | null;
  setup_type?: string | null;
  strategy_id?: string | null;
  triggered_at?: string | null;
  exit_time?: string | null;
  status?: string | null;
  gross_R?: number | null;
  gross_pnl_pct?: number | null;
  entry_source?: string | null;
};

type HistorySnapshot = {
  status: string;
  source?: string;
  reason?: string | null;
  trade_count?: number | null;
  retained_trade_limit?: number;
  trades?: PaperTrade[] | null;
};

type ResearchSnapshot = {
  status: string;
  source?: string;
  entry_count?: number;
  entries?: Array<{ title: string; summary: string }>;
};

type BacktestArtifact = {
  name: string;
  path: string;
  bytes: number;
  metadata?: Record<string, unknown>;
  metadata_status?: string;
  data_status?: string;
  columns?: string[];
  rows?: Array<Record<string, string>>;
};

type BacktestSnapshot = {
  status: string;
  source?: string;
  artifact_count?: number;
  artifacts?: BacktestArtifact[];
};

type RiskSnapshot = {
  status: string;
  as_of?: string;
  source?: string;
  account_equity?: number | null;
  account_exposure?: number | null;
  open_positions?: number | null;
  open_symbols?: string[];
  pending_outcomes?: number | null;
  realized_gross_r_retained_history?: number | null;
  max_drawdown_r_retained_history?: number | null;
  retained_history_trades?: number | null;
  circuit_breaker?: string | null;
  limitations?: string[];
};

type DashboardData = {
  loading: boolean;
  health: HealthSnapshot | null;
  markets: MarketSnapshot | null;
  scanner: ScannerSnapshot | null;
  positions: PositionsSnapshot | null;
  history: HistorySnapshot | null;
  research: ResearchSnapshot | null;
  backtests: BacktestSnapshot | null;
  risk: RiskSnapshot | null;
};

async function fetchApi<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`/api/quant/${path}`, { cache: "no-store" });
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function marketTone(status?: string): "muted" | "green" | "amber" {
  if (status === "live" || status === "available") return "green";
  if (status === "stale") return "amber";
  return "muted";
}

function marketLabel(status?: string) {
  if (status === "live") return "CACHE FRESH";
  if (status === "stale") return "STALE";
  return "UNAVAILABLE";
}

function formatPrice(market: MarketRecord) {
  if (market.last_price == null || !Number.isFinite(market.last_price)) return "—";
  const digits = market.symbol === "BTC" ? 1 : 2;
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format(market.last_price);
}

function formatAge(age?: number | null) {
  return age == null || !Number.isFinite(age) ? "age unavailable" : `${Math.max(0, Math.round(age))}m since close`;
}

function formatLevel(value?: number | null, digits = 2) {
  return value == null || !Number.isFinite(value)
    ? "—"
    : value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function formatScannerTimestamp(value?: string | null) {
  if (!value) return "Timestamp unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatArtifactBytes(value?: number) {
  if (value == null || !Number.isFinite(value) || value < 0) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

function formatArtifactValue(value: unknown) {
  if (value == null) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isFinite(value) ? value.toLocaleString("en-US") : "—";
  if (typeof value === "string") return value || "—";
  try {
    return JSON.stringify(value);
  } catch {
    return "—";
  }
}

function scannerDecisionTone(status?: string | null): "muted" | "green" | "amber" {
  if (status === "SELECTED") return "green";
  if (status === "RESEARCH_ONLY") return "amber";
  return "muted";
}

function StatusPill({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "green" | "amber" }) {
  return <span className={"status-pill " + tone}><i />{children}</span>;
}

function MetricCard({ label, value, note, icon }: { label: string; value: string; note: string; icon: string }) {
  return (
    <article className="metric-card">
      <div className="metric-top"><span>{label}</span><b>{icon}</b></div>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

export default function Home() {
  const [active, setActive] = useState("Overview");
  const [search, setSearch] = useState("");
  const [apiData, setApiData] = useState<DashboardData>({
    loading: true,
    health: null,
    markets: null,
    scanner: null,
    positions: null,
    history: null,
    research: null,
    backtests: null,
    risk: null
  });
  const currentNav = navigation.find((item) => item.label === active);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const [health, markets, scanner, positions, history, research, backtests, risk] = await Promise.all([
          fetchApi<HealthSnapshot>("health"),
          fetchApi<MarketSnapshot>("markets"),
          fetchApi<ScannerSnapshot>("scanner/candidates"),
          fetchApi<PositionsSnapshot>("paper/positions"),
          fetchApi<HistorySnapshot>("paper/history"),
          fetchApi<ResearchSnapshot>("research/experiments"),
          fetchApi<BacktestSnapshot>("backtests"),
          fetchApi<RiskSnapshot>("risk/summary")
        ]);
        if (!cancelled) {
          setApiData({ loading: false, health, markets, scanner, positions, history, research, backtests, risk });
        }
      } finally {
        inFlight = false;
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const marketRows = apiData.markets?.markets ?? [];
  const scannerSymbols = apiData.scanner?.symbols ?? [];
  const candidateCount =
    apiData.scanner && apiData.scanner.status !== "unavailable"
      ? scannerSymbols.reduce((total, item) => total + (item.candidates?.length ?? 0), 0)
      : null;
  const rejectedCandidateCount = scannerSymbols.reduce((total, item) => total + (item.rejected_candidates?.length ?? 0), 0);
  const staleScannerCount = scannerSymbols.filter((item) => item.status === "stale").length;
  const marketFeedStatus = apiData.markets?.status;
  const feedLabel =
    marketFeedStatus === "live" ? "PERSISTED CACHE FRESH" :
    marketFeedStatus === "stale" ? "MARKET CACHE STALE" :
    apiData.loading ? "CHECKING READ-ONLY API" : "MARKET DATA UNAVAILABLE";
  const feedTone = marketTone(marketFeedStatus);
  const approvedCount =
    apiData.health?.status === "available" && typeof apiData.health.approved_strategy_count === "number"
      ? String(apiData.health.approved_strategy_count)
      : "—";
  const positionsCount =
    apiData.positions?.status === "available" && typeof apiData.positions.position_count === "number"
      ? String(apiData.positions.position_count)
      : "—";
  const candidateValue = candidateCount == null ? "—" : String(candidateCount);
  const freshMarketCount = marketRows.filter((market) => market.status === "live").length;
  const paperPositionRows = apiData.positions?.positions ?? [];

  const renderMarketRows = () => {
    if (!marketRows.length) {
      return <div className="market-empty">No persisted market records are available from the read-only API.</div>;
    }
    return marketRows.map((market) => (
      <div className="market-row" key={market.symbol}>
        <div className="instrument">
          <div className="coin-icon">{market.symbol === "BTC" ? "₿" : market.symbol === "ETH" ? "◆" : market.symbol === "XAU" ? "Au" : "✣"}</div>
          <div>
            <strong>{market.instrument ?? market.symbol}</strong>
            <small>{market.symbol} · {market.last_price == null ? "Last close unavailable" : formatPrice(market)}</small>
          </div>
        </div>
        <span className="venue">{market.venue ?? "Venue unavailable"}<small>{formatAge(market.age_minutes)}</small></span>
        <StatusPill tone={marketTone(market.status)}>{marketLabel(market.status)}</StatusPill>
      </div>
    ));
  };

  const renderScannerCandidate = (candidate: ScannerCandidate, index: number) => {
    const direction = candidate.direction === "LONG" || candidate.direction === "SHORT" ? candidate.direction : "DIRECTION UNAVAILABLE";
    return (
      <article className="scanner-candidate" key={(candidate.strategy_id ?? "candidate") + "-" + index}>
        <div className="scanner-candidate-top">
          <div>
            <strong>{candidate.setup_type ?? candidate.strategy_id ?? "Candidate name unavailable"}</strong>
            <small>{candidate.strategy_id ?? "Strategy ID unavailable"}</small>
          </div>
          <StatusPill tone={direction === "LONG" ? "green" : direction === "SHORT" ? "amber" : "muted"}>{direction}</StatusPill>
        </div>
        <div className="scanner-level-grid">
          <div><span>ENTRY</span><strong>{formatLevel(candidate.entry, 4)}</strong></div>
          <div><span>STOP</span><strong>{formatLevel(candidate.stop_loss, 4)}</strong></div>
          <div><span>TARGET</span><strong>{formatLevel(candidate.take_profit, 4)}</strong></div>
        </div>
        <div className="scanner-meta">
          <span>R:R {formatLevel(candidate.rr, 2)}</span>
          <span>{candidate.quality_score == null ? "Quality unavailable" : "Quality points " + candidate.quality_score + "/100"}</span>
          <span>{candidate.timeframes_in_agreement?.length ? candidate.timeframes_in_agreement.join(" · ") : "Timeframe evidence unavailable"}</span>
        </div>
        {candidate.score_type ? <small className="scanner-disclaimer">{candidate.score_type === "RULE_QUALITY_POINTS_NOT_PROBABILITY" ? "Rule-quality points are not a probability or expected win rate." : candidate.score_type}</small> : null}
        {candidate.rationale ? <p className="scanner-rationale">{candidate.rationale}</p> : null}
        {candidate.invalidation ? <p className="scanner-invalidation">Invalidation: {candidate.invalidation}</p> : null}
      </article>
    );
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">S<span>Q</span></div>
          <div><strong>SALTY QUANT</strong><small>RESEARCH TERMINAL</small></div>
        </div>

        <div className="workspace-switch">
          <span className="workspace-dot" />
          <div><strong>Quant workspace</strong><small>Crypto · Paper only</small></div>
          <span className="chevron">⌄</span>
        </div>

        {["Workspace", "Research", "Execution", "Intelligence"].map((group) => (
          <div className="nav-group" key={group}>
            <p>{group}</p>
            {navigation.filter((item) => item.group === group).map((item) => (
              <button key={item.label} className={active === item.label ? "nav-item active" : "nav-item"} onClick={() => setActive(item.label)}>
                <span className="nav-icon">{item.icon}</span><span>{item.label}</span>
                {item.label === "AI Scanner" && <em>NEW</em>}
              </button>
            ))}
          </div>
        ))}

        <div className="sidebar-bottom">
          <div className="environment-card">
            <div className="environment-heading"><span className="pulse-dot" /> RESEARCH ENVIRONMENT</div>
            <strong>Live orders disabled</strong>
            <small>Read-only data and paper workflows only.</small>
          </div>
          <button className="nav-item settings" onClick={() => setActive("Settings")}><span className="nav-icon">⚙</span>Settings</button>
          <div className="user-row"><div className="avatar">SQ</div><div><strong>Salty Quant AI</strong><small>Research operator</small></div><span className="more">•••</span></div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumbs"><span>Salty Quant</span><b>/</b><strong>{active}</strong></div>
          <div className="topbar-actions">
            <div className="feed-state" aria-live="polite"><span className={feedTone === "green" ? "online-dot" : "offline-dot"} /> {feedLabel}</div>
            <span className="divider" />
            <button className="icon-button" aria-label="Notifications">♧<i /></button>
            <div className="avatar small">SQ</div>
          </div>
        </header>

        <div className="page-content">
          {active === "Overview" ? (
            <>
              <div className="page-heading">
                <div><div className="eyebrow">RESEARCH WORKSPACE <span>•</span> PERSISTED SNAPSHOTS</div><h1>Market overview</h1><p>Your research and paper-trading operations, in one place.</p></div>
                <div className="heading-tags"><StatusPill tone="green">PAPER MODE</StatusPill><StatusPill>SHADOW RESEARCH</StatusPill></div>
              </div>

              <div className="notice">
                <span className="notice-icon">i</span>
                <div><strong>{marketFeedStatus === "live" ? "Persisted market cache connected" : marketFeedStatus === "stale" ? "Market cache is stale" : apiData.loading ? "Connecting to the read-only API" : "Market data unavailable"}</strong><p>Prices are latest persisted closed-candle values, not websocket ticks. {apiData.markets?.source ?? "No market snapshot source is available."}</p></div>
                <span className="notice-code">{apiData.health?.api_version ? `API v${apiData.health.api_version}` : "API / UNAVAILABLE"}</span>
              </div>

              <div className="metric-grid">
                <MetricCard label="Total paper equity" value={apiData.risk?.account_equity == null ? "—" : apiData.risk.account_equity.toLocaleString("en-US")} note="Account capital is not persisted by the paper engine" icon="◉" />
                <MetricCard label="Open paper positions" value={positionsCount} note={apiData.positions?.status === "available" ? "Read-only paper ledger" : "Paper state unavailable"} icon="↗" />
                <MetricCard label="Research candidates" value={candidateValue} note={apiData.scanner?.status === "stale" ? "Latest persisted scan is stale" : apiData.scanner?.status === "unavailable" || !apiData.scanner ? "Scanner records unavailable" : "Latest persisted scanner records"} icon="⌕" />
                <MetricCard label="Approved strategies" value={approvedCount} note={apiData.health?.status === "available" ? "Authoritative approved strategy set" : "Approval state unavailable"} icon="◇" />
              </div>

              <div className="content-grid">
                <section className="panel market-panel">
                  <div className="panel-heading"><div><h2>Market watch</h2><p>Connected instruments and source status</p></div><button className="text-button" onClick={() => setActive("Live Markets")}>View markets <span>→</span></button></div>
                  <div className="market-table">
                    <div className="table-head"><span>INSTRUMENT</span><span>VENUE</span><span>DATA STATUS</span></div>
                    {renderMarketRows()}
                  </div>
                  <div className="panel-foot"><span className="tiny-dot" /> Read-only persisted cache · {apiData.markets?.as_of ?? "snapshot time unavailable"} · 5m freshness is not a websocket connection.</div>
                </section>

                <section className="panel system-panel">
                  <div className="panel-heading"><div><h2>System status</h2><p>Core research services</p></div><span className="system-icon">⌘</span></div>
                  <div className="system-list">
                    <div><span>Read-only API</span><StatusPill tone={apiData.health?.status === "available" ? "green" : "amber"}>{apiData.health?.status === "available" ? "Available" : "Unavailable"}</StatusPill></div>
                    <div><span>Persisted market cache</span><StatusPill tone={apiData.health?.checks?.market_data_cache === "present" ? "green" : "muted"}>{apiData.health?.checks?.market_data_cache ?? "Unknown"}</StatusPill></div>
                    <div><span>Saved backtest artifacts</span><StatusPill tone={apiData.backtests?.status === "available" ? "green" : "muted"}>{apiData.backtests?.status === "available" ? `${apiData.backtests.artifact_count ?? "?"} indexed` : "Unavailable"}</StatusPill></div>
                    <div><span>Paper ledger</span><StatusPill tone={apiData.positions?.status === "available" ? "green" : "muted"}>{apiData.positions?.status === "available" ? "Available" : "Unavailable"}</StatusPill></div>
                    <div><span>Telegram / Discord</span><StatusPill>Not exposed by read-only API</StatusPill></div>
                  </div>
                  <div className="system-note">The API only projects persisted repository data. It does not run strategies, backtests, paper lifecycle jobs or alerts.</div>
                </section>
              </div>

              <div className="content-grid lower-grid">
                <section className="panel chart-panel">
                  <div className="panel-heading"><div><h2>Market structure</h2><p>Candlestick chart component is not connected yet</p></div><StatusPill>CHART PENDING</StatusPill></div>
                  <div className="chart-placeholder"><div className="chart-axis"><span>—</span><span>—</span><span>—</span><span>—</span></div><div className="chart-grid"><div className="chart-message"><span className="chart-symbol">⌁</span><strong>Chart renderer not integrated</strong><small>Market snapshots are connected separately; no candles are drawn until a verified chart component is added.</small></div></div><div className="chart-bottom"><span>SYMBOL: —</span><span>TIMEFRAME: —</span><span>LAST UPDATE: —</span></div></div>
                </section>

                <section className="panel strategy-panel">
                  <div className="panel-heading"><div><h2>Strategy lanes</h2><p>Current deterministic research families</p></div><button className="text-button" onClick={() => setActive("Strategy Research")}>Research <span>→</span></button></div>
                  <div className="strategy-list">
                    {apiData.research?.entries?.length ? apiData.research.entries.slice(0, 5).map((entry, index) => <div className="strategy-row" key={entry.title}><div className="strategy-index">0{index + 1}</div><div className="strategy-copy"><strong>{entry.title}</strong><small>{entry.summary || "Ledger entry has no summary text."}</small></div><StatusPill>LEDGER</StatusPill></div>) : <div className="strategy-empty">Research ledger entries unavailable.</div>}
                  </div>
                </section>
              </div>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL <b>·</b> BUILD 0.1.0</span><span>RESEARCH FIRST. VERIFY EVERYTHING.</span></footer>
            </>
          ) : active === "Live Markets" ? (
            <>
              <div className="page-heading">
                <div><div className="eyebrow">READ-ONLY PERSISTED MARKET SNAPSHOT</div><h1>Live Markets</h1><p>Latest closed candles from the repository cache. Freshness does not imply a websocket or executable quote.</p></div>
                <StatusPill tone={marketTone(marketFeedStatus)}>{marketLabel(marketFeedStatus)}</StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div><strong>{marketFeedStatus === "live" ? "Persisted cache passes freshness checks" : marketFeedStatus === "stale" ? "Persisted cache is stale or discontinuous" : "Market snapshot unavailable"}</strong><p>{apiData.markets?.source ?? "The read-only API has not returned a source."} · Snapshot: {apiData.markets?.as_of ?? "unavailable"}</p></div>
                <span className="notice-code">NO ORDER ROUTES</span>
              </div>
              <section className="panel market-panel full-market-panel">
                <div className="panel-heading"><div><h2>Crypto and gold instruments</h2><p>Configured repository instruments · Delta public OHLCV cache</p></div><StatusPill>READ ONLY</StatusPill></div>
                <div className="market-table">
                  <div className="table-head"><span>INSTRUMENT / LAST CLOSE</span><span>VENUE / AGE</span><span>5M STATUS</span></div>
                  {renderMarketRows()}
                </div>
                <div className="panel-foot"><span className="tiny-dot" /> Prices are the latest persisted closed 5m candles, not live bid/ask quotes.</div>
              </section>
              <div className="content-grid live-market-meta">
                <section className="panel system-panel">
                  <div className="panel-heading"><div><h2>Snapshot metadata</h2><p>Provenance and API state</p></div></div>
                  <div className="metadata-list">
                    <div><span>API status</span><strong>{apiData.health?.status ?? "unavailable"}</strong></div>
                    <div><span>API version</span><strong>{apiData.health?.api_version ?? "unavailable"}</strong></div>
                    <div><span>Snapshot time</span><strong>{apiData.markets?.as_of ?? "unavailable"}</strong></div>
                    <div><span>Source</span><strong>{apiData.markets?.source ?? "unavailable"}</strong></div>
                  </div>
                </section>
                <section className="panel system-panel">
                  <div className="panel-heading"><div><h2>Timeframe freshness</h2><p>Per-instrument cache status</p></div></div>
                  <div className="timeframe-list">
                    {marketRows.length ? marketRows.map((market) => <div className="timeframe-row" key={market.symbol}><strong>{market.instrument ?? market.symbol}</strong><div>{Object.entries(market.timeframes ?? {}).map(([timeframe, state]) => <span key={timeframe} className={state.status === "live" ? "timeframe-chip fresh" : state.status === "stale" ? "timeframe-chip stale" : "timeframe-chip"}>{timeframe} · {state.status}</span>)}</div></div>) : <div className="strategy-empty">Timeframe status unavailable.</div>}
                  </div>
                </section>
              </div>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL <b>·</b> BUILD 0.2.0</span><span>READ-ONLY MARKET SNAPSHOTS</span></footer>
            </>
          ) : active === "AI Scanner" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PERSISTED DETERMINISTIC SCANNER SNAPSHOT</div>
                  <h1>AI Scanner</h1>
                  <p>Read-only candidate records from the existing scanner. This page does not generate, rank or execute new signals.</p>
                </div>
                <StatusPill tone={marketTone(apiData.scanner?.status)}>{apiData.scanner?.status ?? "unavailable"}</StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div>
                  <strong>{apiData.scanner?.status === "live" ? "Latest scanner records are within the freshness window" : apiData.scanner?.status === "stale" ? "Scanner records are stale" : apiData.loading ? "Loading persisted scanner records" : "Scanner records unavailable"}</strong>
                  <p>{apiData.scanner?.source ?? "Scanner source unavailable"} · Snapshot: {apiData.scanner?.as_of ?? "timestamp unavailable"} · Malformed lines in retained tail: {apiData.scanner?.malformed_lines_in_tail ?? "unavailable"}</p>
                </div>
                <span className="notice-code">READ ONLY</span>
              </div>
              <div className="metric-grid">
                <MetricCard label="Symbols scanned" value={apiData.scanner?.status === "unavailable" || !apiData.scanner ? "—" : String(scannerSymbols.length)} note="Latest persisted record per symbol" icon="⌕" />
                <MetricCard label="Research candidates" value={candidateCount == null ? "—" : String(candidateCount)} note="Candidate records; not approved strategies" icon="◈" />
                <MetricCard label="Rejected candidates" value={apiData.scanner?.status === "unavailable" || !apiData.scanner ? "—" : String(rejectedCandidateCount)} note="Recorded mechanical rejections" icon="×" />
                <MetricCard label="Stale symbols" value={apiData.scanner?.status === "unavailable" || !apiData.scanner ? "—" : String(staleScannerCount)} note="Freshness is checked from persisted timestamps" icon="◷" />
              </div>
              <div className="scanner-list">
                {scannerSymbols.length ? scannerSymbols.map((item) => (
                  <section className="panel scanner-symbol" key={item.symbol}>
                    <div className="panel-heading">
                      <div>
                        <h2>{item.symbol}</h2>
                        <p>Last scanner record: {formatScannerTimestamp(item.timestamp)}</p>
                      </div>
                      <div className="scanner-heading-status">
                        <StatusPill tone={marketTone(item.status)}>{item.status ?? "unavailable"}</StatusPill>
                        <StatusPill tone={scannerDecisionTone(item.decision_status)}>{item.decision_status ?? "DECISION UNAVAILABLE"}</StatusPill>
                      </div>
                    </div>
                    <div className="scanner-symbol-body">
                      <div className="scanner-context">
                        <div><span>LAST CLOSED 5M PRICE</span><strong>{formatLevel(item.latest_closed_5m_price, 4)}</strong></div>
                        <div><span>TRIGGER CANDLE</span><strong>{formatScannerTimestamp(item.latest_closed_5m_candle)}</strong></div>
                        <div><span>OPEN PAPER POSITION</span><strong>{item.has_open_position == null ? "Unknown" : item.has_open_position ? "Yes" : "No"}</strong></div>
                      </div>
                      <p className="scanner-decision-reason">{item.decision_reason ?? "Decision reason unavailable."}</p>
                      {item.research_preview_strategy ? <p className="scanner-preview">Research preview: <strong>{item.research_preview_strategy}</strong></p> : null}
                      {item.selected_strategy ? <p className="scanner-preview">Selected strategy: <strong>{item.selected_strategy}</strong></p> : null}
                      <div className="scanner-section-heading"><strong>Candidate records</strong><span>{item.candidates?.length ?? 0}</span></div>
                      {item.candidates?.length ? <div className="scanner-candidate-grid">{item.candidates.map(renderScannerCandidate)}</div> : <div className="strategy-empty">No candidate records were persisted for this symbol.</div>}
                      {item.rejected_candidates?.length ? (
                        <details className="rejected-list">
                          <summary>{item.rejected_candidates.length} rejected candidate record(s)</summary>
                          {item.rejected_candidates.slice(0, 10).map((rejected, index) => (
                            <div key={(rejected.strategy_id ?? "rejected") + "-" + index}>
                              <strong>{rejected.strategy_id ?? "Strategy unavailable"}</strong>
                              <span>{rejected.reason ?? "Rejection reason unavailable."}</span>
                            </div>
                          ))}
                        </details>
                      ) : null}
                    </div>
                  </section>
                )) : <section className="panel"><div className="strategy-empty">{apiData.scanner?.status === "unavailable" || !apiData.scanner ? "The persisted scanner log is unavailable; no metrics are inferred." : "No scanner symbol records are currently persisted."}</div></section>}
              </div>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL · SCANNER</span><span>SHADOW / RESEARCH ONLY UNTIL VALIDATED</span></footer>
            </>
          ) : active === "Strategy Research" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">REPOSITORY RESEARCH LEDGER</div>
                  <h1>Strategy Research</h1>
                  <p>Recent ledger sections and recorded hypotheses. A heading is not a validation or promotion decision.</p>
                </div>
                <StatusPill tone={apiData.research?.status === "available" ? "green" : "amber"}>{apiData.research?.status ?? "unavailable"}</StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div>
                  <strong>{apiData.research?.status === "available" ? "Research ledger connected" : apiData.loading ? "Loading research ledger" : "Research ledger unavailable"}</strong>
                  <p>{apiData.research?.source ?? "Ledger source unavailable"} · Entries returned: {apiData.research?.entry_count ?? "unavailable"}</p>
                </div>
                <span className="notice-code">NO AUTO-PROMOTION</span>
              </div>
              <section className="panel research-ledger-panel">
                <div className="panel-heading">
                  <div><h2>Recent research history</h2><p>Latest parsed H2 sections from the repository ledger</p></div>
                  <StatusPill>LEDGER ENTRIES</StatusPill>
                </div>
                <div className="research-entry-list">
                  {apiData.research?.entries?.length ? apiData.research.entries.map((entry, index) => (
                    <article className="research-entry" key={entry.title + "-" + index}>
                      <div className="research-entry-marker">{String(index + 1).padStart(2, "0")}</div>
                      <div className="research-entry-copy">
                        <strong>{entry.title}</strong>
                        <p>{entry.summary || "No summary text was recorded for this ledger section."}</p>
                      </div>
                      <StatusPill>HISTORY</StatusPill>
                    </article>
                  )) : <div className="strategy-empty">{apiData.research?.status === "available" ? "The ledger is readable but no H2 entries were returned." : "The research ledger is unavailable; no research status is inferred."}</div>}
                </div>
                <div className="panel-foot">This view displays ledger text only. Strategy approval remains controlled by the existing deterministic validation gates.</div>
              </section>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL · RESEARCH</span><span>HYPOTHESES ≠ VALIDATED STRATEGIES</span></footer>
            </>
          ) : active === "Backtesting" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PERSISTED QUANT DISCOVERY ARTIFACTS</div>
                  <h1>Backtesting</h1>
                  <p>Read-only inventory of saved experiment outputs. This page never launches or recomputes a backtest.</p>
                </div>
                <StatusPill tone={apiData.backtests?.status === "available" ? "green" : "amber"}>
                  {apiData.backtests?.status ?? "unavailable"}
                </StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div>
                  <strong>{apiData.backtests?.status === "available" ? "Saved research artifacts are indexed" : apiData.loading ? "Loading saved artifacts" : "Backtest artifacts unavailable"}</strong>
                  <p>{apiData.backtests?.source ?? "Artifact source unavailable"} · The inventory is not a strategy approval or a claim that every file contains a completed test.</p>
                </div>
                <span className="notice-code">READ ONLY</span>
              </div>
              <div className="metric-grid">
                <MetricCard
                  label="Indexed artifacts"
                  value={apiData.backtests?.status === "available" ? String(apiData.backtests.artifact_count ?? 0) : "—"}
                  note="Persisted files discovered"
                  icon="▤"
                />
                <MetricCard label="Execution" value="Disabled" note="No backtest is launched here" icon="⌁" />
                <MetricCard label="Source" value="Repository" note="quant_discovery artifacts" icon="◈" />
                <MetricCard label="Promotion" value="Separate gate" note="No automatic approval" icon="⛨" />
              </div>
              <section className="panel backtest-artifacts-panel">
                <div className="panel-heading">
                  <div><h2>Saved experiment artifacts</h2><p>Metadata and file provenance returned by the read-only API</p></div>
                  <StatusPill>ARTIFACT INVENTORY</StatusPill>
                </div>
                <div className="backtest-artifact-list">
                  {apiData.backtests?.artifacts?.length ? apiData.backtests.artifacts.map((artifact) => (
                    <article className="backtest-artifact" key={artifact.path}>
                      <div className="backtest-artifact-heading">
                        <div className="backtest-artifact-title">
                          <strong>{artifact.name}</strong>
                          <small>{artifact.path}</small>
                        </div>
                        <StatusPill>FILE ONLY</StatusPill>
                      </div>
                      <div className="backtest-artifact-meta">
                        <div><span>FILE SIZE</span><strong>{formatArtifactBytes(artifact.bytes)}</strong></div>
                        <div><span>RESEARCH TYPE</span><strong>{formatArtifactValue(artifact.metadata?.research_type ?? artifact.metadata?.artifact_type ?? artifact.metadata?.data_classification)}</strong></div>
                        <div><span>VALIDATION STATE</span><strong>{formatArtifactValue(artifact.metadata?.validation_state)}</strong></div>
                        <div><span>SYMBOL / ASSET</span><strong>{formatArtifactValue(artifact.metadata?.symbol ?? artifact.metadata?.asset)}</strong></div>
                        <div><span>STRATEGY</span><strong>{formatArtifactValue(artifact.metadata?.strategy ?? artifact.metadata?.strategy_id)}</strong></div>
                        <div><span>RECORDED TRADES</span><strong>{formatArtifactValue(artifact.metadata?.trade_count)}</strong></div>
                      </div>
                      {artifact.metadata && Object.keys(artifact.metadata).length > 0 ? (
                        <details className="backtest-artifact-details">
                          <summary>Recorded metadata · not an approval decision</summary>
                          <div className="backtest-metadata-list">
                            {Object.entries(artifact.metadata).map(([key, value]) => (
                              <div key={key}><span>{key.replace(/_/g, " ")}</span><strong>{formatArtifactValue(value)}</strong></div>
                            ))}
                          </div>
                        </details>
                      ) : null}
                      {artifact.columns?.length ? (
                        <p className="backtest-columns">CSV columns: {artifact.columns.join(" · ")}</p>
                      ) : null}
                      {artifact.columns?.length && artifact.rows?.length ? (
                        <details className="backtest-csv-preview">
                          <summary>Last {artifact.rows.length} persisted CSV rows · preview only</summary>
                          <div className="backtest-csv-table-wrap">
                            <table className="backtest-csv-table">
                              <thead>
                                <tr>{artifact.columns.map((column) => <th key={column}>{column.replace(/_/g, " ")}</th>)}</tr>
                              </thead>
                              <tbody>
                                {artifact.rows.map((row, rowIndex) => (
                                  <tr key={rowIndex}>
                                    {artifact.columns!.map((column) => <td key={column}>{row[column] ?? "—"}</td>)}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </details>
                      ) : null}
                      {artifact.metadata_status === "unreadable" || artifact.data_status === "unreadable" ? (
                        <p className="backtest-warning">The file exists, but its metadata or sample rows could not be parsed.</p>
                      ) : null}
                    </article>
                  )) : (
                    <div className="strategy-empty">
                      {apiData.backtests?.status === "available"
                        ? "The artifact directory is readable, but no supported metadata, primary CSV or results files were indexed."
                        : "No artifact inventory is available. Missing files are not treated as zero trades or failed strategies."}
                    </div>
                  )}
                </div>
                <div className="panel-foot">Artifact presence does not prove reproducibility, validation, positive expectancy or promotion. Open each experiment report for its dataset, assumptions, costs and evaluation splits.</div>
              </section>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL · BACKTESTING</span><span>ARTIFACTS ≠ VALIDATED STRATEGIES</span></footer>
            </>
          ) : active === "Paper Trading" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PERSISTED PAPER POSITION LEDGER</div>
                  <h1>Paper Trading</h1>
                  <p>Open simulated positions from the existing paper lifecycle state. This page is read-only and cannot create, close or modify trades.</p>
                </div>
                <StatusPill tone={apiData.positions?.status === "available" ? "green" : "amber"}>{apiData.positions?.status ?? "unavailable"}</StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div>
                  <strong>{apiData.positions?.status === "available" ? "Paper position state is readable" : apiData.loading ? "Loading paper state" : "Paper state unavailable"}</strong>
                  <p>{apiData.positions?.reason ?? apiData.positions?.source ?? "The API has not returned a paper-state source."} · Positions are persisted simulations, not exchange positions.</p>
                </div>
                <span className="notice-code">NO ORDER ROUTES</span>
              </div>
              <div className="metric-grid">
                <MetricCard label="Open paper positions" value={apiData.positions?.status === "available" ? String(apiData.positions.position_count ?? "—") : "—"} note="Persisted position records" icon="↗" />
                <MetricCard label="Pending outcomes" value={apiData.positions?.status === "available" ? formatArtifactValue(apiData.positions.pending_outcome_count) : "—"} note="Existing lifecycle queue" icon="◷" />
                <MetricCard label="Account equity" value="—" note="Not persisted by the current paper engine" icon="◉" />
                <MetricCard label="Execution" value="Read only" note="No create, close or modify controls" icon="⛨" />
              </div>
              <section className="panel paper-ledger-panel">
                <div className="panel-heading">
                  <div><h2>Open simulated positions</h2><p>Entry geometry and provenance from the persisted paper state</p></div>
                  <StatusPill>SIMULATED ONLY</StatusPill>
                </div>
                {apiData.positions?.positions?.length ? (
                  <div className="paper-position-list">
                    <div className="paper-position-row paper-table-head"><span>SYMBOL / SETUP</span><span>DIRECTION</span><span>ENTRY</span><span>STOP</span><span>TARGET</span><span>R:R</span><span>STATUS</span></div>
                    {apiData.positions.positions.map((position, index) => (
                      <div className="paper-position-row" key={position.signal_id ?? position.sym ?? index}>
                        <div><strong>{position.sym ?? "—"}</strong><small>{position.strategy_id ?? position.setup_type ?? "Strategy unavailable"}</small></div>
                        <span>{position.dir ?? "—"}</span>
                        <span>{formatLevel(position.entry, 6)}</span>
                        <span>{formatLevel(position.sl, 6)}</span>
                        <span>{formatLevel(position.tp, 6)}</span>
                        <span>{formatLevel(position.rr, 2)}</span>
                        <StatusPill>{position.status ?? "status unavailable"}</StatusPill>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="paper-empty">{apiData.positions?.status === "available" ? "No open paper positions are currently persisted." : "Paper positions cannot be displayed until the source state is available."}</div>
                )}
                <div className="panel-foot">Source: {apiData.positions?.source ?? "unavailable"} · Snapshot: {apiData.positions?.as_of ?? "unavailable"} · No real exchange positions are queried.</div>
              </section>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL · PAPER TRADING</span><span>SIMULATION ONLY · READ ONLY</span></footer>
            </>
          ) : active === "Portfolio" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PAPER PORTFOLIO DIAGNOSTICS</div>
                  <h1>Portfolio</h1>
                  <p>Read-only risk summary from retained paper lifecycle records. This is not a funded account or exchange portfolio.</p>
                </div>
                <StatusPill tone={apiData.risk?.status === "available" ? "green" : "amber"}>{apiData.risk?.status ?? "unavailable"}</StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div>
                  <strong>{apiData.risk?.status === "available" ? "Retained paper risk diagnostics are readable" : apiData.loading ? "Loading paper risk state" : "Paper risk state unavailable"}</strong>
                  <p>{apiData.risk?.source ?? "Risk source unavailable"} · {apiData.risk?.as_of ?? "Snapshot time unavailable"} · Account capital and notional position quantities are not persisted.</p>
                </div>
                <span className="notice-code">NO REAL CAPITAL</span>
              </div>
              <div className="metric-grid">
                <MetricCard label="Account equity" value={formatLevel(apiData.risk?.account_equity, 2)} note="Unavailable in current paper-state schema" icon="◉" />
                <MetricCard label="Notional exposure" value={formatLevel(apiData.risk?.account_exposure, 2)} note="Position quantities are not persisted" icon="↗" />
                <MetricCard label="Open paper positions" value={apiData.risk?.status === "available" ? formatArtifactValue(apiData.risk.open_positions) : "—"} note="Source risk snapshot" icon="▤" />
                <MetricCard label="Pending outcomes" value={apiData.risk?.status === "available" ? formatArtifactValue(apiData.risk.pending_outcomes) : "—"} note="Existing lifecycle queue" icon="◷" />
                <MetricCard label="Retained gross R" value={formatLevel(apiData.risk?.realized_gross_r_retained_history, 3)} note="Sum of stored gross-R records" icon="◇" />
                <MetricCard label="Retained max drawdown" value={formatLevel(apiData.risk?.max_drawdown_r_retained_history, 3)} note="Gross-R sequence, retained history only" icon="⌁" />
                <MetricCard label="Trades in R diagnostic" value={formatArtifactValue(apiData.risk?.retained_history_trades)} note="Only records with numeric gross R" icon="◷" />
                <MetricCard label="Circuit breaker" value={apiData.risk?.circuit_breaker === "unavailable_not_persisted" ? "Unavailable" : apiData.risk?.circuit_breaker ?? "—"} note="Not persisted by the paper engine" icon="⛨" />
              </div>
              <section className="panel paper-ledger-panel">
                <div className="panel-heading">
                  <div><h2>Open paper symbols</h2><p>Symbols reported by the persisted paper risk snapshot</p></div>
                  <StatusPill>SIMULATED ONLY</StatusPill>
                </div>
                <div className="paper-symbol-list">
                  {apiData.risk?.status === "available" && apiData.risk.open_symbols ? (
                    apiData.risk.open_symbols.length
                      ? apiData.risk.open_symbols.map((symbol) => <span className="paper-symbol-chip" key={symbol}>{symbol}</span>)
                      : <div className="paper-empty">No open paper symbols are currently recorded.</div>
                  ) : <div className="paper-empty">Open-symbol data is unavailable.</div>}
                </div>
                <div className="panel-foot">This drawdown is a retained gross-R diagnostic, not account-equity drawdown. Costs, funding and unrealized P&L are not represented here.</div>
              </section>
              {apiData.risk?.limitations?.length ? (
                <section className="panel risk-limitations-panel">
                  <div className="panel-heading"><div><h2>Known data limitations</h2><p>Metrics intentionally left unavailable</p></div><StatusPill>TRANSPARENCY</StatusPill></div>
                  <ul>{apiData.risk.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
                </section>
              ) : null}
              <footer className="page-footer"><span>SALTY QUANT TERMINAL · PORTFOLIO</span><span>PAPER DIAGNOSTICS · NOT ACCOUNT EQUITY</span></footer>
            </>
          ) : active === "Trade History" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PERSISTED PAPER TRADE HISTORY</div>
                  <h1>Trade History</h1>
                  <p>Closed simulated trade records retained by the existing lifecycle engine. Gross R is not a fee-adjusted account return.</p>
                </div>
                <StatusPill tone={apiData.history?.status === "available" ? "green" : "amber"}>{apiData.history?.status ?? "unavailable"}</StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div>
                  <strong>{apiData.history?.status === "available" ? "Paper history is readable" : apiData.loading ? "Loading paper history" : "Paper history unavailable"}</strong>
                  <p>{apiData.history?.reason ?? apiData.history?.source ?? "The API has not returned a history source."} · Retained history is limited by the source engine.</p>
                </div>
                <span className="notice-code">NO LIVE TRADES</span>
              </div>
              <div className="metric-grid">
                <MetricCard label="Retained trade records" value={apiData.history?.status === "available" ? formatArtifactValue(apiData.history.trade_count) : "—"} note="Count reported by paper state" icon="◷" />
                <MetricCard label="Rows returned" value={apiData.history?.status === "available" ? String(apiData.history.trades?.length ?? 0) : "—"} note="Read-only API sample" icon="▤" />
                <MetricCard label="History retention" value={apiData.history?.retained_trade_limit == null ? "—" : String(apiData.history.retained_trade_limit)} note="Source engine retained-record limit" icon="⌁" />
                <MetricCard label="P&L basis" value="Gross R" note="Before fees, funding and slippage" icon="◇" />
              </div>
              <section className="panel paper-ledger-panel">
                <div className="panel-heading">
                  <div><h2>Closed paper trades</h2><p>Most recent records returned by the read-only API</p></div>
                  <StatusPill>HISTORICAL · PAPER</StatusPill>
                </div>
                {apiData.history?.trades?.length ? (
                  <div className="paper-history-list">
                    <div className="paper-history-row paper-table-head"><span>SYMBOL / STRATEGY</span><span>SIDE</span><span>ENTRY</span><span>EXIT</span><span>GROSS R</span><span>STATUS</span><span>EXIT TIME</span></div>
                    {apiData.history.trades.slice().reverse().map((trade, index) => (
                      <div className="paper-history-row" key={trade.signal_id ?? (trade.sym ?? "trade") + "-" + index}>
                        <div><strong>{trade.sym ?? "—"}</strong><small>{trade.strategy_id ?? trade.setup_type ?? "Strategy unavailable"}</small></div>
                        <span>{trade.dir ?? "—"}</span>
                        <span>{formatLevel(trade.entry, 6)}</span>
                        <span>{formatLevel(trade.exit, 6)}</span>
                        <strong>{formatLevel(trade.gross_R, 3)}</strong>
                        <StatusPill>{trade.status ?? "status unavailable"}</StatusPill>
                        <span>{trade.exit_time ?? "—"}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="paper-empty">{apiData.history?.status === "available" ? "No closed paper trades are currently retained." : "Trade history cannot be displayed until the source state is available."}</div>
                )}
                <div className="panel-foot">Source: {apiData.history?.source ?? "unavailable"} · Returned rows: {apiData.history?.trades?.length ?? "unavailable"} · Gross R is the stored lifecycle field, not net realized account P&L.</div>
              </section>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL · TRADE HISTORY</span><span>GROSS RESULTS · PAPER ONLY</span></footer>
            </>
          ) : active === "AI Analyst" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">DETERMINISTIC EVIDENCE BRIEF · READ ONLY</div>
                  <h1>AI Analyst</h1>
                  <p>A source-grounded summary of persisted market, scanner, research, backtest and paper records. No external model call or signal generation is performed here.</p>
                </div>
                <StatusPill tone="green">EVIDENCE MODE</StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div>
                  <strong>This analyst does not predict prices or recommend trades</strong>
                  <p>Every observation below is derived from the same read-only API snapshots used elsewhere in the terminal. Missing or stale sources remain explicitly unavailable.</p>
                </div>
                <span className="notice-code">NO ORDERS</span>
              </div>
              <div className="metric-grid">
                <MetricCard label="Fresh market snapshots" value={apiData.markets?.status === "unavailable" || !apiData.markets ? "—" : String(freshMarketCount) + " / " + String(marketRows.length)} note={apiData.markets?.status === "live" ? "Persisted 5m cache passed freshness checks" : apiData.markets?.status === "stale" ? "One or more market snapshots are stale" : "Market source unavailable"} icon="◫" />
                <MetricCard label="Scanner candidates" value={candidateCount == null ? "—" : String(candidateCount)} note={apiData.scanner?.status === "stale" ? "Count comes from a stale persisted scan" : "Persisted candidate records; not win probabilities"} icon="⌕" />
                <MetricCard label="Research artifacts" value={apiData.backtests?.status === "available" ? String(apiData.backtests.artifact_count ?? "—") : "—"} note="File inventory only; not a count of profitable strategies" icon="▤" />
                <MetricCard label="Open paper positions" value={apiData.positions?.status === "available" ? String(apiData.positions.position_count ?? "—") : "—"} note="Simulated ledger only; no exchange positions" icon="⇄" />
              </div>
              <div className="content-grid analyst-grid">
                <section className="panel analyst-evidence-panel">
                  <div className="panel-heading"><div><h2>Current evidence state</h2><p>Source status, not an inferred market forecast</p></div><StatusPill>SNAPSHOT</StatusPill></div>
                  <div className="analyst-evidence-list">
                    <div><span>Market cache</span><StatusPill tone={marketTone(apiData.markets?.status)}>{apiData.markets?.status ?? "unavailable"}</StatusPill><small>{apiData.markets?.source ?? "Source unavailable"}</small></div>
                    <div><span>Deterministic scanner</span><StatusPill tone={marketTone(apiData.scanner?.status)}>{apiData.scanner?.status ?? "unavailable"}</StatusPill><small>{apiData.scanner?.as_of ?? "Snapshot time unavailable"}</small></div>
                    <div><span>Research ledger</span><StatusPill tone={apiData.research?.status === "available" ? "green" : "amber"}>{apiData.research?.status ?? "unavailable"}</StatusPill><small>{apiData.research?.entry_count == null ? "Entry count unavailable" : String(apiData.research.entry_count) + " parsed sections"}</small></div>
                    <div><span>Backtest inventory</span><StatusPill tone={apiData.backtests?.status === "available" ? "green" : "amber"}>{apiData.backtests?.status ?? "unavailable"}</StatusPill><small>{apiData.backtests?.source ?? "Artifact source unavailable"}</small></div>
                    <div><span>Paper ledger</span><StatusPill tone={apiData.positions?.status === "available" ? "green" : "amber"}>{apiData.positions?.status ?? "unavailable"}</StatusPill><small>{apiData.positions?.source ?? "Paper source unavailable"}</small></div>
                  </div>
                  <div className="panel-foot">Approved strategy count from the existing supervisor: {approvedCount}. The analyst cannot alter approval state.</div>
                </section>
                <section className="panel analyst-latest-panel">
                  <div className="panel-heading"><div><h2>Latest research record</h2><p>Most recent parsed ledger section</p></div><StatusPill>HISTORY</StatusPill></div>
                  {apiData.research?.entries?.[0] ? (
                    <div className="analyst-latest-copy">
                      <strong>{apiData.research.entries[0].title}</strong>
                      <p>{apiData.research.entries[0].summary || "The ledger section has no summary paragraph."}</p>
                    </div>
                  ) : (
                    <div className="paper-empty">No latest research record is available. The analyst will not infer a research conclusion.</div>
                  )}
                  <div className="panel-foot">A ledger heading or saved artifact is not, by itself, a validation or promotion decision.</div>
                </section>
              </div>
              <section className="panel analyst-guardrails-panel">
                <div className="panel-heading"><div><h2>Evidence guardrails</h2><p>What this analyst can and cannot conclude</p></div><StatusPill>TRANSPARENCY</StatusPill></div>
                <div className="analyst-guardrails">
                  <div><b>01</b><span>Candidate counts are not probabilities or expected win rates.</span></div>
                  <div><b>02</b><span>Backtest artifact counts do not establish positive expectancy or out-of-sample validity.</span></div>
                  <div><b>03</b><span>Stored paper gross R is not fee-adjusted account P&amp;L or equity drawdown.</span></div>
                  <div><b>04</b><span>Stale, missing or unsupported fields remain unavailable instead of being estimated.</span></div>
                  <div><b>05</b><span>No signal, strategy approval, order or execution alert can be created from this page.</span></div>
                </div>
              </section>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL · AI ANALYST</span><span>DETERMINISTIC EVIDENCE · NO GENERATIVE CLAIMS</span></footer>
            </>
          ) : active === "Risk Management" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PAPER RISK VISIBILITY · READ ONLY</div>
                  <h1>Risk Management</h1>
                  <p>Persisted paper-ledger diagnostics and explicit risk-data gaps. This is not an account-level risk engine.</p>
                </div>
                <StatusPill tone={apiData.risk?.status === "available" ? "green" : "amber"}>{apiData.risk?.status ?? "unavailable"}</StatusPill>
              </div>
              <div className="notice">
                <span className="notice-icon">i</span>
                <div>
                  <strong>{apiData.risk?.status === "available" ? "Paper risk snapshot is readable" : apiData.loading ? "Loading paper risk snapshot" : "Paper risk snapshot unavailable"}</strong>
                  <p>{apiData.risk?.source ?? "Risk source unavailable"} · {apiData.risk?.as_of ?? "Snapshot time unavailable"} · Values below are limited to persisted paper records.</p>
                </div>
                <span className="notice-code">NO LIVE RISK CONTROLS</span>
              </div>
              <div className="metric-grid">
                <MetricCard label="Open paper positions" value={apiData.risk?.status === "available" ? formatArtifactValue(apiData.risk.open_positions) : "—"} note="Persisted simulated positions" icon="⇄" />
                <MetricCard label="Pending outcomes" value={apiData.risk?.status === "available" ? formatArtifactValue(apiData.risk.pending_outcomes) : "—"} note="Existing lifecycle queue" icon="◷" />
                <MetricCard label="Retained gross R" value={apiData.risk?.status === "available" ? formatLevel(apiData.risk.realized_gross_r_retained_history, 3) : "—"} note="Stored gross-R history only" icon="◇" />
                <MetricCard label="Retained gross-R drawdown" value={apiData.risk?.status === "available" ? formatLevel(apiData.risk.max_drawdown_r_retained_history, 3) : "—"} note="Not account-equity drawdown" icon="⌁" />
                <MetricCard label="Account equity" value="—" note="Not persisted by the current paper engine" icon="◉" />
                <MetricCard label="Notional exposure" value="—" note="Position quantities are not persisted" icon="↗" />
                <MetricCard label="Circuit breaker" value="—" note="No persisted circuit-breaker state" icon="⛨" />
                <MetricCard label="Numeric gross-R records" value={apiData.risk?.status === "available" ? formatArtifactValue(apiData.risk.retained_history_trades) : "—"} note="Records included in the retained R diagnostic" icon="▤" />
              </div>
              <section className="panel risk-position-panel">
                <div className="panel-heading"><div><h2>Open-position price risk</h2><p>Entry-to-stop distance per simulated position; size and capital risk are unknown</p></div><StatusPill>PRICE GEOMETRY ONLY</StatusPill></div>
                {apiData.positions?.status === "available" && paperPositionRows.length ? (
                  <div className="risk-position-list">
                    <div className="risk-position-row risk-position-head"><span>SYMBOL / STRATEGY</span><span>SIDE</span><span>ENTRY</span><span>STOP</span><span>PRICE DISTANCE</span><span>DISTANCE %</span></div>
                    {paperPositionRows.map((position, index) => {
                      const entry = position.entry;
                      const stop = position.sl;
                      const valid = typeof entry === "number" && Number.isFinite(entry) && entry > 0 && typeof stop === "number" && Number.isFinite(stop);
                      const distance = valid ? Math.abs(entry - stop) : null;
                      const distancePct = valid && distance != null ? (distance / entry) * 100 : null;
                      return (
                        <div className="risk-position-row" key={position.signal_id ?? position.sym ?? index}>
                          <div><strong>{position.sym ?? "—"}</strong><small>{position.strategy_id ?? position.setup_type ?? "Strategy unavailable"}</small></div>
                          <span>{position.dir ?? "—"}</span>
                          <span>{formatLevel(entry, 6)}</span>
                          <span>{formatLevel(stop, 6)}</span>
                          <span>{formatLevel(distance, 6)}</span>
                          <span>{distancePct == null ? "—" : formatLevel(distancePct, 3) + "%"}</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="paper-empty">{apiData.positions?.status === "available" ? "No open paper positions are currently persisted." : "Position geometry is unavailable because the paper-state source is unavailable."}</div>
                )}
                <div className="panel-foot">Distance is absolute entry-to-stop price movement. Without quantity, leverage, contract multiplier and account equity it cannot be converted into monetary risk or portfolio exposure.</div>
              </section>
              <section className="panel risk-readiness-panel">
                <div className="panel-heading"><div><h2>Risk-control data readiness</h2><p>Required inputs for an account-level risk engine</p></div><StatusPill>GAPS EXPOSED</StatusPill></div>
                <div className="risk-readiness-grid">
                  <div><span>Account capital / equity</span><StatusPill>NOT PERSISTED</StatusPill><small>Risk per trade and account drawdown cannot be calculated.</small></div>
                  <div><span>Position quantity / notional</span><StatusPill>NOT PERSISTED</StatusPill><small>Portfolio concentration and leverage cannot be calculated.</small></div>
                  <div><span>Daily loss limit / circuit breaker</span><StatusPill>NOT PERSISTED</StatusPill><small>No active risk-control state is exposed by the paper engine.</small></div>
                  <div><span>Net costs / funding cashflows</span><StatusPill>NOT IN GROSS R</StatusPill><small>Stored lifecycle gross R excludes fee-adjusted account P&amp;L.</small></div>
                  <div><span>Trade-level stop geometry</span><StatusPill tone={apiData.positions?.status === "available" ? "green" : "amber"}>{apiData.positions?.status === "available" ? "AVAILABLE WHEN PRESENT" : "UNAVAILABLE"}</StatusPill><small>Price distance can be displayed for persisted open positions.</small></div>
                  <div><span>Retained history</span><StatusPill tone={apiData.history?.status === "available" ? "green" : "amber"}>{apiData.history?.status ?? "unavailable"}</StatusPill><small>{apiData.history?.retained_trade_limit == null ? "Retention limit unavailable" : "Source retention limit: " + String(apiData.history.retained_trade_limit) + " records"}.</small></div>
                </div>
              </section>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL · RISK MANAGEMENT</span><span>DIAGNOSTICS ONLY · NO AUTOMATIC CONTROLS</span></footer>
            </>
          ) : (
            <div className="module-empty">
              <div className="module-icon">{currentNav?.icon ?? "⚙"}</div>
              <div className="eyebrow">MODULE FOUNDATION</div>
              <h1>{active}</h1>
              <p>This module is mapped in the product architecture but is not connected yet. Only modules with a documented read-only API projection will display repository data.</p>
              <div className="module-state"><StatusPill tone="amber">API INTEGRATION PENDING</StatusPill><span>Placeholder only · no simulated market metrics</span></div>
              <button className="back-button" onClick={() => setActive("Overview")}>← Back to overview</button>
            </div>
          )}
        </div>
      </section>
      <aside className="right-rail">
        <div className="rail-top"><span>QUANT TERMINAL</span><span className="rail-live">● DEVELOPMENT</span></div>
        <div className="rail-card">
          <div className="rail-label">WORKSPACE SEARCH</div>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search modules..." />
          {search && <div className="search-results">{navigation.filter((item) => item.label.toLowerCase().includes(search.toLowerCase())).map((item) => <button key={item.label} onClick={() => { setActive(item.label); setSearch(""); }}>{item.label} <span>→</span></button>)}</div>}
        </div>
        <div className="rail-card">
          <div className="rail-label">RESEARCH PRINCIPLES</div>
          <div className="principle"><b>01</b><span>Evidence before signals</span></div>
          <div className="principle"><b>02</b><span>Out-of-sample validation</span></div>
          <div className="principle"><b>03</b><span>Risk before return</span></div>
          <div className="principle"><b>04</b><span>No fabricated metrics</span></div>
        </div>
        <div className="rail-spacer" />
        <div className="rail-footer"><div className="footer-mark">SQ</div><div><strong>Salty Quant AI</strong><small>Independent research workspace</small></div></div>
      </aside>
    </main>
  );
}
