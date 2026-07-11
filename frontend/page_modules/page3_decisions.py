"""
Page 3: Decision Process Analytics
Understand HOW the AI thinks and decides.
Decision timeline, tool usage, token trends, latency, market regime, rejection analysis.
"""

from __future__ import annotations
import json

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from frontend.data_layer import DataLayer
from frontend.components import (
    kpi_row, tool_usage_bar, latency_violin, regime_bar_chart,
    COLORS, styled_dataframe,
)


def render(dl: DataLayer, model_filter: str | None = None):
    st.title("Decision Process Analytics")

    # ------------------------------------------------------------------
    # Run selector
    # ------------------------------------------------------------------
    run_list = dl.get_run_list(model=model_filter)
    if not run_list:
        st.warning("No runs found.")
        return

    run_summary_df = dl.get_all_runs_brief()
    if model_filter:
        run_summary_df = run_summary_df[run_summary_df["model"] == model_filter]

    run_labels = []
    run_label_to_id = {}
    for _, r in run_summary_df.iterrows():
        label = f"{r['model']} | {r['start_date']}→{r['end_date']} | {int(r['decisions_made'])} decisions"
        run_labels.append(label)
        run_label_to_id[label] = r["run_id"]

    selected_label = st.selectbox("Select Run", options=run_labels, index=0, key="page3_run_selector")
    run_id = run_label_to_id[selected_label]

    # Load data
    data = dl.get_run_package(run_id)
    df_decisions = data["decisions"]
    df_llm = data["llm_calls"]
    df_tool = data["tool_calls"]
    df_tool_summary = data["tool_summary"]
    df_token_timeline = data["token_timeline"]
    df_regime = data["regime_summary"]
    df_rejection = data["rejection_summary"]
    df_round = data["round_summary"]

    # ------------------------------------------------------------------
    # KPI Summary
    # ------------------------------------------------------------------
    total_tool_calls = len(df_tool)
    total_llm_calls = len(df_llm)
    total_tokens = int(df_llm["total_tokens"].sum()) if not df_llm.empty else 0
    avg_latency = df_llm["latency_ms"].mean() if not df_llm.empty else 0
    unique_tools = df_tool["tool_name"].nunique() if not df_tool.empty else 0

    kpi_row([
        {"label": "LLM Calls", "value": total_llm_calls, "suffix": ""},
        {"label": "Tool Calls", "value": total_tool_calls, "suffix": ""},
        {"label": "Total Tokens", "value": f"{total_tokens:,}", "suffix": ""},
        {"label": "Avg Latency", "value": avg_latency, "suffix": " ms"},
        {"label": "Unique Tools", "value": unique_tools, "suffix": ""},
        {"label": "Decisions", "value": len(df_decisions), "suffix": ""},
    ], columns=6)

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section A: Decision Timeline
    # ------------------------------------------------------------------
    st.subheader("Decision Timeline")

    if not df_decisions.empty:
        _render_decision_timeline(df_decisions, df_llm, df_tool)
    else:
        st.info("No decision data.")

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section B: Tool Usage Distribution
    # ------------------------------------------------------------------
    col_b, col_c = st.columns(2)

    with col_b:
        st.subheader("Tool Usage Distribution")
        if not df_tool_summary.empty:
            st.plotly_chart(tool_usage_bar(df_tool_summary), use_container_width=True)
        else:
            st.info("No tool call data.")

    with col_c:
        st.subheader("Tool Calls by Round")
        df_tool_by_round = data["tool_calls_by_round"]
        if not df_tool_by_round.empty:
            fig = px.bar(
                df_tool_by_round,
                x="round_num", y="call_count", color="tool_name",
                title="Tool Calls per Round",
                labels={"round_num": "Round", "call_count": "Count", "tool_name": "Tool"},
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_layout(height=350, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section D: Token Usage Over Time
    # ------------------------------------------------------------------
    st.subheader("Token Usage Trend")

    if not df_token_timeline.empty:
        col_d1, col_d2 = st.columns([3, 1])
        with col_d1:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_token_timeline["decision_timestamp"],
                y=df_token_timeline["total_tokens"],
                name="Total Tokens",
                marker=dict(color=COLORS["primary"], opacity=0.5),
                yaxis="y",
            ))
            fig.add_trace(go.Scatter(
                x=df_token_timeline["decision_timestamp"],
                y=df_token_timeline["prompt_tokens"],
                mode="lines", name="Prompt Tokens",
                line=dict(color=COLORS["info"], width=2),
                yaxis="y",
            ))
            fig.add_trace(go.Scatter(
                x=df_token_timeline["decision_timestamp"],
                y=df_token_timeline["completion_tokens"],
                mode="lines", name="Completion Tokens",
                line=dict(color=COLORS["success"], width=2),
                yaxis="y",
            ))

            # Moving average
            window = max(5, len(df_token_timeline) // 20)
            ma = df_token_timeline["total_tokens"].rolling(window=window, min_periods=1).mean()
            fig.add_trace(go.Scatter(
                x=df_token_timeline["decision_timestamp"],
                y=ma,
                mode="lines", name=f"MA({window})",
                line=dict(color=COLORS["danger"], width=2, dash="dash"),
                yaxis="y",
            ))

            fig.update_layout(
                title="Token Usage per Decision",
                xaxis_title="Time",
                yaxis_title="Tokens",
                height=350,
                template="plotly_white",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_d2:
            st.markdown("**Token Stats**")
            if not df_llm.empty:
                st.metric("Avg Prompt Tokens", f"{df_llm['prompt_tokens'].mean():,.0f}")
                st.metric("Avg Completion Tokens", f"{df_llm['completion_tokens'].mean():,.0f}")
                st.metric("Max Total Tokens", f"{df_llm['total_tokens'].max():,}")
                st.metric("Total Tokens", f"{df_llm['total_tokens'].sum():,}")
                ratio = (
                    df_llm["prompt_tokens"].sum() / df_llm["completion_tokens"].sum()
                    if df_llm["completion_tokens"].sum() > 0 else 0
                )
                st.metric("Prompt:Completion", f"{ratio:.1f}:1")

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section E: Latency Distribution
    # ------------------------------------------------------------------
    st.subheader("Latency Analysis")

    if not df_llm.empty:
        col_e1, col_e2 = st.columns(2)

        with col_e1:
            # Histogram
            fig = px.histogram(
                df_llm, x="latency_ms", nbins=30,
                title="LLM Call Latency Distribution",
                labels={"latency_ms": "Latency (ms)", "count": "Frequency"},
                color_discrete_sequence=[COLORS["primary"]],
            )
            p50 = df_llm["latency_ms"].quantile(0.50)
            p90 = df_llm["latency_ms"].quantile(0.90)
            p99 = df_llm["latency_ms"].quantile(0.99)
            fig.add_vline(x=p50, line=dict(color="green", dash="dash"),
                         annotation_text=f"P50: {p50:.0f}ms")
            fig.add_vline(x=p90, line=dict(color="orange", dash="dash"),
                         annotation_text=f"P90: {p90:.0f}ms")
            fig.add_vline(x=p99, line=dict(color="red", dash="dash"),
                         annotation_text=f"P99: {p99:.0f}ms")
            fig.update_layout(height=350, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)

        with col_e2:
            st.plotly_chart(latency_violin(df_llm), use_container_width=True)

        # Summary stats
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("P50 Latency", f"{p50:.0f}ms")
        c2.metric("P90 Latency", f"{p90:.0f}ms")
        c3.metric("P99 Latency", f"{p99:.0f}ms")
        c4.metric("Mean Latency", f"{df_llm['latency_ms'].mean():.0f}ms")
        c5.metric("Max Latency", f"{df_llm['latency_ms'].max():.0f}ms")

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section F: Market Regime Analysis
    # ------------------------------------------------------------------
    st.subheader("Market Regime Analysis")

    if not df_regime.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            st.plotly_chart(regime_bar_chart(df_regime), use_container_width=True)
        with col_f2:
            styled_dataframe(
                df_regime,
                color_cols=["decision_count", "trade_count"],
            )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section G: Rejection Analysis
    # ------------------------------------------------------------------
    st.subheader("Trade Rejection Analysis")

    if not df_rejection.empty:
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig = px.bar(
                df_rejection,
                x="rejection_code", y="count",
                title="Rejection Reasons",
                labels={"rejection_code": "Reason", "count": "Count"},
                color="rejection_code",
                color_discrete_sequence=px.colors.qualitative.Set2,
                text="count",
            )
            fig.update_layout(
                height=350,
                template="plotly_white",
                showlegend=False,
            )
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        with col_g2:
            styled_dataframe(
                df_rejection,
                color_cols=["count"],
            )
            total_rejections = int(df_rejection["count"].sum())
            st.metric("Total Rejections", total_rejections)
    else:
        st.info("No trade rejections recorded — all trades passed validation.")

    st.markdown("---")

    # ------------------------------------------------------------------
    # Round Summary Table
    # ------------------------------------------------------------------
    st.subheader("LLM Round Summary")
    if not df_round.empty:
        styled_dataframe(
            df_round,
            color_cols=["avg_total_tokens", "avg_latency_ms"],
        )
    else:
        st.info("No round data.")


# ---------------------------------------------------------------------------
# Decision Timeline Renderer
# ---------------------------------------------------------------------------

def _render_decision_timeline(
    df_decisions: pd.DataFrame,
    df_llm: pd.DataFrame,
    df_tool: pd.DataFrame,
):
    """Render an interactive decision timeline with expandable detail cards."""
    # Color map for actions
    action_colors = {
        "trade": COLORS["success"],
        "hold": COLORS["dark"],
        "query": COLORS["warning"],
    }

    # Build timeline chart
    df_d = df_decisions.copy()
    df_d["color"] = df_d["action"].map(action_colors).fillna(COLORS["dark"])

    fig = go.Figure()
    for action in ["trade", "hold"]:
        subset = df_d[df_d["action"] == action]
        if subset.empty:
            continue
        fig.add_trace(go.Scatter(
            x=subset["timestamp"], y=[1] * len(subset),
            mode="markers",
            name=action.upper(),
            marker=dict(
                symbol="diamond" if action == "trade" else "circle",
                size=10 if action == "trade" else 6,
                color=action_colors[action],
                line=dict(color="white" if action == "trade" else "gray", width=1),
            ),
            hovertemplate=f"%{{x}}<br>{action.upper()}<br>NAV: $%{{customdata:,.2f}}<extra></extra>",
            customdata=subset["portfolio_nav"],
        ))

    fig.update_layout(
        title="",
        height=100,
        template="plotly_white",
        showlegend=True,
        legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5),
        xaxis=dict(showgrid=True),
        yaxis=dict(visible=False, fixedrange=True),
        margin=dict(l=20, r=20, t=10, b=40),
    )
    st.caption("Decision Timeline — click legend to filter by action")
    st.plotly_chart(fig, use_container_width=True)

    # Detail expanders
    trade_decisions = df_decisions[df_decisions["action"] == "trade"]
    st.write(f"**Trade Decisions ({len(trade_decisions)} total):**")

    show_n = st.slider("Show last N trade decisions", 1, min(20, max(1, len(trade_decisions))), 5, key="p3_show_n")
    for _, dec in trade_decisions.tail(show_n).iterrows():
        with st.expander(
            f"{dec['timestamp']} — TRADE | NAV: ${dec['portfolio_nav']:,.2f} | "
            f"Regime: {dec.get('market_regime', 'N/A')}"
        ):
            try:
                trades = json.loads(dec["trades"]) if dec["trades"] else []
            except (json.JSONDecodeError, TypeError):
                trades = []

            st.write(f"**Reason:** {dec['reason']}")
            st.write(f"**Market Regime:** {dec.get('market_regime', 'N/A')} "
                    f"(1h: {dec.get('index_1h_pct', 0):+.3f}%, "
                    f"1d: {dec.get('index_1d_pct', 0):+.3f}%)")

            if trades:
                st.write("**Orders:**")
                for t in trades:
                    side_emoji = "🟢" if t.get("side") == "buy" else "🔴"
                    st.text(
                        f"  {side_emoji} {t.get('side', '?').upper()} "
                        f"{t.get('symbol', '?')} ({t.get('market', '?')}) "
                        f"x{t.get('quantity', '?')} — {t.get('reason', '')}"
                    )

            # Show LLM calls for this decision
            ts = dec["timestamp"]
            llm_for_dec = df_llm[df_llm["decision_timestamp"] == ts] if not df_llm.empty else pd.DataFrame()
            if not llm_for_dec.empty:
                st.write("**LLM Calls:**")
                for _, call in llm_for_dec.iterrows():
                    st.text(
                        f"  Round {int(call['round_num'])}: "
                        f"{int(call['total_tokens'])} tokens, "
                        f"{call['latency_ms']:.0f}ms"
                    )

            # Show tool calls for this decision
            if not df_tool.empty:
                tool_for_dec = df_tool[df_tool["decision_timestamp"] == ts]
                if not tool_for_dec.empty:
                    st.write(f"**Tool Calls ({len(tool_for_dec)}):**")
                    for _, tc in tool_for_dec.iterrows():
                        st.text(
                            f"  [{tc['tool_name']}] {tc['tool_args']} "
                            f"— {tc['latency_ms']:.0f}ms"
                        )
