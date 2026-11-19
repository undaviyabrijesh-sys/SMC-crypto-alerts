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

type PositionsSnapshot = {
  status: string;
  position_count?: number | null;
  positions?: unknown[] | null;
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
  account_equity?: number | null;
  account_exposure?: number | null;
};

type DashboardData = {
  loading: boolean;
  health: HealthSnapshot | null;
  markets: MarketSnapshot | null;
  scanner: ScannerSnapshot | null;
  positions: PositionsSnapshot | null;
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
        const [health, markets, scanner, positions, research, backtests, risk] = await Promise.all([
          fetchApi<HealthSnapshot>("health"),
          fetchApi<MarketSnapshot>("markets"),
          fetchApi<ScannerSnapshot>("scanner/candidates"),
          fetchApi<PositionsSnapshot>("paper/positions"),
          fetchApi<ResearchSnapshot>("research/experiments"),
          fetchApi<BacktestSnapshot>("backtests"),
          fetchApi<RiskSnapshot>("risk/summary")
        ]);
        if (!cancelled) {
          setApiData({ loading: false, health, markets, scanner, positions, research, backtests, risk });
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
                <div><div className="eyebrow">THURSDAY, NOVEMBER 19, 2026 <span>•</span> RESEARCH WORKSPACE</div><h1>Market overview</h1><p>Your research and paper-trading operations, in one place.</p></div>
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
                        <div><span>SYMBOL / ASSET</span><strong>{formatArtifactValue(artifact.metadata?.symbol ?? artifact.metadata?.asset)}</strong></div>
                        <div><span>STRATEGY</span><strong>{formatArtifactValue(artifact.metadata?.strategy ?? artifact.metadata?.strategy_id)}</strong></div>
                        <div><span>RECORDED TRADES</span><strong>{formatArtifactValue(artifact.metadata?.trade_count)}</strong></div>
                      </div>
                      {artifact.metadata && Object.keys(artifact.metadata).length > 0 ? (
                        <details className="backtest-artifact-details">
                          <summary>Recorded metadata · not an approval decision</summary>
                          <div className="backtest-metadata-list">
                            {Object.entries(artifact.metadata).map(([key, value]) => (
                              <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{formatArtifactValue(value)}</strong></div>
                            ))}
                          </div>
                        </details>
                      ) : null}
                      {artifact.columns?.length ? (
                        <p className="backtest-columns">CSV columns: {artifact.columns.join(" · ")}</p>
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
