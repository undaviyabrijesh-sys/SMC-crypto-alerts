"""Render clean, unannotated OHLCV chart panels for vision-based market analysis."""
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
import pandas as pd

PANELS = [
    ("1d", "Daily", 100),
    ("4h", "4-hour", 100),
    ("1h", "1-hour", 120),
    ("15m", "15-minute", 120),
    ("5m", "5-minute", 100),
]


def render_symbol_chart(symbol, frames, now=None):
    """Return one PNG with five aligned-timeframe candlestick + volume panels."""
    fig, axes = plt.subplots(
        nrows=len(PANELS), ncols=1, figsize=(17, 15),
        gridspec_kw={"height_ratios": [1.0, 1.0, 1.0, 1.0, 1.0]},
        constrained_layout=True
    )
    fig.patch.set_facecolor("#101722")
    last_price = None
    last_time = None

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
        interval_days = {"1d": 1.0, "4h": 4 / 24, "1h": 1 / 24, "15m": 15 / 1440, "5m": 5 / 1440}[key]
        candle_width = interval_days * 0.62
        for x, (_, row) in zip(dates, df.iterrows()):
            o, h, l, c = map(float, (row.open, row.high, row.low, row.close))
            up = c >= o
            candle_color = "#27c18a" if up else "#ef6262"
            ax.vlines(x, l, h, color=candle_color, linewidth=0.9, zorder=2)
            bottom = min(o, c)
            height = max(abs(c - o), max(abs(c), 1.0) * 0.000025)
            ax.add_patch(Rectangle((x - candle_width / 2, bottom), candle_width, height,
                                   facecolor=candle_color, edgecolor=candle_color, linewidth=0.5, zorder=3))
        # Volume is shown on a hidden secondary axis so price scale remains exact.
        vol = df["volume"].fillna(0).astype(float).to_numpy()
        if len(vol) and vol.max() > 0:
            vax = ax.twinx()
            colors = ["#27c18a" if float(r.close) >= float(r.open) else "#ef6262"
                      for _, r in df.iterrows()]
            vax.bar(dates, vol, width=candle_width, color=colors, alpha=0.15, align="center")
            vax.set_ylim(0, max(vol.max() * 5, 1))
            vax.set_yticks([])
            vax.set_zorder(0)
            ax.set_zorder(1)
            ax.patch.set_visible(False)

        close = float(df["close"].iloc[-1])
        last_price = close
        last_time = df.index[-1]
        ax.axhline(close, color="#f5c451", linewidth=0.8, linestyle=(0, (4, 3)), alpha=0.75)
        ax.set_xlim(dates[0] - candle_width, dates[-1] + (dates[-1] - dates[0]) * 0.08 + candle_width * 8)
        ax.yaxis.tick_right()
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.4f}" if abs(value) < 10 else f"{value:,.2f}"))
        ax.tick_params(axis="y", colors="#d9e2ef", labelsize=8)
        ax.tick_params(axis="x", colors="#a9b5c6", labelsize=7)
        ax.grid(True, axis="y", color="#425066", linewidth=0.45, alpha=0.55)
        ax.grid(True, axis="x", color="#425066", linewidth=0.25, alpha=0.25)
        ax.set_title(
            f"{label}  |  {len(df)} closed candles  |  last close {close:,.6g}  |  {df.index[-1]:%Y-%m-%d %H:%M} UTC",
            loc="left", color="#edf2f7", fontsize=9, pad=3
        )
        ax.xaxis.set_major_locator(mdates.MaxNLocator(6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M", tz=df.index.tz))

    stamp = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    fig.suptitle(
        f"{symbol}  |  VISUAL MARKET MAP  |  {stamp:%Y-%m-%d %H:%M UTC}  |  No algorithmic zones are pre-drawn",
        color="#f4f7fb", fontsize=13, fontweight="bold"
    )
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=125, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()
