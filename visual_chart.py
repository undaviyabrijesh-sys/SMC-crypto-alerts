"""Render raw OHLCV charts and optional AI-inferred demand/supply review overlays."""
import io
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator
import pandas as pd

PANELS = [
    ("1w", "Weekly", 80),
    ("1d", "Daily", 100),
    ("4h", "4-hour", 100),
    ("1h", "1-hour", 120),
    ("15m", "15-minute", 120),
    ("5m", "5-minute", 100),
]
VALID_TIMEFRAMES = {item[0] for item in PANELS}


def _valid_zone_rows(analysis, key):
    """Return well-formed AI zone bands; this validates output shape, not price structure."""
    zones = analysis.get(key, []) if isinstance(analysis, dict) else []
    if not isinstance(zones, list):
        return []
    valid = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        try:
            low = float(zone["low"])
            high = float(zone["high"])
            quality = int(zone.get("quality", 0))
            timeframe = str(zone["timeframe"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            not math.isfinite(low)
            or not math.isfinite(high)
            or low <= 0
            or low >= high
            or timeframe not in VALID_TIMEFRAMES
            or quality < 1
            or quality > 5
        ):
            continue
        valid.append({
            "low": low,
            "high": high,
            "quality": quality,
            "timeframe": timeframe,
            "evidence": str(zone.get("evidence", "")),
        })
    return sorted(valid, key=lambda item: (-item["quality"], item["low"]))


def _draw_dns_annotations(ax, timeframe, analysis):
    """Draw model-reported bands on their own timeframe panel without changing price scale."""
    original_ylim = ax.get_ylim()
    drawn = 0
    for side, key, color, prefix in (
        ("DEMAND", "demand_zones", "#27c18a", "D"),
        ("SUPPLY", "supply_zones", "#ef6262", "S"),
    ):
        side_drawn = 0
        panel_zones = [
            zone for zone in _valid_zone_rows(analysis, key)
            if zone["timeframe"] == timeframe
        ][:5]
        for zone in panel_zones:
            low, high = zone["low"], zone["high"]
            # Keep the candle panel's original price range; do not let an AI band
            # distort or expand the plotted scale.
            if high < original_ylim[0] or low > original_ylim[1]:
                continue
            ax.axhspan(
                low, high, xmin=0.54, xmax=1.0,
                facecolor=color, edgecolor=color, alpha=0.17,
                linewidth=0.7, zorder=1.1
            )
            midpoint = (low + high) / 2.0
            label = (
                f"{prefix}{side_drawn + 1} {timeframe} Q{zone['quality']} "
                f"{low:,.6g}-{high:,.6g}"
            )
            ax.text(
                0.995, midpoint, label,
                transform=ax.get_yaxis_transform(),
                ha="right", va="center", color="#f4f7fb",
                fontsize=6.2, zorder=4, clip_on=True,
                bbox={
                    "boxstyle": "round,pad=0.16",
                    "facecolor": "#101722",
                    "edgecolor": color,
                    "linewidth": 0.55,
                    "alpha": 0.9,
                },
            )
            drawn += 1
            side_drawn += 1

    selected = analysis.get("selected_entry_zone") if isinstance(analysis, dict) else None
    if isinstance(selected, dict) and selected.get("timeframe") == timeframe:
        try:
            low, high = float(selected["low"]), float(selected["high"])
            if (
                math.isfinite(low) and math.isfinite(high)
                and 0 < low < high
                and high >= original_ylim[0] and low <= original_ylim[1]
            ):
                ax.axhspan(
                    low, high, xmin=0.54, xmax=1.0,
                    facecolor="none", edgecolor="#f5c451",
                    linewidth=1.15, linestyle="--", zorder=1.6
                )
        except (KeyError, TypeError, ValueError, OverflowError):
            pass

    ax.set_ylim(original_ylim)
    return drawn


def render_symbol_chart(symbol, frames, now=None, annotations=None):
    """Return a six-panel chart; optional annotations are AI output rendered for human audit."""
    fig, axes = plt.subplots(
        nrows=len(PANELS), ncols=1, figsize=(17, 17),
        gridspec_kw={"height_ratios": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]},
        constrained_layout=True
    )
    fig.patch.set_facecolor("#101722")

    for ax, (key, label, limit) in zip(axes, PANELS):
        df = frames.get(key)
        ax.set_facecolor("#101722")
        if df is None or df.empty:
            ax.text(0.5, 0.5, f"{label}: no data", color="white",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
            continue
        df = df.tail(limit).copy()
        dates = mdates.date2num(df.index.to_pydatetime())
        interval_days = {
            "1w": 7.0, "1d": 1.0, "4h": 4 / 24,
            "1h": 1 / 24, "15m": 15 / 1440, "5m": 5 / 1440
        }[key]
        candle_width = interval_days * 0.62
        for x, (_, row) in zip(dates, df.iterrows()):
            o, h, low, c = map(float, (row.open, row.high, row.low, row.close))
            candle_color = "#27c18a" if c >= o else "#ef6262"
            ax.vlines(x, low, h, color=candle_color, linewidth=0.9, zorder=2)
            bottom = min(o, c)
            height = max(abs(c - o), max(abs(c), 1.0) * 0.000025)
            ax.add_patch(Rectangle(
                (x - candle_width / 2, bottom), candle_width, height,
                facecolor=candle_color, edgecolor=candle_color,
                linewidth=0.5, zorder=3
            ))

        # Volume is shown on a hidden secondary axis so price scale remains exact.
        vol = df["volume"].fillna(0).astype(float).to_numpy()
        if len(vol) and vol.max() > 0:
            vax = ax.twinx()
            colors = [
                "#27c18a" if float(r.close) >= float(r.open) else "#ef6262"
                for _, r in df.iterrows()
            ]
            vax.bar(dates, vol, width=candle_width, color=colors, alpha=0.15, align="center")
            vax.set_ylim(0, max(vol.max() * 5, 1))
            vax.set_yticks([])
            vax.set_zorder(0)
            ax.set_zorder(1)
            ax.patch.set_visible(False)

        close = float(df["close"].iloc[-1])
        ax.axhline(close, color="#f5c451", linewidth=0.8, linestyle=(0, (4, 3)), alpha=0.75)
        ax.set_xlim(
            dates[0] - candle_width,
            dates[-1] + (dates[-1] - dates[0]) * 0.08 + candle_width * 8
        )
        if annotations is not None:
            _draw_dns_annotations(ax, key, annotations)
        ax.yaxis.tick_right()
        ax.yaxis.set_major_formatter(FuncFormatter(
            lambda value, _: f"{value:,.4f}" if abs(value) < 10 else f"{value:,.2f}"
        ))
        ax.tick_params(axis="y", colors="#d9e2ef", labelsize=8)
        ax.tick_params(axis="x", colors="#a9b5c6", labelsize=7)
        ax.grid(True, axis="y", color="#425066", linewidth=0.45, alpha=0.55)
        ax.grid(True, axis="x", color="#425066", linewidth=0.25, alpha=0.25)
        ax.set_title(
            f"{label}  |  {len(df)} closed candles  |  last close {close:,.6g}  |  "
            f"{df.index[-1]:%Y-%m-%d %H:%M} UTC",
            loc="left", color="#edf2f7", fontsize=9, pad=3
        )
        ax.xaxis.set_major_locator(MaxNLocator(6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M", tz=df.index.tz))

    stamp = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if annotations is None:
        title = "RAW VISUAL MARKET MAP | AI zone inference input | no pre-drawn zones"
    else:
        title = "AI DNS REVIEW OVERLAY | model-reported bands on matching timeframe panels"
    fig.suptitle(
        f"{symbol}  |  {title}  |  {stamp:%Y-%m-%d %H:%M UTC}",
        color="#f4f7fb", fontsize=13, fontweight="bold"
    )
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=125, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()
