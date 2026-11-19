"use client";

import { useState } from "react";

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

const markets = [
  { symbol: "BTCUSD", name: "Bitcoin Perpetual", venue: "Delta Exchange India", state: "Waiting for feed" },
  { symbol: "ETHUSD", name: "Ethereum Perpetual", venue: "Delta Exchange India", state: "Waiting for feed" },
  { symbol: "XAUTUSD", name: "Tether Gold Perpetual", venue: "Delta Exchange India", state: "Waiting for feed" },
  { symbol: "MAJORS", name: "Liquid major perpetuals", venue: "Exchange adapter pending", state: "Not connected" }
];

const strategies = [
  { name: "Trend pullback", detail: "HTF trend · 15m pullback · 5m confirmation" },
  { name: "Breakout / retest", detail: "Range break · retest · 5m confirmation" },
  { name: "Volatility expansion", detail: "ATR expansion · 4h / 1h alignment" },
  { name: "Liquidity sweep reversal", detail: "15m sweep · reclaim · 5m confirmation" },
  { name: "Mean reversion", detail: "1h Bollinger re-entry · balanced regime" },
  { name: "Momentum continuation", detail: "HTF direction · displacement · follow-through" }
];

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
  const currentNav = navigation.find((item) => item.label === active);

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
            <div className="feed-state"><span className="offline-dot" /> DATA FEED NOT CONNECTED</div>
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
                <div><strong>Dashboard foundation is ready</strong><p>Market feeds and the read-only API are not connected yet. Live prices, P&amp;L and scanner results will appear only after verified backend integration.</p></div>
                <span className="notice-code">PHASE 0 / 7</span>
              </div>

              <div className="metric-grid">
                <MetricCard label="Total paper equity" value="—" note="Waiting for paper ledger API" icon="◉" />
                <MetricCard label="Open paper positions" value="—" note="Waiting for lifecycle API" icon="↗" />
                <MetricCard label="Research candidates" value="—" note="Waiting for scanner API" icon="⌕" />
                <MetricCard label="Approved strategies" value="0" note="No strategy is approved for execution" icon="◇" />
              </div>

              <div className="content-grid">
                <section className="panel market-panel">
                  <div className="panel-heading"><div><h2>Market watch</h2><p>Connected instruments and source status</p></div><button className="text-button" onClick={() => setActive("Live Markets")}>View markets <span>→</span></button></div>
                  <div className="market-table">
                    <div className="table-head"><span>INSTRUMENT</span><span>VENUE</span><span>DATA STATUS</span></div>
                    {markets.map((market) => <div className="market-row" key={market.symbol}><div className="instrument"><div className="coin-icon">{market.symbol === "BTCUSD" ? "₿" : market.symbol === "ETHUSD" ? "◆" : market.symbol === "XAUTUSD" ? "Au" : "✣"}</div><div><strong>{market.symbol}</strong><small>{market.name}</small></div></div><span className="venue">{market.venue}</span><StatusPill>{market.state}</StatusPill></div>)}
                  </div>
                  <div className="panel-foot"><span className="tiny-dot" /> No synthetic or cached prices are being displayed.</div>
                </section>

                <section className="panel system-panel">
                  <div className="panel-heading"><div><h2>System status</h2><p>Core research services</p></div><span className="system-icon">⌘</span></div>
                  <div className="system-list">
                    <div><span>Python research engine</span><StatusPill tone="amber">Integration pending</StatusPill></div>
                    <div><span>Historical data store</span><StatusPill>Not queried</StatusPill></div>
                    <div><span>Backtest service</span><StatusPill>Not connected</StatusPill></div>
                    <div><span>Paper lifecycle</span><StatusPill>Not connected</StatusPill></div>
                    <div><span>Telegram / Discord</span><StatusPill>Code present</StatusPill></div>
                  </div>
                  <div className="system-note">Existing Python modules remain the source of truth. The dashboard will consume them through a read-only API.</div>
                </section>
              </div>

              <div className="content-grid lower-grid">
                <section className="panel chart-panel">
                  <div className="panel-heading"><div><h2>Market structure</h2><p>Chart workspace will activate after verified candle-feed integration</p></div><StatusPill>AWAITING DATA</StatusPill></div>
                  <div className="chart-placeholder"><div className="chart-axis"><span>—</span><span>—</span><span>—</span><span>—</span></div><div className="chart-grid"><div className="chart-message"><span className="chart-symbol">⌁</span><strong>No market data loaded</strong><small>Connect the read-only market API to render candles and indicators.</small></div></div><div className="chart-bottom"><span>SYMBOL: —</span><span>TIMEFRAME: —</span><span>LAST UPDATE: —</span></div></div>
                </section>

                <section className="panel strategy-panel">
                  <div className="panel-heading"><div><h2>Strategy lanes</h2><p>Current deterministic research families</p></div><button className="text-button" onClick={() => setActive("Strategy Research")}>Research <span>→</span></button></div>
                  <div className="strategy-list">
                    {strategies.map((strategy, index) => <div className="strategy-row" key={strategy.name}><div className="strategy-index">0{index + 1}</div><div className="strategy-copy"><strong>{strategy.name}</strong><small>{strategy.detail}</small></div><StatusPill>SHADOW</StatusPill></div>)}
                  </div>
                </section>
              </div>
              <footer className="page-footer"><span>SALTY QUANT TERMINAL <b>·</b> BUILD 0.1.0</span><span>RESEARCH FIRST. VERIFY EVERYTHING.</span></footer>
            </>
          ) : (
            <div className="module-empty">
              <div className="module-icon">{currentNav?.icon ?? "⚙"}</div>
              <div className="eyebrow">MODULE FOUNDATION</div>
              <h1>{active}</h1>
              <p>This module is mapped in the product architecture. It will be connected to the existing Python research and paper engines in the next build phases.</p>
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
