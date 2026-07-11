# AI-Trader Benchmark Frontend

**Mint Green 主仓库** (`https://github.com/Mint-green/llm-trading-benchmark`) 对应的前端可视化面板。

基于 Streamlit + Plotly，提供 6 个分析页面，支持多模型对比。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动前端
streamlit run frontend/app.py

# 3. 浏览器打开 http://localhost:8501
```

**首次启动前**，确保有一个回测产出的 `benchmark.db` 文件。最简方式：

```bash
# 将前端放在 blue 同级目录，前端会自动检测
ls ~/Desktop/
# AI-Trader-Frontend/   blue/   red/   ...

# 或手动指定:
export BENCHMARK_DB_PATH=~/Desktop/blue/output/results/benchmark.db
```

---

## 页面一览

| 页面 | 功能 | 需要的数据表 |
|------|------|------------|
| **1. Model Comparison** | 多模型 KPI 卡片、雷达图、成本-收益散点图、对比表格 | benchmark_runs |
| **2. Single Run Detail** | NAV 曲线、回撤图、持仓甘特图、市场敞口、交易日志 | portfolio_snapshots, trades |
| **3. Decision Analytics** | 决策时间线、工具调用分布、Token 用量、延迟分布、市场状态分析 | decisions, llm_calls, tool_calls, agent_rounds |
| **4. Cost & Efficiency** | 成本构成、效率排行榜、Token 效率、延迟深度分析 | benchmark_runs, llm_calls |
| **5. Trade Analysis** | P&L 分布、持仓时长 vs 盈亏散点、胜率分段、盈亏瀑布图 | trades |
| **6. Experiment Manager** | 回测配置表单、运行队列、实时日志、结果预览 | benchmark_runs |

---

## 目录结构

```
AI-Trader-Frontend/
├── .streamlit/
│   └── config.toml          # Streamlit 服务端配置
├── frontend/
│   ├── app.py               # 主入口，DB_PATH 配置，侧边栏导航
│   ├── data_layer.py        # 所有 SQL 查询集中管理，返回 pandas DataFrame
│   ├── components.py        # 可复用组件：KPI 卡片、Plotly 图表、Morandi 样式
│   └── page_modules/        # 6 个独立页面渲染器
│       ├── page1_overview.py      # 模型对比总览
│       ├── page2_detail.py        # 单次回测详情
│       ├── page3_decisions.py     # 决策过程分析
│       ├── page4_efficiency.py    # 成本与效率
│       ├── page5_trades.py        # 交易对分析
│       └── page6_experiment.py    # 实验管理
├── requirements.txt         # Python 依赖
├── HOW_TO_CONNECT.md        # 后端对接完整指南（必读）
└── README.md                # 本文件
```

---

## 数据流

```
后端 (blue/red)                 SQLite DB                  前端 (本文件夹)
───────────────                ──────────                  ────────────────
ExperimentLogger               benchmark.db               DataLayer
  .init_run()         ──写入──▶ benchmark_runs    ◀──读取──  .get_runs_summary()
  .log_llm_call()     ──写入──▶ llm_calls        ◀──读取──  .get_llm_calls()
  .log_tool_call()    ──写入──▶ tool_calls       ◀──读取──  .get_tool_calls()
  .log_decision()     ──写入──▶ decisions        ◀──读取──  .get_decisions()
  .log_trade()        ──写入──▶ trades           ◀──读取──  .get_trades()
  .log_snapshot()     ──写入──▶ portfolio_snapshots ◀──读取── .get_nav_series()
  .log_round()        ──写入──▶ agent_rounds     ◀──读取──  .get_agent_rounds()
```

前后端完全解耦，只通过 7 张 SQLite 表的结构约定通信。

---

## 对接你的后端项目

详细说明见 **[HOW_TO_CONNECT.md](./HOW_TO_CONNECT.md)**，包含：

- 数据流全链路（从 ExperimentRunner → SQLite → 前端页面）
- 7 张核心表的完整字段说明
- 4 种 DB 路径配置方式
- blue 项目兼容性矩阵
- 可选的增强列 SQL（提升前端展示效果）
- 多项目对比方案

---

## 添加新模型

无需改前端代码。用新模型跑回测后自动出现：

```bash
cd ~/Desktop/blue
python runners/run_backtest.py --model qwen-max --start 2026-02-03 --end 2026-03-03
```

---

## 技术栈

- **Streamlit** — Python 数据面板框架
- **Plotly** — 交互式图表（支持缩放、平移、hover 提示）
- **Pandas** — 数据处理
- **SQLite** — 数据存储（前后端共享）

---

## 配色

采用 **Morandi 色系** — 低饱和度、灰调底色，适合长时间盯盘分析：

| 颜色 | 用途 |
|------|------|
| `#7b8fa1` 灰蓝 | 主色调、US 市场 |
| `#8aa38a` 鼠尾草绿 | 盈利、HK 市场 |
| `#b8907a` 陶土色 | 亏损、CN 市场 |
| `#c4a882` 暖灰褐 | CRYPTO、警告 |
| `#f3f0ec` 暖米白 | 背景色 |

---

## 许可

Mint Green 主仓库项目。本前端文件夹为本地使用，不推送至 GitHub。
