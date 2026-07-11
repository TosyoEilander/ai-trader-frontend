"""
Page 5: Trade Pair Analysis
Evaluate individual trade quality and patterns.
P&L distribution, holding period analysis, win rate segmentation, cumulative P&L waterfall.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy import stats as scipy_stats

from frontend.data_layer import DataLayer
from frontend.components import (
    kpi_row, pnl_waterfall, styled_dataframe, COLORS, MODEL_COLORS,
    fmt_pct, fmt_usd,
)


def render(dl: DataLayer, model_filter: str | None = None):
    st.title("Trade Pair Analysis")

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
        label = f"{r['model']} | {r['start_date']}→{r['end_date']} | {int(r['total_trades'])} trades"
        run_labels.append(label)
        run_label_to_id[label] = r["run_id"]

    selected_label = st.selectbox("Select Run", options=run_labels, index=0, key="page5_run_selector")
    run_id = run_label_to_id[selected_label]

    # Load data
    df_completed = dl.get_completed_trades(run_id)
    df_all_trades = dl.get_trades(run_id)
    df_pnl_by_market = dl.get_trade_pnl_summary(run_id)

    if df_completed.empty:
        st.warning("No completed trades (buy→sell pairs) found for this run.")
        if not df_all_trades.empty:
            st.info(f"There are {len(df_all_trades)} trade records but none are completed sell trades with P&L data.")
        return

    # ------------------------------------------------------------------
    # KPI Summary
    # ------------------------------------------------------------------
    total_pnl = df_completed["realized_pnl"].sum()
    total_trades = len(df_completed)
    wins = (df_completed["realized_pnl"] > 0).sum()
    losses = (df_completed["realized_pnl"] <= 0).sum()
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0
    avg_pnl = df_completed["realized_pnl"].mean()
    avg_pnl_pct = df_completed["realized_pnl_pct"].mean()
    avg_holding = df_completed["holding_minutes"].mean()
    best_trade = df_completed.loc[df_completed["realized_pnl"].idxmax()] if total_trades > 0 else None
    worst_trade = df_completed.loc[df_completed["realized_pnl"].idxmin()] if total_trades > 0 else None

    kpi_row([
        {"label": "Completed Trades", "value": total_trades, "suffix": ""},
        {"label": "Total Realized P&L", "value": total_pnl, "suffix": " USD"},
        {"label": "Win Rate", "value": win_rate, "suffix": " %"},
        {"label": "Avg P&L/Trade", "value": avg_pnl, "suffix": " USD"},
        {"label": "Avg P&L %", "value": avg_pnl_pct, "suffix": " %"},
        {"label": "Avg Holding", "value": avg_holding / 60, "suffix": " hrs"},
    ], columns=6)

    if best_trade is not None:
        _, bc1, bc2 = st.columns([1, 2, 2])
        bc1.metric("Best Trade", f"{best_trade['symbol']}",
                   delta=f"${best_trade['realized_pnl']:+,.2f} ({best_trade['realized_pnl_pct']:+.2f}%)")
        bc2.metric("Worst Trade", f"{worst_trade['symbol']}",
                   delta=f"${worst_trade['realized_pnl']:+,.2f} ({worst_trade['realized_pnl_pct']:+.2f}%)")

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section A: P&L Distribution
    # ------------------------------------------------------------------
    st.subheader("P&L Distribution")

    col_a1, col_a2 = st.columns(2)

    with col_a1:
        # Histogram with normal fit
        pnl_pct = df_completed["realized_pnl_pct"].dropna()

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=pnl_pct,
            nbinsx=min(30, max(5, len(pnl_pct) // 2)),
            name="P&L %",
            marker=dict(
                color=[
                    COLORS["success"] if v > 0 else COLORS["danger"]
                    for v in pnl_pct
                ],
                opacity=0.7,
            ),
            hovertemplate="P&L: %{x:+.2f}%<br>Count: %{y}<extra></extra>",
        ))

        # Add normal fit if enough data with variance
        if len(pnl_pct) >= 3 and pnl_pct.std() > 1e-9:
            mu, sigma = scipy_stats.norm.fit(pnl_pct.dropna())
            x_range = np.linspace(pnl_pct.min(), pnl_pct.max(), 100)
            n_bins = min(30, max(5, len(pnl_pct) // 2))
            bin_width = (pnl_pct.max() - pnl_pct.min()) / max(n_bins, 1)
            y_fit = scipy_stats.norm.pdf(x_range, mu, sigma) * len(pnl_pct) * bin_width
            fig.add_trace(go.Scatter(
                x=x_range, y=y_fit,
                mode="lines", name="Normal Fit",
                line=dict(color=COLORS["warning"], width=2, dash="dash"),
            ))

        fig.add_vline(x=0, line=dict(color="gray", width=1, dash="dot"))

        fig.update_layout(
            title="Realized P&L % Distribution",
            xaxis_title="P&L (%)",
            yaxis_title="Count",
            height=350,
            template="plotly_white",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_a2:
        # Stats
        st.markdown("**P&L Statistics**")
        stats_data = {
            "Mean P&L %": f"{pnl_pct.mean():+.2f}%",
            "Median P&L %": f"{pnl_pct.median():+.2f}%",
            "Std Dev": f"{pnl_pct.std():.2f}%",
            "Skewness": f"{pnl_pct.skew():.2f}",
            "Max Profit": f"{pnl_pct.max():+.2f}%",
            "Max Loss": f"{pnl_pct.min():+.2f}%",
            "Profit Factor": _profit_factor(df_completed),
        }
        for label, val in stats_data.items():
            st.metric(label, val)

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section B: Holding Period vs P&L Scatter
    # ------------------------------------------------------------------
    st.subheader("Holding Period vs P&L")

    if "holding_minutes" in df_completed.columns:
        col_b1, col_b2 = st.columns([3, 1])

        with col_b1:
            fig = px.scatter(
                df_completed,
                x="holding_minutes", y="realized_pnl_pct",
                color="market",
                size=df_completed["realized_pnl"].abs(),
                title="Holding Period vs P&L %",
                labels={
                    "holding_minutes": "Holding (minutes)",
                    "realized_pnl_pct": "P&L (%)",
                    "market": "Market",
                },
                color_discrete_map={
                    "US": COLORS["us"], "HK": COLORS["hk"],
                    "CN": COLORS["cn"], "CRYPTO": COLORS["crypto"],
                },
                hover_data={
                    "symbol": True,
                    "realized_pnl": ":,.2f",
                },
                opacity=0.7,
            )

            # Trend line
            if len(df_completed) >= 5:
                try:
                    fig.add_trace(go.Scatter(
                        x=df_completed["holding_minutes"],
                        y=np.poly1d(np.polyfit(
                            df_completed["holding_minutes"],
                            df_completed["realized_pnl_pct"], 2
                        ))(df_completed["holding_minutes"].sort_values()),
                        mode="lines",
                        name="Quadratic Fit",
                        line=dict(color=COLORS["dark"], width=2, dash="dash"),
                    ))
                except Exception:
                    pass

            fig.add_hline(y=0, line=dict(color="gray", width=1, dash="dot"))
            fig.update_layout(height=400, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)

        with col_b2:
            st.markdown("**Holding Analysis**")
            # Bucket holdings
            bins = [0, 60, 120, 360, 720, 1440, 100000]
            labels = ["<1h", "1-2h", "2-6h", "6-12h", "12-24h", ">24h"]
            df_completed_ = df_completed.copy()
            df_completed_["holding_bucket"] = pd.cut(
                df_completed_["holding_minutes"], bins=bins, labels=labels, right=True
            )
            if not df_completed_["holding_bucket"].isna().all():
                bucket_stats = df_completed_.groupby("holding_bucket", observed=False).agg(
                    count=("realized_pnl", "count"),
                    avg_pnl=("realized_pnl", "mean"),
                    win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
                ).reset_index()
                for _, row in bucket_stats.iterrows():
                    if pd.notna(row["holding_bucket"]):
                        st.text(
                            f"{row['holding_bucket']}: "
                            f"{int(row['count'])} trades, "
                            f"avg {fmt_usd(row['avg_pnl'])}, "
                            f"{row['win_rate']:.0f}% win"
                        )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section C: Win Rate Segmentation
    # ------------------------------------------------------------------
    st.subheader("Win Rate Segmentation")

    if not df_pnl_by_market.empty:
        col_c1, col_c2 = st.columns(2)

        with col_c1:
            # By market
            fig = px.bar(
                df_pnl_by_market,
                x="market", y="trade_count",
                color="market",
                title="Trade Count by Market",
                color_discrete_map={
                    "US": COLORS["us"], "HK": COLORS["hk"],
                    "CN": COLORS["cn"], "CRYPTO": COLORS["crypto"],
                },
                text="trade_count",
            )
            fig.update_layout(height=300, template="plotly_white", showlegend=False)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        with col_c2:
            # Win rate by market
            df_winrate = df_pnl_by_market.copy()
            df_winrate["win_rate"] = (
                df_winrate["wins"] / df_winrate["trade_count"] * 100
            )
            fig = px.bar(
                df_winrate,
                x="market", y="win_rate",
                color="market",
                title="Win Rate by Market (%)",
                color_discrete_map={
                    "US": COLORS["us"], "HK": COLORS["hk"],
                    "CN": COLORS["cn"], "CRYPTO": COLORS["crypto"],
                },
                text=[f"{v:.0f}%" for v in df_winrate["win_rate"]],
            )
            fig.add_hline(y=50, line=dict(color="gray", dash="dash"))
            fig.update_layout(height=300, yaxis_range=[0, 100], template="plotly_white", showlegend=False)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        # P&L by market table
        styled_dataframe(
            df_pnl_by_market,
            color_cols=["total_pnl", "avg_pnl", "win_rate"],
            usd_cols=["avg_pnl", "total_pnl"],
        )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section D: Cumulative P&L Waterfall
    # ------------------------------------------------------------------
    st.subheader("Cumulative P&L Waterfall")
    st.plotly_chart(
        pnl_waterfall(df_completed, "Cumulative Realized P&L Over Time"),
        use_container_width=True,
    )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section E: Trade Sequence Table
    # ------------------------------------------------------------------
    st.subheader("Trade Sequence")

    df_completed_sorted = df_completed.sort_values("timestamp")

    # Fancy display
    display_cols = {
        "timestamp": "Sell Time",
        "symbol": "Symbol",
        "market": "Market",
        "buy_timestamp": "Buy Time",
        "quantity": "Qty",
        "price": "Sell Price",
        "realized_pnl": "P&L",
        "realized_pnl_pct": "P&L%",
        "holding_minutes": "Holding(min)",
    }
    cols_avail = [c for c in display_cols if c in df_completed_sorted.columns]
    df_show = df_completed_sorted[cols_avail].rename(columns={
        c: display_cols[c] for c in cols_avail
    })

    styled_dataframe(
        df_show,
        color_cols=["P&L", "P&L%"],
        pct_cols=["P&L%"],
        usd_cols=["P&L", "Sell Price"],
        height=400,
    )

    csv = df_show.to_csv(index=False)
    st.download_button(
        "Export Trade Pairs CSV",
        data=csv,
        file_name=f"trade_pairs_{run_id}.csv",
        mime="text/csv",
    )

    # ------------------------------------------------------------------
    # Section F: Best/Worst trades spotlight
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Trade Spotlight")

    col_f1, col_f2 = st.columns(2)

    with col_f1:
        st.markdown("**Top 5 Best Trades:**")
        best_5 = df_completed_sorted.nlargest(5, "realized_pnl")
        for _, t in best_5.iterrows():
            st.markdown(
                f"🟢 **{t['symbol']}** ({t['market']}) — "
                f"{fmt_usd(t['realized_pnl'])} ({fmt_pct(t['realized_pnl_pct'])}) "
                f"held {int(t['holding_minutes'])}min"
            )

    with col_f2:
        st.markdown("**Top 5 Worst Trades:**")
        worst_5 = df_completed_sorted.nsmallest(5, "realized_pnl")
        for _, t in worst_5.iterrows():
            st.markdown(
                f"🔴 **{t['symbol']}** ({t['market']}) — "
                f"{fmt_usd(t['realized_pnl'])} ({fmt_pct(t['realized_pnl_pct'])}) "
                f"held {int(t['holding_minutes'])}min"
            )


def _profit_factor(df_completed: pd.DataFrame) -> str:
    """Calculate profit factor (gross profit / gross loss)."""
    gross_profit = df_completed[df_completed["realized_pnl"] > 0]["realized_pnl"].sum()
    gross_loss = abs(df_completed[df_completed["realized_pnl"] < 0]["realized_pnl"].sum())
    if gross_loss > 0:
        return f"{gross_profit / gross_loss:.2f}x"
    return "N/A (no losses)"
