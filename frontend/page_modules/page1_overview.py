"""
Page 1: Model Comparison Dashboard

Two-tier view:
  Tier 1 — Model vs Model: aggregated metrics, bar charts, radar overlay
  Tier 2 — Run vs Run: individual run comparison table, detail expanders

When sidebar Model Filter = "All": Tier 1 compares all models
When sidebar Model Filter = specific model: Tier 1 shows single model summary, Tier 2 drills into runs
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
import json

from frontend.data_layer import DataLayer
from frontend.components import (
    kpi_row, comparison_table, radar_chart, efficiency_scatter,
    model_comparison_bars, model_kpi_card,
    COLORS, MODEL_COLORS, model_color,
)


def render(dl: DataLayer, model_filter: str | None = None):
    st.title("Model Comparison Dashboard")

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    df_runs = dl.get_runs_summary(model=model_filter)

    if df_runs.empty:
        st.warning("No completed runs found. Run a backtest first.")
        return

    # Compute derived per-run metrics
    df_runs["return_pct"] = (
        (df_runs["current_nav"] - df_runs["initial_cash"])
        / df_runs["initial_cash"] * 100
    )
    df_runs["return_usd"] = df_runs["current_nav"] - df_runs["initial_cash"]
    df_runs["win_rate"] = np.where(
        df_runs["total_trades"] > 0,
        df_runs["successful_trades"] / df_runs["total_trades"] * 100,
        0,
    )

    # ------------------------------------------------------------------
    # Aggregation: per-model summary
    # ------------------------------------------------------------------
    df_models = _aggregate_by_model(df_runs)
    available_models = df_models["model"].tolist()
    show_model_comparison = len(available_models) > 1

    # ------------------------------------------------------------------
    # TIER 1: Model Comparison
    # ------------------------------------------------------------------
    if show_model_comparison:
        st.subheader("Model vs Model")

        # --- Model KPI cards ---
        _render_model_kpi_cards(df_models)

        # --- Bar chart: side-by-side model metrics ---
        st.plotly_chart(
            model_comparison_bars(df_models, "Model Metrics Comparison"),
            use_container_width=True,
        )

        # --- Radar + Scatter side by side ---
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("Radar Comparison")
            models_data = []
            for _, row in df_models.iterrows():
                models_data.append(_build_radar_from_aggregate(row))
            if models_data:
                st.plotly_chart(radar_chart(models_data), use_container_width=True)

        with col_right:
            st.subheader("Cost vs Return Efficiency")
            st.plotly_chart(efficiency_scatter(df_runs), use_container_width=True)

    else:
        # Single model — show summary header
        _render_single_model_summary(df_runs, df_models)

    st.markdown("---")

    # ------------------------------------------------------------------
    # TIER 2: Run Comparison Table
    # ------------------------------------------------------------------
    if show_model_comparison:
        st.subheader("Run Comparison (Drill-down)")
    else:
        st.subheader("Run Details")

    comparison_table(df_runs)
    st.caption("Click column headers to sort. Green = better, Red = worse.")

    # --- Model aggregate table ---
    if show_model_comparison:
        st.markdown("---")
        st.subheader("Model Aggregate Summary")
        _render_model_aggregate_table(df_models)

    # --- Run detail expanders ---
    st.markdown("---")
    st.subheader("Individual Run Details")

    for _, run in df_runs.iterrows():
        with st.expander(
            f"{run['model']} — {run['start_date']} → {run['end_date']} "
            f"| Return: {run['return_pct']:+.2f}% | "
            f"Trades: {int(run['total_trades'])} | "
            f"Cost: ${run.get('total_cost', 0):,.4f}"
        ):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Model", run["model"])
                st.metric("Period", f"{run['start_date']} → {run['end_date']}")
            with c2:
                st.metric("Decisions", f"{int(run['decisions_made'])}")
                st.metric("Interval", f"{int(run['interval_min'])}min")
                st.metric("Thinking", "ON" if run["thinking_enabled"] else "OFF")
            with c3:
                st.metric("API Cost", f"${run.get('api_cost_total', 0):,.4f}")
                st.metric("Trading Fees", f"${run.get('trading_fees_total', 0):,.4f}")
                st.metric("Total Cost", f"${run.get('total_cost', 0):,.4f}")
            with c4:
                st.metric("Tokens/Dec", f"{run.get('tokens_per_decision', 0):,.0f}")
                st.metric("Cost/Dec", f"${run.get('cost_per_decision', 0):,.6f}")
                st.metric("Ret/$Cost", f"{run.get('return_per_dollar_cost', 0):.2f}x")

            # Show result JSON if available
            try:
                result = json.loads(str(run.get("result", "{}")))
                if result:
                    st.json(result)
            except (json.JSONDecodeError, TypeError):
                pass


# ---------------------------------------------------------------------------
# Helpers: Aggregation
# ---------------------------------------------------------------------------

def _aggregate_by_model(df_runs: pd.DataFrame) -> pd.DataFrame:
    """Aggregate run-level metrics into model-level summary."""
    agg = df_runs.groupby("model").agg(
        run_count=("run_id", "count"),
        avg_return_pct=("return_pct", "mean"),
        total_return_usd=("return_usd", "sum"),
        avg_win_rate=("win_rate", "mean"),
        total_trades=("total_trades", "sum"),
        total_successful=("successful_trades", "sum"),
        total_api_cost=("api_cost_total", "sum"),
        total_cost=("total_cost", "sum"),
        avg_latency_ms=("avg_latency_ms", "mean"),
        avg_tokens_per_decision=("tokens_per_decision", "mean"),
        avg_cost_per_decision=("cost_per_decision", "mean"),
        avg_return_per_dollar=("return_per_dollar_cost", "mean"),
        total_prompt_tokens=("total_prompt_tokens", "sum"),
        total_completion_tokens=("total_completion_tokens", "sum"),
    ).reset_index()

    # Rename for display
    agg = agg.rename(columns={
        "avg_return_pct": "return_pct",
        "avg_win_rate": "win_rate",
        "avg_latency_ms": "avg_latency_ms",
        "avg_tokens_per_decision": "tokens_per_decision",
        "avg_cost_per_decision": "cost_per_decision",
        "avg_return_per_dollar": "return_per_dollar_cost",
    })

    return agg.sort_values("return_pct", ascending=False)


# ---------------------------------------------------------------------------
# Helpers: Rendering sub-sections
# ---------------------------------------------------------------------------

def _render_model_kpi_cards(df_models: pd.DataFrame):
    """Render one KPI card per model."""
    cols = st.columns(len(df_models))
    for i, (_, row) in enumerate(df_models.iterrows()):
        model = row["model"]
        with cols[i]:
            metrics = {
                "return_pct": row["return_pct"],
                "win_rate": row["win_rate"],
                "return_per_dollar_cost": row["return_per_dollar_cost"],
                "avg_latency_ms": row["avg_latency_ms"],
                "run_count": int(row["run_count"]),
            }
            model_kpi_card(model, metrics, model_color(model))


def _render_model_aggregate_table(df_models: pd.DataFrame):
    """Render the model aggregate summary table with styling."""
    display_order = [
        "model", "run_count", "return_pct", "win_rate",
        "return_per_dollar_cost", "total_cost",
        "avg_latency_ms", "tokens_per_decision", "cost_per_decision",
    ]
    cols_avail = [c for c in display_order if c in df_models.columns]
    df_show = df_models[cols_avail].copy()

    rename = {
        "model": "Model",
        "run_count": "Runs",
        "return_pct": "Avg Return %",
        "win_rate": "Avg Win Rate %",
        "return_per_dollar_cost": "Ret / $ Cost",
        "total_cost": "Total Cost",
        "avg_latency_ms": "Avg Latency (ms)",
        "tokens_per_decision": "Tokens / Decision",
        "cost_per_decision": "Cost / Decision",
    }
    df_show = df_show.rename(columns={k: v for k, v in rename.items() if k in df_show.columns})

    from frontend.components import styled_dataframe
    styled_dataframe(
        df_show,
        color_cols=["Avg Return %", "Avg Win Rate %", "Ret / $ Cost"],
        pct_cols=["Avg Return %", "Avg Win Rate %"],
        usd_cols=["Total Cost", "Cost / Decision"],
        height=150 + len(df_show) * 35,
    )


def _render_single_model_summary(df_runs: pd.DataFrame, df_models: pd.DataFrame):
    """Render single-model summary when only one model is in view."""
    if df_models.empty:
        return
    row = df_models.iloc[0]
    model = row["model"]

    st.subheader(f"Model: {model}")

    total_return = df_runs["return_usd"].sum()
    run_count = len(df_runs)
    total_cost = df_runs["total_cost"].sum()
    total_trades = int(df_runs["total_trades"].sum())
    avg_ret_per_cost = df_runs["return_per_dollar_cost"].mean()

    kpi_row([
        {"label": "Runs", "value": run_count},
        {"label": "Total Return", "value": total_return, "suffix": " USD"},
        {"label": "Avg Return %", "value": row["return_pct"], "suffix": "%"},
        {"label": "Win Rate", "value": row["win_rate"] or 0, "suffix": "%"},
        {"label": "Total Cost", "value": total_cost, "suffix": " USD"},
        {"label": "Ret/$Cost", "value": avg_ret_per_cost, "suffix": "x"},
        {"label": "Avg Latency", "value": row["avg_latency_ms"], "suffix": " ms"},
        {"label": "Tokens/Dec", "value": row["tokens_per_decision"], "suffix": ""},
    ], columns=4)


# ---------------------------------------------------------------------------
# Helpers: Radar chart data
# ---------------------------------------------------------------------------

def _build_radar_from_aggregate(model_row: pd.Series) -> dict:
    """Build radar chart data from a model aggregate row.

    Normalizes each metric to [0, 1] range across reasonable max values.
    When only one model is present, max values are based on that model's data.
    When multiple models compete, the best model gets 1.0 on each axis.
    """
    name = model_row.get("model", "Unknown")
    ret = model_row.get("return_pct", 0) or 0
    win = model_row.get("win_rate", 0) or 0
    ret_per_cost = model_row.get("return_per_dollar_cost", 0) or 0
    latency = model_row.get("avg_latency_ms", 1000) or 1000

    return {
        "name": name,
        "return": min(max(ret, 0) / 10.0, 1.0),        # 10% return = full score
        "sharpe": 0.5,                                   # placeholder (no sharpe in aggregate)
        "stability": 0.5,                                # placeholder (no maxdd in aggregate)
        "win_rate": min(max(win, 0) / 100.0, 1.0),      # 100% win rate = full
        "cost_efficiency": min(max(ret_per_cost, 0) / 3.0, 1.0),  # 3x return/$ = full
        "speed": min(1000.0 / max(latency, 1), 1.0),    # 1s latency = full
    }
