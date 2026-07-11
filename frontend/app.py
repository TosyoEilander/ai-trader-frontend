"""
AI-Trader Benchmark — Streamlit Frontend
=========================================
Mint Green 主仓库 (https://github.com/Mint-green/llm-trading-benchmark) 对应前端。

入口: streamlit run frontend/app.py

6 个页面:
  1. Model Comparison Dashboard  — 模型对比总览
  2. Single Run Detail           — 单次回测详情
  3. Decision Process Analytics  — 决策过程分析
  4. Cost & Efficiency Analytics — 成本与效率
  5. Trade Pair Analysis         — 交易对分析
  6. Experiment Manager          — 实验管理

架构:
  - data_layer.py  : 所有 SQL 查询 → pandas DataFrames
  - components.py  : 可复用图表、KPI 卡片、样式表格
  - page_modules/* : 各页面独立渲染器

对接后端:
  前端只读 SQLite 数据库。后端项目（如 blue）在回测时将数据写入
  SQLite 表，前端通过 DataLayer 读取展示。详见 HOW_TO_CONNECT.md
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 项目根目录（AI-Trader-Frontend/）
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

# Page config — 必须第一个 Streamlit 调用
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
# 数据库路径配置
# ---------------------------------------------------------------------------
# 优先级: 环境变量 > 自动检测 > 默认路径
#
# 自动检测顺序:
#   1. ../blue/output/results/bench_v2_weekD.db   (blue 项目)
#   2. ../red/output/results/benchmark.db          (red 项目)
#   3. ./output/results/benchmark.db               (本地)

def _resolve_db_path() -> str:
    """智能解析数据库路径。"""
    # 1. 环境变量优先
    env_path = os.environ.get("BENCHMARK_DB_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. 自动检测兄弟项目
    candidates = [
        PROJECT_ROOT.parent / "blue" / "output" / "results" / "bench_v2_weekD.db",
        PROJECT_ROOT.parent / "blue" / "output" / "results" / "benchmark.db",
        PROJECT_ROOT.parent / "red" / "output" / "results" / "benchmark.db",
        PROJECT_ROOT / "output" / "results" / "benchmark.db",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)

    # 3. 默认路径（即使不存在也返回，DataLayer 会给出友好提示）
    default = PROJECT_ROOT.parent / "blue" / "output" / "results" / "benchmark.db"
    return str(default)

DB_PATH = _resolve_db_path()


@st.cache_resource
def get_data_layer() -> DataLayer:
    """获取或创建 DataLayer 单例。"""
    return DataLayer(DB_PATH)


# ---------------------------------------------------------------------------
# 页面路由
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
# 侧边栏
# ---------------------------------------------------------------------------

def render_sidebar():
    """渲染侧边栏：导航 + 全局筛选器。"""
    st.sidebar.title("AI-Trader Benchmark")

    # 数据库状态
    st.sidebar.caption(f"DB: `{DB_PATH}`")
    if not os.path.exists(DB_PATH):
        st.sidebar.warning(
            "数据库文件未找到！\n\n"
            "请设置环境变量 `BENCHMARK_DB_PATH` 指向你的 benchmark.db，\n"
            "或运行一次回测生成数据。\n\n"
            "详见 `HOW_TO_CONNECT.md`"
        )

    # 导航
    selected = st.sidebar.radio(
        "Navigation",
        list(PAGE_MAP.keys()),
        index=0,
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")

    # 模型筛选
    dl = get_data_layer()
    try:
        models = dl.get_available_models()
    except Exception:
        models = []

    model_count = len(models)
    if model_count == 0:
        st.sidebar.info("暂无模型数据")
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
            help="'All' = 多模型对比。选单个模型可深入查看其回测。",
        )
        if selected_model.startswith("All"):
            selected_model = None

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "**如何添加新模型：**\n\n"
        "用新模型跑一次回测即可：\n"
        "`python runners/run_backtest.py --model qwen-max ...`\n\n"
        "自动出现在这里 — 无需改前端代码。"
    )
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Mint Green 主仓库前端 | [GitHub]"
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
