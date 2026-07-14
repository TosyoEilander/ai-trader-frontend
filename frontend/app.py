"""
AI-Trader Benchmark — Streamlit Frontend
=========================================
Frontend for Mint Green main repository (https://github.com/Mint-green/llm-trading-benchmark).

Entry: streamlit run frontend/app.py

6 pages:
  1. Model Comparison Dashboard
  2. Single Run Detail
  3. Decision Process Analytics
  4. Cost & Efficiency Analytics
  5. Trade Pair Analysis
  6. Experiment Manager

Architecture:
  - data_layer.py  : All SQL queries → pandas DataFrames
  - components.py  : Reusable charts, KPI cards, styled tables
  - page_modules/* : Individual page renderers

Backend integration:
  The frontend reads from SQLite databases only. Backend projects (e.g. blue)
  write data to SQLite tables during backtesting; the frontend reads via
  DataLayer. See HOW_TO_CONNECT.md for details.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root (AI-Trader-Frontend/)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

# Page config — must be the first Streamlit call
st.set_page_config(
    page_title="AI-Trader Benchmark",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
    initial_sidebar_state="expanded",
)

from frontend.data_layer import DataLayer
from frontend.components import inject_morandi_css

from frontend.page_modules.page1_overview import render as render_page1
from frontend.page_modules.page2_detail import render as render_page2
from frontend.page_modules.page3_decisions import render as render_page3
from frontend.page_modules.page4_efficiency import render as render_page4
from frontend.page_modules.page5_trades import render as render_page5
from frontend.page_modules.page6_experiment import render as render_page6

# ---------------------------------------------------------------------------
# Database path resolution
# ---------------------------------------------------------------------------
# Priority: env variable > auto-detect > default path
#
# Auto-detect order:
#   1. PROJECT_ROOT/artifacts/runs/*.db   (newest non-empty .db)
#   2. PROJECT_ROOT/output/results/*.db   (legacy)
#   3. Fallback default

def _resolve_db_path() -> str:
    """Smart database path detection."""
    # 1. Environment variable takes priority
    env_path = os.environ.get("BENCHMARK_DB_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. Auto-detect — blue project's own output
    runs_dir = PROJECT_ROOT / "artifacts" / "runs"
    legacy_dir = PROJECT_ROOT / "output" / "results"

    # Priority: newest .db file under artifacts/runs/
    if runs_dir.exists():
        db_files = sorted(
            runs_dir.glob("*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for db in db_files:
            if db.stat().st_size > 0:
                return str(db)

    # Fallback: output/results/ files
    if legacy_dir.exists():
        db_files = sorted(
            legacy_dir.glob("*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for db in db_files:
            if db.stat().st_size > 0:
                return str(db)

    # 3. Default path (may not exist yet; DataLayer will show a friendly hint)
    default = PROJECT_ROOT / "artifacts" / "runs" / "benchmark.db"
    return str(default)

DB_PATH = _resolve_db_path()


@st.cache_resource
def get_data_layer() -> DataLayer:
    """Get or create the DataLayer singleton."""
    return DataLayer(DB_PATH)


# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------

PAGE_MAP = {
    "1. Model Comparison": render_page1,
    "2. Single Run Detail": render_page2,
    "3. Decision Analytics": render_page3,
    "4. Cost & Efficiency": render_page4,
    "5. Trade Analysis": render_page5,
    "6. Experiment Manager": render_page6,
}


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar():
    """Render sidebar: navigation + global filters."""
    st.sidebar.title("AI-Trader Benchmark")

    # Database status
    st.sidebar.caption(f"DB: `{DB_PATH}`")
    if not os.path.exists(DB_PATH):
        st.sidebar.warning(
            "Database file not found!\n\n"
            "Set `BENCHMARK_DB_PATH` env variable to your benchmark.db,\n"
            "or run a backtest to generate data.\n\n"
            "See `HOW_TO_CONNECT.md`"
        )

    # Navigation
    selected = st.sidebar.radio(
        "Navigation",
        list(PAGE_MAP.keys()),
        index=0,
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")

    # Model filter
    dl = get_data_layer()
    try:
        models = dl.get_available_models()
    except Exception:
        models = []

    model_count = len(models)
    if model_count == 0:
        st.sidebar.info("No model data available")
    elif model_count == 1:
        st.sidebar.info(f"1 model: **{models[0]}**")
    else:
        st.sidebar.success(f"{model_count} models available")

    selected_model = None
    if models:
        selected_model = st.sidebar.selectbox(
            "Model Filter",
            options=["All (compare)"] + models,
            index=0,
            help="'All' = compare all models side by side. Select one model to drill into its runs.",
        )
        if selected_model.startswith("All"):
            selected_model = None

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "**How to add a new model:**\n\n"
        "Run a backtest with the new model:\n"
        "`python runners/run_backtest.py --model qwen-max ...`\n\n"
        "It appears here automatically — no code changes needed."
    )
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Mint Green Main Repo Frontend | [GitHub]"
        "(https://github.com/Mint-green/llm-trading-benchmark)"
    )

    return selected, selected_model


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    inject_morandi_css()
    selected_page, model_filter = render_sidebar()

    render_func = PAGE_MAP[selected_page]

    with st.spinner(f"Loading {selected_page}..."):
        try:
            render_func(get_data_layer(), model_filter)
        except Exception as e:
            st.error(f"Error rendering page: {e}")
            st.exception(e)


if __name__ == "__main__":
    main()
