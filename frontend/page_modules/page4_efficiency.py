"""
Page 4: Cost & Efficiency Analytics
Which model/config gives the best bang for the buck?
Cost composition, efficiency leaderboard, cost vs return, token efficiency, latency.
"""

from __future__ import annotations
import json

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from frontend.data_layer import DataLayer
from frontend.components import (
    kpi_row, styled_dataframe, efficiency_scatter, COLORS, MODEL_COLORS,
    fmt_usd, fmt_pct, model_color,
)


def render(dl: DataLayer, model_filter: str | None = None):
    st.title("Cost & Efficiency Analytics")

    # ------------------------------------------------------------------
    # Load all runs
    # ------------------------------------------------------------------
    df_runs = dl.get_runs_summary(model=model_filter)

    if df_runs.empty:
        st.warning("No completed runs found.")
        return

    # Compute metrics
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
    # Section A: Cost Composition (per run)
    # ------------------------------------------------------------------
    st.subheader("Cost Composition by Run")

    if len(df_runs) > 0:
        fig = go.Figure()
        runs_display = df_runs.head(10)  # Show top 10

        fig.add_trace(go.Bar(
            y=[f"{r['model'][:20]} | {r['start_date']}" for _, r in runs_display.iterrows()],
            x=runs_display["api_cost_total"],
            name="API Cost",
            orientation="h",
            marker=dict(color=COLORS["primary"]),
            text=[f"${v:,.2f}" for v in runs_display["api_cost_total"]],
            textposition="inside",
        ))
        fig.add_trace(go.Bar(
            y=[f"{r['model'][:20]} | {r['start_date']}" for _, r in runs_display.iterrows()],
            x=runs_display["trading_fees_total"],
            name="Trading Fees",
            orientation="h",
            marker=dict(color=COLORS["warning"]),
            text=[f"${v:,.2f}" for v in runs_display["trading_fees_total"]],
            textposition="inside",
        ))

        fig.update_layout(
            title="Cost Stack: API Cost + Trading Fees",
            barmode="stack",
            height=max(250, len(runs_display) * 35),
            template="plotly_white",
            xaxis_title="Cost (USD)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=20, r=20, t=50, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section B: Efficiency Leaderboard
    # ------------------------------------------------------------------
    st.subheader("Efficiency Leaderboard")

    if not df_runs.empty:
        # Build leaderboard
        df_lb = df_runs.copy()

        # Normalize and score (lower is better rank)
        n = max(len(df_lb), 2)
        # Inverse rank for cost/speed (lower cost = better)
        df_lb["return_rank"] = df_lb["return_pct"].rank(ascending=False)
        df_lb["cost_eff_rank"] = df_lb["return_per_dollar_cost"].rank(ascending=False)
        df_lb["speed_rank"] = (1.0 / df_lb["avg_latency_ms"].clip(lower=1)).rank(ascending=False)
        df_lb["winrate_rank"] = df_lb["win_rate"].rank(ascending=False)

        df_lb["efficiency_score"] = (
            0.4 * df_lb["return_rank"]
            + 0.3 * df_lb["cost_eff_rank"]
            + 0.2 * df_lb["speed_rank"]
            + 0.1 * df_lb["winrate_rank"]
        )
        df_lb["efficiency_score"] = df_lb["efficiency_score"].rank(method="min")

        display_cols = {
            "model": "Model",
            "start_date": "Start",
            "end_date": "End",
            "return_pct": "Return%",
            "return_per_dollar_cost": "Ret/$Cost",
            "tokens_per_decision": "Tokens/Dec",
            "cost_per_decision": "$/Dec",
            "avg_latency_ms": "AvgLat(ms)",
            "efficiency_score": "Score",
        }
        cols_avail = [c for c in display_cols if c in df_lb.columns]
        df_show = df_lb[cols_avail].rename(columns={
            c: display_cols[c] for c in cols_avail
        })
        sort_col = "Score" if "Score" in df_show.columns else display_cols["return_pct"]
        df_show = df_show.sort_values(sort_col)

        styled_dataframe(
            df_show,
            color_cols=["Return%", "Ret/$Cost", "Score"],
            pct_cols=["Return%"],
            usd_cols=["$/Dec"],
            height=350,
        )

        st.caption(
            "Efficiency Score = 0.4*ReturnRank + 0.3*CostEfficiencyRank "
            "+ 0.2*SpeedRank + 0.1*WinRateRank. Lower = better."
        )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section C: Cost vs Return Scatter
    # ------------------------------------------------------------------
    st.subheader("Cost vs Return Efficiency")
    st.plotly_chart(
        efficiency_scatter(df_runs, "Cost vs Return — Bubble size = Trade Count"),
        use_container_width=True,
    )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section D: Token Efficiency Breakdown
    # ------------------------------------------------------------------
    st.subheader("Token Efficiency")

    if not df_runs.empty:
        col_d1, col_d2 = st.columns(2)

        with col_d1:
            # Tokens per decision by run
            fig = px.bar(
                df_runs,
                x="run_id", y="tokens_per_decision",
                color="model",
                title="Tokens per Decision",
                labels={"tokens_per_decision": "Tokens", "run_id": "Run"},
                color_discrete_map=MODEL_COLORS,
                text=[f"{v:,.0f}" for v in df_runs["tokens_per_decision"]],
            )
            fig.update_layout(
                height=350,
                template="plotly_white",
                showlegend=False,
                xaxis=dict(showticklabels=False),
            )
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        with col_d2:
            # Cost per decision by run
            fig = px.bar(
                df_runs,
                x="run_id", y="cost_per_decision",
                color="model",
                title="Cost per Decision (USD)",
                labels={"cost_per_decision": "Cost (USD)", "run_id": "Run"},
                color_discrete_map=MODEL_COLORS,
                text=[f"${v:,.4f}" for v in df_runs["cost_per_decision"]],
            )
            fig.update_layout(
                height=350,
                template="plotly_white",
                showlegend=False,
                xaxis=dict(showticklabels=False),
            )
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        # Aggregate by model
        st.markdown("**Per-Model Averages:**")
        model_agg = df_runs.groupby("model").agg(
            avg_tokens_per_dec=("tokens_per_decision", "mean"),
            avg_cost_per_dec=("cost_per_decision", "mean"),
            avg_latency=("avg_latency_ms", "mean"),
            total_prompt=("total_prompt_tokens", "sum"),
            total_completion=("total_completion_tokens", "sum"),
            total_api_cost=("api_cost_total", "sum"),
            runs=("run_id", "count"),
        ).reset_index()

        styled_dataframe(
            model_agg,
            color_cols=["avg_tokens_per_dec", "avg_cost_per_dec", "avg_latency"],
            usd_cols=["avg_cost_per_dec", "total_api_cost"],
        )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section E: Latency Deep-Dive
    # ------------------------------------------------------------------
    st.subheader("Latency Deep-Dive")

    # For latency we need individual run data — pick first run
    run_list = dl.get_run_list(model=model_filter)
    if run_list:
        selected_run = st.selectbox(
            "Select run for latency detail:",
            options=run_list,
            index=0,
            key="latency_run",
        )
        df_llm = dl.get_llm_calls(selected_run)

        if not df_llm.empty:
            col_e1, col_e2 = st.columns(2)

            with col_e1:
                # Latency over time
                fig = px.scatter(
                    df_llm,
                    x="decision_timestamp", y="latency_ms",
                    color="round_num",
                    title="LLM Call Latency Scatter Over Time",
                    labels={"latency_ms": "Latency (ms)", "decision_timestamp": "Time"},
                    color_continuous_scale="Viridis",
                    opacity=0.7,
                )
                fig.add_hline(
                    y=df_llm["latency_ms"].mean(),
                    line=dict(color="red", dash="dash"),
                    annotation_text="Mean",
                )
                fig.update_layout(height=350, template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

            with col_e2:
                # Latency vs token count scatter
                fig = px.scatter(
                    df_llm,
                    x="total_tokens", y="latency_ms",
                    color="round_num",
                    title="Latency vs Token Count",
                    labels={
                        "latency_ms": "Latency (ms)",
                        "total_tokens": "Total Tokens",
                    },
                    color_continuous_scale="Viridis",
                    opacity=0.7,
                )
                fig.update_layout(height=350, template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section F: ROI Summary Cards
    # ------------------------------------------------------------------
    st.subheader("ROI Summary")

    if not df_runs.empty:
        cols = st.columns(min(len(df_runs), 3))
        for i, (_, run) in enumerate(df_runs.iterrows()):
            ret_per_cost = run.get("return_per_dollar_cost", 0) or 0
            total_tokens = (run.get("total_prompt_tokens", 0) or 0) + (run.get("total_completion_tokens", 0) or 0)
            ret_per_1k_tokens = (run["return_usd"] / (total_tokens / 1000)) if total_tokens > 0 else 0

            with cols[i % 3]:
                color = model_color(run["model"])
                pos_color = COLORS["success"]
                neg_color = COLORS["danger"]
                st.markdown(
                    f"<div style='background:#faf8f5; border:2px solid {color}; border-radius:14px; "
                    f"padding:18px 16px; margin:6px 0; box-shadow:0 2px 8px rgba(0,0,0,0.03);'>"
                    f"<div style='font-weight:700; font-size:1rem; color:{color}; margin-bottom:4px;'>{run['model']}</div>"
                    f"<div style='font-size:0.78rem; color:#8a8782; margin-bottom:10px;'>{run['start_date']} → {run['end_date']}</div>"
                    f"<hr style='border-color:#e8e4dd;'>"
                    f"<div style='font-size:0.8rem; font-weight:700; color:#4a5055;'>For every $1 spent on API:</div>"
                    f"<div style='font-size:22px; font-weight:800; color:{pos_color if ret_per_cost > 0 else neg_color}; margin:4px 0;'>"
                    f"${ret_per_cost:+.2f}</div>"
                    f"<div style='font-size:0.8rem; font-weight:700; color:#4a5055; margin-top:8px;'>For every 1,000 tokens:</div>"
                    f"<div style='font-size:18px; font-weight:800; color:{pos_color if ret_per_1k_tokens > 0 else neg_color}; margin:4px 0;'>"
                    f"${ret_per_1k_tokens:+.4f}</div>"
                    f"<div style='font-size:0.75rem; color:#8a8782; margin-top:8px;'>Avg Latency: {run['avg_latency_ms']:,.0f}ms</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
