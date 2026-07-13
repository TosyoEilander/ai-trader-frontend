"""
Reusable UI components for the AI-Trader Benchmark frontend.

KPI cards, styled metric displays, and helper functions used across all pages.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json


# ---------------------------------------------------------------------------
# Color palette — consistent across all pages
# ---------------------------------------------------------------------------

# ---- Morandi Color Palette ----
# Muted, low-saturation tones with gray undertones for a polished, professional look.
COLORS = {
    "primary":    "#7b8fa1",   # dusty blue-gray
    "secondary":  "#a8b8a0",   # sage green
    "success":    "#8aa38a",   # muted sage
    "danger":     "#b8907a",   # dusty terracotta
    "warning":    "#c4a882",   # warm taupe
    "info":       "#9aa5ae",   # light slate
    "dark":       "#4a5055",   # charcoal
    "light":      "#f3f0ec",   # warm off-white
    "bg-card":    "#faf8f5",   # cream
    "us":         "#7b8fa1",   # dusty blue
    "hk":         "#8aa38a",   # muted sage
    "cn":         "#b8907a",   # dusty rose
    "crypto":     "#c4a882",   # warm taupe
    "green_regime":  "#8aa38a",
    "yellow_regime": "#c4a882",
    "red_regime":    "#b8907a",
}

MODEL_COLORS = {
    "deepseek-v4-pro": "#7b8fa1",
    "deepseek-chat":   "#8aa38a",
    "mimo-v2.5-pro":   "#b8907a",
    "qwen-max":        "#9a8fb8",
    "qwen-plus":       "#a09090",
    "claude-opus":     "#c49b8a",
    "claude-sonnet":   "#a8a090",
    "gpt-4o":          "#8a9ea8",
    "gpt-4.1":         "#989898",
}

# Chart template — warm, clean, no grid clutter
CHART_TEMPLATE = {
    "layout": {
        "plot_bgcolor": "#faf8f5",
        "paper_bgcolor": "#faf8f5",
        "font": {"color": "#4a5055", "family": "Inter, sans-serif"},
        "title": {"font": {"size": 16, "color": "#4a5055", "family": "Inter, sans-serif"}},
        "xaxis": {"gridcolor": "#e8e4dd", "linecolor": "#d5cfc7", "title": {"font": {"color": "#4a5055"}}},
        "yaxis": {"gridcolor": "#e8e4dd", "linecolor": "#d5cfc7", "title": {"font": {"color": "#4a5055"}}},
    }
}


def model_color(model_name: str) -> str:
    """Get consistent color for a model name."""
    for key, color in MODEL_COLORS.items():
        if key in model_name:
            return color
    return COLORS["primary"]


# ---------------------------------------------------------------------------
# KPI Cards
# ---------------------------------------------------------------------------

def kpi_card(label: str, value, suffix: str = "", delta: float | None = None,
             delta_label: str = "", help_text: str = ""):
    """Render a single KPI metric card."""
    if isinstance(value, (int, float)):
        if abs(value) >= 1_000_000:
            display = f"{value:,.1f}M" if value >= 1_000_000 else f"{value:,.0f}"
        elif abs(value) >= 1_000:
            display = f"{value:,.0f}"
        elif abs(value) < 1 and value != 0:
            display = f"{value:.4f}"
        else:
            display = f"{value:,.2f}"
        display += suffix
    else:
        display = str(value)

    delta_str = None
    if delta is not None:
        delta_str = f"{delta:+.2f}{suffix}"

    st.metric(label=label, value=display, delta=delta_str, help=help_text)


def kpi_row(metrics: list[dict], columns: int = 5):
    """Render a row of KPI cards.

    Each metric dict: {label, value, suffix?, delta?, delta_label?, help?}
    """
    cols = st.columns(columns)
    for i, m in enumerate(metrics):
        with cols[i % columns]:
            kpi_card(
                label=m["label"],
                value=m["value"],
                suffix=m.get("suffix", ""),
                delta=m.get("delta"),
                help_text=m.get("help", ""),
            )


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def fmt_pct(v: float) -> str:
    """Format as percentage."""
    if pd.isna(v):
        return "-"
    return f"{v:+.2f}%"

def fmt_usd(v: float) -> str:
    """Format as USD."""
    if pd.isna(v):
        return "-"
    return f"${v:,.2f}"

def fmt_int(v) -> str:
    """Format as integer."""
    if pd.isna(v):
        return "-"
    return f"{int(v):,}"

def fmt_ms(v: float) -> str:
    """Format as milliseconds."""
    if pd.isna(v):
        return "-"
    return f"{v:,.0f}ms"

def fmt_ratio(v: float) -> str:
    """Format as ratio."""
    if pd.isna(v):
        return "-"
    return f"{v:.2f}x"


# ---------------------------------------------------------------------------
# Color-gradient table helper
# ---------------------------------------------------------------------------

def styled_dataframe(df: pd.DataFrame,
                     color_cols: list[str] | None = None,
                     pct_cols: list[str] | None = None,
                     usd_cols: list[str] | None = None,
                     height: int = 400) -> None:
    """Display a styled dataframe with automatic formatting and color gradients.

    Args:
        df: DataFrame to display
        color_cols: Columns to apply green-red color gradient
        pct_cols: Columns to format as percentages
        usd_cols: Columns to format as USD
        height: Table height in pixels
    """
    if df.empty:
        st.info("No data to display.")
        return

    styled = df.style

    # Apply percentage formatting
    fmt_dict = {}
    for col in (pct_cols or []):
        if col in df.columns:
            fmt_dict[col] = "{:+.2f}%"
    for col in (usd_cols or []):
        if col in df.columns:
            fmt_dict[col] = "${:,.2f}"

    if fmt_dict:
        styled = styled.format(fmt_dict, na_rep="-")

    # Apply color gradients
    if color_cols:
        for col in color_cols:
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors="coerce")
                if vals.notna().any():
                    styled = styled.background_gradient(
                        subset=[col],
                        cmap="RdYlGn",
                        vmin=vals.min(),
                        vmax=vals.max(),
                    )

    st.dataframe(styled, use_container_width=True, height=height)


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def comparison_table(df: pd.DataFrame) -> None:
    """Render the model comparison table with styling."""
    display_cols = {
        "model": "Model",
        "start_date": "Start",
        "end_date": "End",
        "interval_min": "Interval(m)",
        "current_nav": "Final NAV",
        "return_pct": "Return%",
        "total_trades": "Trades",
        "win_rate": "WinRate%",
        "api_cost_total": "API Cost",
        "trading_fees_total": "Fees",
        "total_cost": "Total Cost",
        "return_per_dollar_cost": "Return/$Cost",
        "tokens_per_decision": "Tokens/Dec",
        "cost_per_decision": "Cost/Dec",
        "avg_latency_ms": "Avg Latency",
    }

    df_display = df.rename(columns={
        k: v for k, v in display_cols.items() if k in df.columns
    })

    cols_to_show = [v for k, v in display_cols.items() if k in df.columns]

    styled_dataframe(
        df_display[cols_to_show],
        color_cols=[
            "Return%", "WinRate%", "Return/$Cost", "Final NAV",
        ],
        pct_cols=["Return%", "WinRate%"],
        usd_cols=["API Cost", "Fees", "Total Cost", "Final NAV"],
        height=300,
    )


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def nav_chart(df_nav: pd.DataFrame, df_trades: pd.DataFrame | None = None,
              title: str = "Portfolio NAV") -> go.Figure:
    """Build interactive NAV chart with benchmark, index, and trade markers."""
    fig = go.Figure()

    # Portfolio NAV
    fig.add_trace(go.Scatter(
        x=df_nav["timestamp"], y=df_nav["nav"],
        mode="lines", name="Portfolio NAV",
        line=dict(color=COLORS["primary"], width=2.5),
        hovertemplate="%{x}<br>NAV: $%{y:,.2f}<extra></extra>",
    ))

    # Benchmark NAV
    if "benchmark_nav" in df_nav.columns and df_nav["benchmark_nav"].gt(0).any():
        fig.add_trace(go.Scatter(
            x=df_nav["timestamp"], y=df_nav["benchmark_nav"],
            mode="lines", name="Benchmark (EW)",
            line=dict(color=COLORS["success"], width=1.5, dash="dash"),
            hovertemplate="%{x}<br>Benchmark: $%{y:,.2f}<extra></extra>",
        ))

    # Index NAV
    if "index_nav" in df_nav.columns and df_nav["index_nav"].gt(0).any():
        fig.add_trace(go.Scatter(
            x=df_nav["timestamp"], y=df_nav["index_nav"],
            mode="lines", name="Index",
            line=dict(color=COLORS["dark"], width=1, dash="dot"),
            hovertemplate="%{x}<br>Index: $%{y:,.2f}<extra></extra>",
        ))

    # Trade markers
    if df_trades is not None and not df_trades.empty:
        buys = df_trades[df_trades["side"] == "buy"]
        sells = df_trades[df_trades["side"] == "sell"]

        # Find corresponding NAV values for trade markers
        if not buys.empty:
            buy_navs = []
            for _, t in buys.iterrows():
                ts = t["timestamp"]
                row = df_nav[df_nav["timestamp"] <= ts]
                if not row.empty:
                    buy_navs.append(row.iloc[-1]["nav"])
                else:
                    buy_navs.append(None)
            fig.add_trace(go.Scatter(
                x=buys["timestamp"], y=buy_navs,
                mode="markers", name="BUY",
                marker=dict(color=COLORS["success"], symbol="triangle-up", size=10,
                           line=dict(color="white", width=1)),
                hovertemplate="%{x}<br>BUY %{text}<extra></extra>",
                text=[f"{s}" for s in buys["symbol"]],
            ))

        if not sells.empty:
            sell_navs = []
            for _, t in sells.iterrows():
                ts = t["timestamp"]
                row = df_nav[df_nav["timestamp"] <= ts]
                if not row.empty:
                    sell_navs.append(row.iloc[-1]["nav"])
                else:
                    sell_navs.append(None)
            fig.add_trace(go.Scatter(
                x=sells["timestamp"], y=sell_navs,
                mode="markers", name="SELL",
                marker=dict(color=COLORS["danger"], symbol="triangle-down", size=10,
                           line=dict(color="white", width=1)),
                hovertemplate="%{x}<br>SELL %{text}<extra></extra>",
                text=[f"{s}" for s in sells["symbol"]],
            ))

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="NAV (USD)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
        margin=dict(l=20, r=20, t=50, b=40),
        template="plotly_white",
    )
    fig.update_xaxes(rangeslider_visible=True)
    return fig


def drawdown_chart(df_nav: pd.DataFrame, title: str = "Drawdown") -> go.Figure:
    """Build drawdown chart as filled area."""
    nav = df_nav["nav"].values
    peak = nav[0]
    dd = []
    for v in nav:
        if v > peak:
            peak = v
        dd.append((v - peak) / peak * 100)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_nav["timestamp"], y=dd,
        mode="lines", name="Drawdown",
        fill="tozeroy",
        fillcolor="rgba(214, 39, 40, 0.2)",
        line=dict(color=COLORS["danger"], width=1),
        hovertemplate="%{x}<br>Drawdown: %{y:.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color="gray", width=0.5, dash="dash"))

    max_dd_idx = min(range(len(dd)), key=lambda i: dd[i])
    fig.add_annotation(
        x=df_nav.iloc[max_dd_idx]["timestamp"],
        y=dd[max_dd_idx],
        text=f"Max DD: {dd[max_dd_idx]:.2f}%",
        showarrow=True,
        arrowhead=1,
        font=dict(color=COLORS["danger"], size=11),
    )

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Drawdown (%)",
        height=250,
        margin=dict(l=20, r=20, t=50, b=40),
        template="plotly_white",
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig


def position_timeline(df_trades: pd.DataFrame, title: str = "Position Timeline") -> go.Figure:
    """Build a Gantt-style position timeline."""
    if "side" not in df_trades.columns or df_trades.empty:
        fig = go.Figure()
        fig.add_annotation(text="No trade data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=200, template="plotly_white")
        return fig

    buys = df_trades[df_trades["side"] == "buy"].copy()
    sells = df_trades[df_trades["side"] == "sell"].copy()

    positions = []
    for _, sell in sells.iterrows():
        sym = sell["symbol"]
        market = sell.get("market", "")
        sell_ts = sell["timestamp"]
        matching_buys = buys[
            (buys["symbol"] == sym) &
            (buys["timestamp"] < sell_ts)
        ]
        if not matching_buys.empty:
            buy = matching_buys.iloc[-1]
            pnl_pct = sell.get("realized_pnl_pct", 0) or 0
            pnl = sell.get("realized_pnl", 0) or 0
            positions.append({
                "symbol": f"{sym} ({market})",
                "buy_time": buy["timestamp"],
                "sell_time": sell["timestamp"],
                "pnl_pct": pnl_pct,
                "pnl": pnl,
                "market": market,
            })

    if not positions:
        fig = go.Figure()
        fig.add_annotation(text="No completed trades (buy→sell pairs) found.",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=200, template="plotly_white")
        return fig

    df_pos = pd.DataFrame(positions)
    df_pos["buy_time"] = pd.to_datetime(df_pos["buy_time"])
    df_pos["sell_time"] = pd.to_datetime(df_pos["sell_time"])
    df_pos = df_pos.sort_values("buy_time")

    fig = go.Figure()
    market_color_map = {"US": COLORS["us"], "HK": COLORS["hk"],
                        "CN": COLORS["cn"], "CRYPTO": COLORS["crypto"]}

    for i, (_, pos) in enumerate(df_pos.iterrows()):
        pnl_color = COLORS["success"] if pos["pnl_pct"] > 0 else COLORS["danger"]
        edge_color = market_color_map.get(pos["market"], COLORS["primary"])

        fig.add_trace(go.Bar(
            y=[pos["symbol"]],
            x=[(pos["sell_time"] - pos["buy_time"]).total_seconds() / 3600],  # hours
            base=pos["buy_time"],
            orientation="h",
            marker=dict(
                color=pnl_color,
                opacity=0.7,
                line=dict(color=edge_color, width=2),
            ),
            hovertemplate=(
                f"<b>{pos['symbol']}</b><br>"
                f"Buy: %{{base}}<br>"
                f"Sell: {pos['sell_time']}<br>"
                f"P&L: ${pos['pnl']:,.2f} ({pos['pnl_pct']:+.2f}%)<br>"
                f"<extra></extra>"
            ),
            showlegend=False,
            name="",
        ))

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        height=max(200, len(df_pos) * 30),
        margin=dict(l=20, r=20, t=50, b=40),
        template="plotly_white",
        barmode="overlay",
        bargap=0.3,
    )
    fig.update_xaxes(type="date")
    return fig


def radar_chart(models_data: list[dict], title: str = "Model Comparison") -> go.Figure:
    """Build a radar/spider chart for multi-model comparison.

    Each dict: {name, return, sharpe, stability, win_rate, cost_efficiency, speed}
    """
    categories = ["Return", "Sharpe", "Stability<br>(1/MaxDD)", "Win Rate",
                  "Cost Efficiency<br>(Ret/$Cost)", "Speed<br>(1/Latency)"]

    fig = go.Figure()

    for m in models_data:
        fig.add_trace(go.Scatterpolar(
            r=[m.get("return", 0), m.get("sharpe", 0),
               m.get("stability", 0), m.get("win_rate", 0),
               m.get("cost_efficiency", 0), m.get("speed", 0)],
            theta=categories,
            fill="toself",
            name=m["name"],
            opacity=0.3,
            line=dict(color=model_color(m["name"]), width=2),
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1.0])),
        title=title,
        height=400,
        template="plotly_white",
    )
    return fig


def efficiency_scatter(df_runs: pd.DataFrame, title: str = "Cost vs Return") -> go.Figure:
    """Build cost vs return scatter plot."""
    if df_runs.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig

    # Compute return from current_nav - initial_cash
    if "current_nav" in df_runs.columns and "initial_cash" in df_runs.columns:
        df_runs = df_runs.copy()
        df_runs["return_pct"] = (
            (df_runs["current_nav"] - df_runs["initial_cash"])
            / df_runs["initial_cash"] * 100
        )

    fig = px.scatter(
        df_runs,
        x="total_cost",
        y="return_pct" if "return_pct" in df_runs.columns else "current_nav",
        size="total_trades",
        color="model",
        color_discrete_map=MODEL_COLORS,
        hover_name="run_id",
        hover_data={
            "start_date": True,
            "end_date": True,
            "total_cost": ":.2f",
            "decisions_made": True,
        },
        title=title,
        labels={
            "total_cost": "Total Cost (USD)",
            "return_pct": "Total Return (%)",
            "total_trades": "Trade Count",
        },
    )

    # Add break-even line
    max_cost = df_runs["total_cost"].max() or 1
    fig.add_trace(go.Scatter(
        x=[0, max_cost],
        y=[0, 0],
        mode="lines",
        line=dict(color="gray", dash="dash", width=1),
        name="Break-even",
        showlegend=True,
    ))

    # Quadrant lines
    median_cost = df_runs["total_cost"].median()
    fig.add_vline(x=median_cost, line=dict(color="gray", dash="dot", width=0.5),
                  annotation_text="Median Cost")
    fig.add_hline(y=0, line=dict(color="gray", dash="dot", width=0.5))

    fig.update_layout(
        height=400,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def pnl_waterfall(df_trades: pd.DataFrame, title: str = "Cumulative P&L") -> go.Figure:
    """Build a cumulative P&L waterfall/step chart."""
    sells = df_trades[(df_trades["side"] == "sell") & (df_trades["success"] == 1)]

    if sells.empty:
        fig = go.Figure()
        fig.add_annotation(text="No completed trades", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=250, template="plotly_white")
        return fig

    sells = sells.sort_values("timestamp")
    cumsum = sells["realized_pnl"].cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sells["timestamp"], y=cumsum,
        mode="lines+markers",
        name="Cumulative P&L",
        line=dict(color=COLORS["primary"], width=2, shape="hv"),
        marker=dict(
            size=6,
            color=[COLORS["success"] if v > 0 else COLORS["danger"] for v in sells["realized_pnl"]],
        ),
        hovertemplate="%{x}<br>Cum. P&L: $%{y:,.2f}<br>Trade: %{text}<extra></extra>",
        text=[f"{s['symbol']} {s['realized_pnl']:+,.2f}" for _, s in sells.iterrows()],
    ))
    fig.add_hline(y=0, line=dict(color="gray", width=0.5, dash="dash"))

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Cumulative P&L (USD)",
        height=300,
        template="plotly_white",
    )
    return fig


def market_exposure_chart(df_nav: pd.DataFrame) -> go.Figure:
    """Build stacked area chart of market exposure over time."""
    fig = go.Figure()

    # Parse market_exposure JSON
    markets = ["US", "HK", "CN", "CRYPTO"]
    exposure_data = {m: [] for m in markets}
    timestamps = []

    for _, row in df_nav.iterrows():
        ts = row["timestamp"]
        timestamps.append(ts)
        try:
            exp = json.loads(row["market_exposure"]) if row["market_exposure"] else {}
        except (json.JSONDecodeError, TypeError):
            exp = {}

        for m in markets:
            exposure_data[m].append(exp.get(m, 0) * 100)  # convert to %

    for m in markets:
        market_name = {"US": "US", "HK": "HK", "CN": "CN", "CRYPTO": "Crypto"}
        fig.add_trace(go.Scatter(
            x=timestamps, y=exposure_data[m],
            mode="lines", name=market_name.get(m, m),
            stackgroup="one",
            line=dict(width=0.5, color=COLORS.get(m.lower(), COLORS["primary"])),
            hovertemplate="%{x}<br>" + market_name.get(m, m) + ": %{y:.1f}%<extra></extra>",
        ))

    fig.add_hline(y=50, line=dict(color=COLORS["danger"], dash="dash", width=1.5),
                  annotation_text="50% Limit")

    fig.update_layout(
        title="Market Exposure Over Time",
        xaxis_title="Time",
        yaxis_title="Exposure (%)",
        height=300,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def regime_bar_chart(df_regime: pd.DataFrame) -> go.Figure:
    """Build grouped bar chart of decisions by market regime."""
    if df_regime.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig

    fig = go.Figure()
    regimes = df_regime["market_regime"].tolist()

    fig.add_trace(go.Bar(
        name="Decision Count",
        x=regimes, y=df_regime["decision_count"],
        marker_color=[COLORS.get(f"{r.lower()}_regime", COLORS["primary"]) for r in regimes],
        text=df_regime["decision_count"],
        textposition="auto",
    ))

    fig.update_layout(
        title="Decisions by Market Regime",
        xaxis_title="Market Regime",
        yaxis_title="Count",
        height=300,
        template="plotly_white",
    )
    return fig


def tool_usage_bar(df_tool: pd.DataFrame) -> go.Figure:
    """Build horizontal bar chart of tool usage."""
    if df_tool.empty:
        fig = go.Figure()
        fig.add_annotation(text="No tool calls", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig

    df_sorted = df_tool.sort_values("call_count")
    fig = go.Figure(go.Bar(
        x=df_sorted["call_count"],
        y=df_sorted["tool_name"],
        orientation="h",
        marker=dict(color=COLORS["primary"], opacity=0.8),
        text=df_sorted["call_count"],
        textposition="outside",
        hovertemplate="%{y}: %{x} calls<br>Avg latency: %{customdata:.1f}ms<extra></extra>",
        customdata=df_sorted["avg_latency_ms"],
    ))
    fig.update_layout(
        title="Tool Usage Frequency",
        xaxis_title="Call Count",
        height=max(200, len(df_sorted) * 30),
        template="plotly_white",
    )
    return fig


def latency_violin(df_calls: pd.DataFrame, group_col: str = "round_num",
                   value_col: str = "latency_ms") -> go.Figure:
    """Build violin plot for latency distribution."""
    if df_calls.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig

    fig = go.Figure()
    groups = sorted(df_calls[group_col].dropna().unique())
    for grp in groups:
        vals = df_calls[df_calls[group_col] == grp][value_col].dropna()
        fig.add_trace(go.Violin(
            y=vals,
            name=f"Round {int(grp)}",
            box_visible=True,
            meanline_visible=True,
            line_color=COLORS["primary"],
        ))

    fig.update_layout(
        title="Latency Distribution by Round",
        yaxis_title="Latency (ms)",
        height=350,
        template="plotly_white",
    )
    return fig


def model_comparison_bars(df_agg: pd.DataFrame, title: str = "Model Comparison") -> go.Figure:
    """Build a grouped bar chart comparing models across key metrics.

    df_agg should have columns: model, return_pct, win_rate, return_per_dollar_cost,
    avg_latency_ms, tokens_per_decision
    """
    metrics = [
        {"col": "return_pct", "label": "Return %", "fmt": "+.2f"},
        {"col": "win_rate", "label": "Win Rate %", "fmt": ".0f"},
        {"col": "return_per_dollar_cost", "label": "Ret / $ Cost", "fmt": ".2f"},
        {"col": "tokens_per_decision", "label": "Tokens/Dec", "fmt": ",.0f"},
    ]

    fig = make_subplots(
        rows=1, cols=len(metrics),
        subplot_titles=[m["label"] for m in metrics],
        shared_yaxes=False,
    )

    for i, metric in enumerate(metrics):
        col = metric["col"]
        if col not in df_agg.columns:
            continue
        vals = df_agg[col].values
        models = df_agg["model"].values
        colors = [model_color(m) for m in models]
        texts = [f"{v:{metric['fmt']}}" for v in vals]

        fig.add_trace(
            go.Bar(
                x=models, y=vals,
                text=texts, textposition="outside",
                marker_color=colors,
                name=metric["label"],
                showlegend=False,
                hovertemplate=f"%{{x}}<br>{metric['label']}: %{{y:{metric['fmt']}}}<extra></extra>",
            ),
            row=1, col=i + 1,
        )

    fig.update_layout(
        title=title,
        height=300,
        template="plotly_white",
        margin=dict(l=20, r=20, t=50, b=60),
    )
    return fig


def inject_morandi_css() -> None:
    """Inject global CSS for Morandi-themed Streamlit styling."""
    st.markdown("""
    <style>
    /* ---- Streamlit overrides ---- */
    .stApp { background: #f3f0ec; }

    /* Section headers */
    h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        color: #4a5055 !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em;
    }
    h1 { font-size: 1.8rem !important; }
    h2 { font-size: 1.35rem !important; border-bottom: 2px solid #e8e4dd; padding-bottom: 8px; }
    h3 { font-size: 1.1rem !important; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #faf8f5;
        border: 1px solid #e8e4dd;
        border-radius: 14px;
        padding: 16px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
    }
    [data-testid="stMetric"] label {
        font-weight: 700 !important;
        color: #4a5055 !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricDelta"] {
        font-weight: 600 !important;
    }

    /* DataFrames */
    [data-testid="stDataFrame"] {
        border: 1px solid #e8e4dd !important;
        border-radius: 12px !important;
        overflow: hidden;
    }

    /* Expanders */
    [data-testid="stExpander"] {
        background: #faf8f5 !important;
        border: 1px solid #e8e4dd !important;
        border-radius: 12px !important;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #ede8e1;
    }

    /* Select boxes */
    .stSelectbox > div > div {
        border-color: #d5cfc7 !important;
    }
    </style>
    """, unsafe_allow_html=True)


def model_kpi_card(model_name: str, metrics: dict, color: str) -> None:
    """Render a compact model KPI card with Morandi styling."""
    ret = metrics.get("return_pct", 0) or 0
    ret_color = COLORS["success"] if ret >= 0 else COLORS["danger"]
    win_rate = metrics.get("win_rate", 0) or 0
    cost_eff = metrics.get("return_per_dollar_cost", 0) or 0
    avg_lat = metrics.get("avg_latency_ms", 0) or 0
    runs = int(metrics.get("run_count", 0) or 0)

    st.markdown(
        f"<div style='background:#faf8f5; border:2px solid {color}; border-radius:14px; "
        f"padding:18px 16px; margin:6px 0; text-align:center; box-shadow:0 2px 10px rgba(0,0,0,0.04);'>"
        f"<div style='font-size:0.85rem; font-weight:700; color:{color}; margin-bottom:6px; "
        f"letter-spacing:0.02em;'>{model_name}</div>"
        f"<div style='font-size:26px; font-weight:800; color:{ret_color}; margin:6px 0;'>"
        f"{ret:+.2f}%</div>"
        f"<div style='font-size:11px; color:#8a8782; font-weight:600; letter-spacing:0.04em;'>RETURN</div>"
        f"<table style='width:100%; font-size:12px; color:#6b6b6b; margin-top:10px;'>"
        f"<tr><td style='padding:2px 0;'>Win Rate</td>"
        f"<td style='text-align:right; font-weight:600; color:#4a5055;'>{win_rate:.0f}%</td></tr>"
        f"<tr><td style='padding:2px 0;'>Ret / $Cost</td>"
        f"<td style='text-align:right; font-weight:600; color:#4a5055;'>{cost_eff:.2f}x</td></tr>"
        f"<tr><td style='padding:2px 0;'>Avg Latency</td>"
        f"<td style='text-align:right; font-weight:600; color:#4a5055;'>{avg_lat:,.0f}ms</td></tr>"
        f"<tr><td style='padding:2px 0;'>Runs</td>"
        f"<td style='text-align:right; font-weight:600; color:#4a5055;'>{runs}</td></tr>"
        f"</table>"
        f"</div>",
        unsafe_allow_html=True,
    )
