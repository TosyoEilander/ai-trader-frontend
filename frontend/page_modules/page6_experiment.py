"""
Page 6: Experiment Manager
Configure, launch, and monitor backtest runs.
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import pandas as pd

from frontend.data_layer import DataLayer
from frontend.components import kpi_row, styled_dataframe, COLORS, MODEL_COLORS

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def render(dl: DataLayer, model_filter: str | None = None):
    st.title("Experiment Manager")

    # ------------------------------------------------------------------
    # Tabs: Config / Run Queue / Results
    # ------------------------------------------------------------------
    tab1, tab2, tab3 = st.tabs([
        "Configuration & Launch",
        "Run Queue & Monitor",
        "Results Quick View",
    ])

    with tab1:
        _render_config_tab(dl)

    with tab2:
        _render_queue_tab(dl, model_filter)

    with tab3:
        _render_results_tab(dl, model_filter)


# ---------------------------------------------------------------------------
# Tab 1: Configuration & Launch
# ---------------------------------------------------------------------------

def _render_config_tab(dl: DataLayer):
    """Config form and launch controls."""
    st.subheader("Backtest Configuration")

    # Load current config
    config_path = PROJECT_ROOT / "config" / "config.toml"
    config_text = ""
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_text = f.read()

    # Model selection
    col_m1, col_m2, col_m3 = st.columns(3)

    with col_m1:
        model_name = st.selectbox(
            "Model",
            options=["deepseek-v4-pro", "deepseek-chat", "mimo-v2.5-pro"],
            index=0,
            help="Select the LLM model to use for trading decisions.",
            key="p6_model",
        )

    with col_m2:
        thinking_enabled = st.checkbox(
            "Enable Thinking Mode",
            value=False,
            help="Enable chain-of-thought reasoning. Slower & more expensive, but may improve decisions.",
            key="p6_thinking",
        )

    with col_m3:
        interval = st.selectbox(
            "Decision Interval",
            options=[30, 60, 120, 240],
            index=1,
            format_func=lambda x: f"{x} minutes",
            key="p6_interval",
        )

    # Date range
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input(
            "Start Date",
            value=datetime(2026, 2, 3),
            key="p6_start_date",
        )
    with col_d2:
        end_date = st.date_input(
            "End Date",
            value=datetime(2026, 3, 3),
            key="p6_end_date",
        )

    # Additional settings
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        initial_cash = st.number_input(
            "Initial Cash (USD)",
            value=100_000,
            min_value=1_000,
            step=10_000,
            format="%d",
        )
    with col_s2:
        max_decisions = st.number_input(
            "Max Decisions (0=unlimited)",
            value=0,
            min_value=0,
            step=10,
        )

    # Advanced settings expander
    with st.expander("Advanced Settings"):
        col_a1, col_a2, col_a3 = st.columns(3)
        with col_a1:
            temperature = st.slider("Temperature", 0.0, 2.0, 0.3, 0.1, key="p6_temperature")
        with col_a2:
            max_rounds = st.slider("Max Agent Rounds", 2, 8, 4, key="p6_max_rounds")
        with col_a3:
            max_tokens = st.slider("Max Tokens", 1024, 16384, 4096, 1024, key="p6_max_tokens")

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            timeout = st.number_input("API Timeout (s)", 30, 600, 180, 30, key="p6_timeout")
        with col_c2:
            output_db = st.text_input(
                "Output Database",
                value=str(PROJECT_ROOT / "output" / "results" / "benchmark.db"),
            )

    st.markdown("---")

    # Estimated cost
    _show_cost_estimate(model_name, thinking_enabled, start_date, end_date, interval)

    # Launch button
    st.markdown("---")
    col_launch1, col_launch2 = st.columns([2, 1])

    with col_launch1:
        if st.button("Launch Backtest", type="primary", use_container_width=True):
            # Build config overrides
            config_overrides = {
                "model": model_name,
                "thinking": thinking_enabled,
                "interval": interval,
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d"),
                "initial_cash": initial_cash,
                "max_decisions": max_decisions,
            }

            cmd = _build_launch_command(config_overrides, output_db)

            with st.spinner("Launching backtest..."):
                try:
                    process = subprocess.Popen(
                        cmd,
                        cwd=str(PROJECT_ROOT),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    st.success(f"Backtest launched! PID: {process.pid}")
                    st.info(
                        "The backtest is running in the background. "
                        "Check the Run Queue tab to monitor progress."
                    )
                    st.code(" ".join(cmd), language="bash")
                except Exception as e:
                    st.error(f"Failed to launch: {e}")

    with col_launch2:
        st.caption("**Dry Run Command:**")
        cmd = _build_launch_command({
            "model": model_name, "thinking": thinking_enabled,
            "interval": interval, "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"), "initial_cash": initial_cash,
            "max_decisions": max_decisions,
        }, output_db)
        st.code(" ".join(cmd), language="bash")

    # Current config display
    st.markdown("---")
    st.subheader("Current config.toml")
    if config_text:
        st.code(config_text, language="toml", line_numbers=True)
    else:
        st.warning("config.toml not found")


def _build_launch_command(overrides: dict, output_db: str) -> list[str]:
    """Build CLI command for launching the backtest."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "runners" / "run_backtest.py"),
        "--model", overrides["model"],
        "--start", overrides["start"],
        "--end", overrides["end"],
        "--interval", str(overrides["interval"]),
        "--initial-cash", str(overrides["initial_cash"]),
        "--max-decisions", str(overrides["max_decisions"]),
        "--output", output_db,
    ]
    if overrides.get("thinking"):
        cmd.append("--thinking")
    return cmd


def _show_cost_estimate(model: str, thinking: bool, start, end, interval: int):
    """Show estimated cost for the run."""
    # Count business days in range (rough)
    days = (end - start).days + 1
    decisions_per_day = (24 * 60) // interval
    total_decisions = days * decisions_per_day

    # Estimated tokens per decision based on historical data
    pricing = {
        "deepseek-v4-pro": {"input": 0.28, "output": 1.10},
        "deepseek-chat": {"input": 0.07, "output": 0.28},
        "mimo-v2.5-pro": {"input": 0.55, "output": 2.19},
    }
    p = pricing.get(model, {"input": 0.50, "output": 1.50})

    # Rough token estimates (from observed runs: ~30k prompt + ~2k completion per decision)
    avg_prompt_tokens = 30000
    avg_completion_tokens = 2000
    if thinking:
        avg_completion_tokens *= 3

    est_input_cost = (total_decisions * avg_prompt_tokens / 1_000_000) * p["input"]
    est_output_cost = (total_decisions * avg_completion_tokens / 1_000_000) * p["output"]
    est_total = est_input_cost + est_output_cost

    st.info(
        f"**Estimated Cost:** ~${est_total:.2f} USD "
        f"(~{total_decisions:,} decisions over {days} days, "
        f"{decisions_per_day} decisions/day at {interval}min intervals)\n\n"
        f"Input: ~${est_input_cost:.2f} | Output: ~${est_output_cost:.2f} | "
        f"Model: {model} {'(thinking ON)' if thinking else ''}"
    )


# ---------------------------------------------------------------------------
# Tab 2: Run Queue & Monitor
# ---------------------------------------------------------------------------

def _render_queue_tab(dl: DataLayer, model_filter: str | None = None):
    """Display run queue with status and progress."""
    st.subheader("Run Queue")

    # Refresh button
    if st.button("Refresh", key="refresh_queue"):
        dl.reload()
        st.rerun()

    df_all = dl.get_all_runs_brief()
    if model_filter:
        df_all = df_all[df_all["model"] == model_filter]

    if df_all.empty:
        st.info("No runs found.")
        return

    # Show running runs first
    running = df_all[df_all["status"] == "running"]
    completed = df_all[df_all["status"] == "completed"]
    failed = df_all[df_all["status"] == "failed"]

    # Running runs
    if not running.empty:
        st.markdown("### Running")
        for _, run in running.iterrows():
            with st.container():
                col_r1, col_r2, col_r3 = st.columns([3, 2, 1])
                with col_r1:
                    st.markdown(f"**{run['model']}** — {run['start_date']} → {run['end_date']}")
                    progress = min(
                        int(run.get("decisions_made", 0)) / max(int(run.get("total_decisions", 1)), 1),
                        1.0,
                    )
                    st.progress(progress)
                with col_r2:
                    st.metric("Decisions Made", f"{int(run['decisions_made'])}")
                    st.metric("Current NAV", f"${run['current_nav']:,.2f}")
                with col_r3:
                    st.metric("Trades", f"{int(run['total_trades'])}")
                    st.metric("Cost", f"${run.get('total_cost', 0):,.4f}")
                st.markdown("---")

    # Completed runs
    if not completed.empty:
        st.markdown("### Completed")
        df_comp_display = completed[[
            "model", "start_date", "end_date", "decisions_made",
            "current_nav", "total_trades", "successful_trades",
            "total_cost",
        ]].copy()
        df_comp_display["return_pct"] = (
            (completed["current_nav"] - 100000) / 100000 * 100
        ).values
        styled_dataframe(
            df_comp_display,
            color_cols=["return_pct", "current_nav"],
            pct_cols=["return_pct"],
            usd_cols=["current_nav", "total_cost"],
            height=300,
        )

    # Failed runs
    if not failed.empty:
        st.markdown("### Failed")
        styled_dataframe(failed, height=200)
        for _, run in failed.iterrows():
            run_detail = dl.get_run_detail(run["run_id"])
            if run_detail.get("error_message"):
                st.error(f"Run {run['run_id']}: {run_detail['error_message']}")

    # Auto-refresh toggle
    st.markdown("---")
    auto_refresh = st.checkbox("Auto-refresh (10s)", value=False, key="p6_auto_refresh")
    if auto_refresh:
        time.sleep(10)
        st.rerun()


# ---------------------------------------------------------------------------
# Tab 3: Results Quick View
# ---------------------------------------------------------------------------

def _render_results_tab(dl: DataLayer, model_filter: str | None = None):
    """Quick view of completed run results."""
    st.subheader("Results Quick View")

    df_runs = dl.get_runs_summary(model=model_filter)

    if df_runs.empty:
        st.info("No completed runs to display.")
        return

    # Compute return
    df_runs["return_pct"] = (
        (df_runs["current_nav"] - df_runs["initial_cash"])
        / df_runs["initial_cash"] * 100
    )

    for _, run in df_runs.iterrows():
        ret_pct = run["return_pct"]
        ret_color = "green" if ret_pct > 0 else "red"

        with st.expander(
            f"{run['model']} | {run['start_date']} → {run['end_date']} | "
            f"Return: {ret_pct:+.2f}% | Trades: {int(run['total_trades'])}",
            expanded=(len(df_runs) == 1),
        ):
            c1, c2, c3, c4 = st.columns(4)

            with c1:
                st.markdown(f"**Performance**")
                st.metric("Final NAV", f"${run['current_nav']:,.2f}")
                st.metric("Return", f"{ret_pct:+.2f}%")
                st.metric("Return/$Cost", f"{run.get('return_per_dollar_cost', 0):.2f}x")

            with c2:
                st.markdown(f"**Trading**")
                st.metric("Total Trades", f"{int(run['total_trades'])}")
                st.metric("Successful", f"{int(run['successful_trades'])}")
                win_rate = (
                    int(run['successful_trades']) / int(run['total_trades']) * 100
                    if int(run['total_trades']) > 0 else 0
                )
                st.metric("Win Rate", f"{win_rate:.0f}%")

            with c3:
                st.markdown(f"**Cost**")
                st.metric("API Cost", f"${run.get('api_cost_total', 0):,.4f}")
                st.metric("Trading Fees", f"${run.get('trading_fees_total', 0):,.4f}")
                st.metric("Total Cost", f"${run.get('total_cost', 0):,.4f}")

            with c4:
                st.markdown(f"**Efficiency**")
                st.metric("Avg Latency", f"{run.get('avg_latency_ms', 0):,.0f}ms")
                st.metric("Tokens/Dec", f"{run.get('tokens_per_decision', 0):,.0f}")
                st.metric("Cost/Dec", f"${run.get('cost_per_decision', 0):,.6f}")

            # Link to detail page
            st.info(
                f"Go to **Single Run Detail** page and select "
                f"run_id: `{run['run_id']}` for full analysis."
            )

            # Raw result JSON
            try:
                result = json.loads(str(run.get("result", "{}")))
                if result:
                    st.json(result)
            except (json.JSONDecodeError, TypeError):
                pass
