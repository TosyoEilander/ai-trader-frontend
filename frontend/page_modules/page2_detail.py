"""
Page 2: Single Run Detail
Deep-dive into one backtest run's performance.
NAV curve, drawdown, position timeline, market exposure, trade log, return decomposition.
"""

from __future__ import annotations
import json

import streamlit as st
import pandas as pd
import numpy as np

from frontend.data_layer import DataLayer
from frontend.components import (
    kpi_row, nav_chart, drawdown_chart, position_timeline,
    market_exposure_chart, pnl_waterfall, styled_dataframe,
    COLORS, fmt_pct, fmt_usd,
)


def render(dl: DataLayer, model_filter: str | None = None):
    st.title("Single Run Detail")

    # ------------------------------------------------------------------
    # Run selector
    # ------------------------------------------------------------------
    run_list = dl.get_run_list(model=model_filter)
    if not run_list:
        st.warning("No runs found for the selected model filter.")
        return

    run_summary_df = dl.get_all_runs_brief()
    if model_filter:
        run_summary_df = run_summary_df[run_summary_df["model"] == model_filter]

    # Build display labels
    run_labels = []
    run_label_to_id = {}
    for _, r in run_summary_df.iterrows():
        ret_pct = (
            (r["current_nav"] - 100000) / 100000 * 100
            if pd.notna(r["current_nav"]) else 0
        )
        label = (
            f"{r['model']} | {r['start_date']}→{r['end_date']} | "
            f"Ret:{ret_pct:+.2f}% | Trades:{int(r['total_trades'])} | "
            f"Status:{r['status']}"
        )
        run_labels.append(label)
        run_label_to_id[label] = r["run_id"]

    selected_label = st.selectbox(
        "Select Run",
        options=run_labels,
        index=0,
        key="page2_run_selector",
    )
    run_id = run_label_to_id[selected_label]

    # ------------------------------------------------------------------
    # Load all data for this run
    # ------------------------------------------------------------------
    data = dl.get_run_package(run_id)
    run_info = dl.get_run_detail(run_id)

    if not run_info:
        st.error("Run not found.")
        return

    # ------------------------------------------------------------------
    # Section A: Run Info Header + KPI Row
    # ------------------------------------------------------------------
    st.subheader(f"Run: {run_info['model']} | {run_info['start_date']} → {run_info['end_date']}")

    nav_initial = run_info.get("initial_cash", 100000)
    nav_final = run_info.get("current_nav", nav_initial)
    return_pct = (nav_final - nav_initial) / nav_initial * 100
    return_usd = nav_final - nav_initial
    total_cost = run_info.get("total_cost", 0) or 0
    api_cost = run_info.get("api_cost_total", 0) or 0
    trades_total = int(run_info.get("total_trades", 0) or 0)
    trades_success = int(run_info.get("successful_trades", 0) or 0)
    win_rate = (trades_success / trades_total * 100) if trades_total > 0 else 0
    decisions_count = int(run_info.get("decisions_made", 0) or 0)

    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
    tc1.metric("Final NAV", f"${nav_final:,.2f}", delta=f"{return_pct:+.2f}%")
    tc2.metric("Total Return", f"${return_usd:+,.2f}", delta=f"{return_pct:+.2f}%")
    tc3.metric("Total Trades", f"{trades_success}/{trades_total}", delta=f"{win_rate:.0f}% Win")
    tc4.metric("Total Cost", f"${total_cost:,.4f}")
    tc5.metric("Decisions", f"{decisions_count}", delta=f"{run_info.get('interval_min', 60)}min")

    tc1.caption(f"Status: {run_info['status']}")
    tc2.caption(f"Thinking: {'ON' if run_info.get('thinking_enabled') else 'OFF'}")
    tc3.caption(f"API Cost: ${api_cost:,.4f}")
    tc4.caption(f"Ret/$Cost: {run_info.get('return_per_dollar_cost', 0):.2f}x")
    tc5.caption(f"Tokens/Dec: {run_info.get('tokens_per_decision', 0):,.0f}")

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section B: NAV Curve
    # ------------------------------------------------------------------
    st.subheader("Portfolio NAV vs Benchmark")
    df_nav = data["nav"]
    df_trades = data["trades"]

    if not df_nav.empty:
        st.plotly_chart(
            nav_chart(df_nav, df_trades, title=f"NAV — {run_info['model']}"),
            use_container_width=True,
        )
    else:
        st.info("No NAV data available.")

    # ------------------------------------------------------------------
    # Section C: Drawdown (below NAV, aligned)
    # ------------------------------------------------------------------
    if not df_nav.empty:
        st.plotly_chart(drawdown_chart(df_nav), use_container_width=True)

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section D: Position Timeline
    # ------------------------------------------------------------------
    st.subheader("Position Timeline (Gantt)")
    df_completed = data["completed_trades"]
    if not df_completed.empty:
        st.plotly_chart(position_timeline(df_trades), use_container_width=True)
    else:
        st.info("No completed trade pairs to display.")

    # ------------------------------------------------------------------
    # Section E: Market Exposure
    # ------------------------------------------------------------------
    col_exp, col_water = st.columns(2)
    with col_exp:
        if not df_nav.empty and "market_exposure" in df_nav.columns:
            st.plotly_chart(market_exposure_chart(df_nav), use_container_width=True)
    with col_water:
        if not df_completed.empty:
            st.plotly_chart(pnl_waterfall(df_completed), use_container_width=True)

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section F: Trade Log Table
    # ------------------------------------------------------------------
    st.subheader("Trade Log")

    if not df_trades.empty:
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            market_filter = st.selectbox(
                "Market", options=["All", "US", "HK", "CN", "CRYPTO"], key="trade_market"
            )
        with col_f2:
            side_filter = st.selectbox(
                "Side", options=["All", "buy", "sell"], key="trade_side"
            )
        with col_f3:
            success_filter = st.selectbox(
                "Status", options=["All", "Success", "Failed"], key="trade_status"
            )

        df_trades_display = df_trades.copy()
        if market_filter != "All":
            df_trades_display = df_trades_display[df_trades_display["market"] == market_filter]
        if side_filter != "All":
            df_trades_display = df_trades_display[df_trades_display["side"] == side_filter]
        if success_filter == "Success":
            df_trades_display = df_trades_display[df_trades_display["success"] == 1]
        elif success_filter == "Failed":
            df_trades_display = df_trades_display[df_trades_display["success"] == 0]

        # Select and rename columns for display
        display_cols = {
            "timestamp": "Time",
            "symbol": "Symbol",
            "market": "Market",
            "side": "Side",
            "quantity": "Qty",
            "price": "Price",
            "cost": "Cost",
            "fees": "Fees",
            "realized_pnl": "P&L",
            "realized_pnl_pct": "P&L%",
            "holding_minutes": "Hold(min)",
            "rejection_code": "Rejection",
            "error": "Error",
        }
        cols_available = [c for c in display_cols if c in df_trades_display.columns]
        df_show = df_trades_display[cols_available].rename(columns={
            c: display_cols[c] for c in cols_available
        })

        styled_dataframe(
            df_show,
            color_cols=["P&L", "P&L%"],
            pct_cols=["P&L%"],
            usd_cols=["Cost", "Fees", "P&L", "Price"],
            height=400,
        )

        # CSV export
        csv = df_show.to_csv(index=False)
        st.download_button(
            "Export CSV",
            data=csv,
            file_name=f"trades_{run_id}.csv",
            mime="text/csv",
        )
    else:
        st.info("No trades recorded.")

    st.markdown("---")

    # ------------------------------------------------------------------
    # Section G: Return Decomposition + Cost Breakdown (sidebar-style)
    # ------------------------------------------------------------------
    st.subheader("Return & Cost Decomposition")

    cg1, cg2 = st.columns(2)
    with cg1:
        st.markdown("**Return Decomposition**")
        # Realized P&L from completed sells
        realized = df_completed["realized_pnl"].sum() if not df_completed.empty else 0
        # Unrealized = total return - realized
        unrealized = return_usd - realized

        st.metric("Total Return", f"${return_usd:+,.2f}")
        st.metric("Realized P&L", f"${realized:+,.2f}")
        st.metric("Unrealized P&L", f"${unrealized:+,.2f}")

        # Top symbols by trade count
        if not df_trades.empty:
            top_symbols = (
                df_trades.groupby("symbol").size()
                .sort_values(ascending=False).head(5)
            )
            st.write("**Top Traded Symbols:**")
            for sym, cnt in top_symbols.items():
                st.text(f"  {sym}: {cnt} trades")

    with cg2:
        st.markdown("**Cost Breakdown**")
        api_cost_total = run_info.get("api_cost_total", 0) or 0
        trading_fees = run_info.get("trading_fees_total", 0) or 0
        slippage = run_info.get("slippage_total", 0) or 0

        st.metric("Total Cost", f"${total_cost:,.4f}")
        st.metric("API Cost", f"${api_cost_total:,.4f}",
                  delta=f"{api_cost_total/total_cost*100:.0f}%" if total_cost > 0 else None)
        st.metric("Trading Fees", f"${trading_fees:,.4f}",
                  delta=f"{trading_fees/total_cost*100:.0f}%" if total_cost > 0 else None)
        st.metric("Slippage", f"${slippage:,.4f}",
                  delta=f"{slippage/total_cost*100:.0f}%" if total_cost > 0 else None)

        # Top P&L contributors
        if not df_completed.empty:
            pnl_by_sym = (
                df_completed.groupby("symbol")["realized_pnl"].sum()
                .sort_values(ascending=False)
            )
            st.write("**Top P&L Contributors:**")
            for sym, pnl in pnl_by_sym.head(5).items():
                st.text(f"  {sym}: {fmt_usd(pnl)}")
            for sym, pnl in pnl_by_sym.tail(3).items():
                if pnl < 0:
                    st.text(f"  {sym}: {fmt_usd(pnl)}")
