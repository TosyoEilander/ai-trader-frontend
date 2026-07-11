# 前端对接后端数据 — 完整指南

## 概述

本前端是 **Mint Green 主仓库** (`https://github.com/Mint-green/llm-trading-benchmark`) 对应的可视化面板。

**核心原理：前端不直接连接后端代码，而是通过 SQLite 数据库文件间接读取回测结果。** 前端只读取数据库，后端只写入数据库。两者通过共享的 SQLite 文件完成数据交换。

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────┐
│  后端项目     │ ──写入──▶│  SQLite DB 文件   │◀──读取──│  前端面板     │
│  (blue/red)  │         │  benchmark.db    │         │  (本文件夹)   │
└──────────────┘         └──────────────────┘         └──────────────┘
```

---

## 数据流全链路

### 第一步：后端写入数据（以 blue 项目为例）

回测运行时，`ExperimentRunner` 通过 `ExperimentLogger` 将每一步数据写入 SQLite：

```
ExperimentRunner.run()
  │
  ├─ logger.init_run()           → INSERT INTO benchmark_runs      (运行元数据)
  │
  ├─ 每个决策点:
  │   ├─ agent.run()             → 调用 LLM，获取决策
  │   ├─ logger.log_llm_call()   → INSERT INTO llm_calls           (API 调用记录)
  │   ├─ logger.log_tool_call()  → INSERT INTO tool_calls          (工具调用记录)
  │   ├─ logger.log_decision()   → INSERT INTO decisions           (决策记录)
  │   ├─ portfolio.process_order()
  │   │   └─ logger.log_trade()  → INSERT INTO trades              (交易记录)
  │   ├─ logger.log_round()      → INSERT INTO agent_rounds        (Agent 轮次)
  │   └─ logger.log_snapshot()   → INSERT INTO portfolio_snapshots (资产快照)
  │
  └─ logger.save_results()       → UPDATE benchmark_runs           (最终结果)
     logger.mark_completed()     → UPDATE benchmark_runs           (标记完成)
```

关键文件：
- `blue/src/platform/experiment.py` — 回测主循环，调用 logger 写入
- `blue/src/platform/logging.py` — ExperimentLogger，执行 SQL 写入
- `blue/src/agent/runner.py` — AgentRunner，产生 tool_call 和 llm_call

### 第二步：SQLite 数据库表结构

前端读取以下 **7 张核心表**：

#### 1. benchmark_runs — 运行元数据
| 列名 | 类型 | 说明 |
|------|------|------|
| run_id | TEXT PK | 运行 ID，如 `20260711_143022` |
| model | TEXT | 模型名，如 `deepseek-v4-pro` |
| start_date | TEXT | 回测开始日期 `2026-02-03` |
| end_date | TEXT | 回测结束日期 |
| interval_min | INTEGER | 决策间隔（分钟） |
| initial_cash | REAL | 初始资金 |
| thinking_enabled | BOOLEAN | 是否开启思考模式 |
| status | TEXT | running / completed / failed |
| decisions_made | INTEGER | 已做决策数 |
| current_nav | REAL | 当前净值 |
| total_trades | INTEGER | 总交易数 |
| successful_trades | INTEGER | 成功交易数 |
| config | TEXT | 配置 JSON |
| result | TEXT | 结果 JSON（含 sharpe, max_drawdown 等） |

**增强列（red 项目有，blue 项目部分缺失）：**
| 列名 | 说明 |
|------|------|
| api_cost_total | API 总费用 |
| trading_fees_total | 交易手续费总计 |
| total_cost | 总成本 |
| avg_latency_ms | 平均延迟 |
| tokens_per_decision | 每次决策平均 token |
| return_per_dollar_cost | 每美元成本回报 |

> 前端 DataLayer 会自动检测列是否存在，缺失列返回空 DataFrame 而非报错。

#### 2. llm_calls — LLM API 调用记录
| 列名 | 说明 |
|------|------|
| run_id | 所属运行 |
| decision_timestamp | 决策时间戳 |
| round_num | 轮次号 |
| model | 实际使用的 API 模型 |
| prompt_tokens | 输入 token 数 |
| completion_tokens | 输出 token 数 |
| total_tokens | 总 token 数 |
| latency_ms | 延迟（毫秒） |
| response | LLM 回复内容 |

#### 3. decisions — 决策记录
| 列名 | 说明 |
|------|------|
| run_id | 所属运行 |
| timestamp | 决策时间戳 |
| action | hold / trade / query |
| trades | 交易列表 JSON |
| reason | 决策理由 |
| portfolio_nav | 决策时净值 |
| market_regime | 市场状态 GREEN/YELLOW/RED（可选） |
| positions_before | 决策前持仓 JSON（可选） |

#### 4. trades — 交易记录
| 列名 | 说明 |
|------|------|
| run_id | 所属运行 |
| timestamp | 交易时间戳 |
| symbol | 股票/合约代码 |
| market | 市场 US/HK/CN/CRYPTO/GOLD/FUTURES |
| side | buy / sell |
| quantity | 数量 |
| price | 成交价 |
| cost | 成交金额 |
| fees | 手续费 |
| success | 0=失败 1=成功 |
| error | 失败原因 |
| rejection_code | 拒绝分类代码（可选） |
| realized_pnl | 已实现盈亏（可选） |
| holding_minutes | 持仓时长（可选） |

#### 5. portfolio_snapshots — 资产快照
| 列名 | 说明 |
|------|------|
| run_id | 所属运行 |
| timestamp | 快照时间 |
| cash | 现金余额 |
| nav | 总净值 |
| positions | 持仓 JSON |
| market_exposure | 各市场敞口 JSON |
| benchmark_nav | 等权基准净值（可选） |
| index_nav | 指数净值（可选） |

#### 6. agent_rounds — Agent 交互轮次
| 列名 | 说明 |
|------|------|
| run_id | 所属运行 |
| decision_timestamp | 决策时间戳 |
| round_num | 轮次号 |
| action | 动作类型 |
| llm_response | LLM 回复 |
| tool_results | 工具调用结果 |
| latency_ms | 延迟 |

#### 7. tool_calls — 工具调用详情
| 列名 | 说明 |
|------|------|
| run_id | 所属运行 |
| decision_timestamp | 决策时间戳 |
| round_num | 轮次号 |
| tool_name | 工具名 |
| tool_args | 工具参数 JSON |
| tool_result / tool_result_summary | 工具返回结果 |
| latency_ms | 延迟 |

### 第三步：前端读取数据

前端 DataLayer 通过 `sqlite3` + `pandas` 读取上述表：

```
Streamlit 页面
  │
  ├─ app.py ──→ DataLayer(db_path)        # 初始化连接
  │               │
  │               ├─ get_runs_summary()    → SELECT * FROM benchmark_runs
  │               ├─ get_nav_series()      → SELECT * FROM portfolio_snapshots
  │               ├─ get_trades()          → SELECT * FROM trades
  │               ├─ get_decisions()       → SELECT * FROM decisions
  │               ├─ get_llm_calls()       → SELECT * FROM llm_calls
  │               ├─ get_tool_calls()      → SELECT * FROM tool_calls
  │               └─ get_run_package()     → 以上所有的一键封装
  │
  └─ components.py ──→ Plotly 图表（NAV 曲线、盈亏瀑布图等）
       page_modules/* → 各页面渲染逻辑
```

---

## 如何让 blue（或任意后端项目）使用此前端

### 方法一：环境变量指定（推荐）

```bash
# Windows PowerShell
$env:BENCHMARK_DB_PATH = "C:\Users\TOSYO\Desktop\blue\output\results\bench_v2_weekD.db"
streamlit run frontend/app.py

# Linux/Mac/Git Bash
export BENCHMARK_DB_PATH="/c/Users/TOSYO/Desktop/blue/output/results/bench_v2_weekD.db"
streamlit run frontend/app.py
```

### 方法二：自动检测

前端 `app.py` 启动时会自动按以下顺序查找数据库：

1. `../blue/output/results/bench_v2_weekD.db`
2. `../blue/output/results/benchmark.db`
3. `../red/output/results/benchmark.db`
4. `./output/results/benchmark.db`

将本前端文件夹放在与 `blue` 同级的桌面目录即可自动检测。

### 方法三：软链接

```bash
# 在 AI-Trader-Frontend 下创建 output 目录并软链接 blue 的数据库
mkdir -p output/results
ln -s /c/Users/TOSYO/Desktop/blue/output/results/benchmark.db output/results/benchmark.db
```

### 方法四：修改 app.py 默认路径

编辑 `frontend/app.py` 中的 `_resolve_db_path()` 函数，添加自定义路径。

---

## blue 项目与前端兼容性

### 已兼容的内容

| 前端页面 | blue 数据支持 | 说明 |
|----------|:-----------:|------|
| Page 1: 模型对比 | ✅ | benchmark_runs 表完整 |
| Page 2: 单次详情 NAV 曲线 | ✅ | portfolio_snapshots 表完整 |
| Page 2: 交易日志 | ✅ | trades 表完整（含 error） |
| Page 3: 决策分析 | ✅ | decisions + agent_rounds |
| Page 3: LLM 调用分析 | ✅ | llm_calls 表完整 |
| Page 3: 工具调用分析 | ✅ | tool_calls 表完整（blue v3） |
| Page 4: 成本分析 | ⚠️ | 需增强列（见下方） |
| Page 5: 交易对分析 | ⚠️ | 需 P&L 列（见下方） |
| Page 6: 实验管理 | ⚠️ | 需 CLI 启动支持 |

### blue 需要增强的列（可选，不影响基本功能）

blue 的 `logging.py` 相比 red 缺失以下增强列。缺失时前端会自动回退显示或隐藏对应图表：

**benchmark_runs 表** — 影响 Page 4 成本分析：
```sql
ALTER TABLE benchmark_runs ADD COLUMN api_cost_total REAL DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN trading_fees_total REAL DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN slippage_total REAL DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN total_cost REAL DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN total_prompt_tokens INTEGER DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN total_completion_tokens INTEGER DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN avg_latency_ms REAL DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN tokens_per_decision REAL DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN cost_per_decision REAL DEFAULT 0;
ALTER TABLE benchmark_runs ADD COLUMN return_per_dollar_cost REAL DEFAULT 0;
```

**trades 表** — 影响 Page 5 交易对分析：
```sql
ALTER TABLE trades ADD COLUMN rejection_code TEXT DEFAULT '';
ALTER TABLE trades ADD COLUMN buy_timestamp TEXT DEFAULT '';
ALTER TABLE trades ADD COLUMN holding_minutes INTEGER DEFAULT 0;
ALTER TABLE trades ADD COLUMN realized_pnl REAL DEFAULT 0;
ALTER TABLE trades ADD COLUMN realized_pnl_pct REAL DEFAULT 0;
```

**decisions 表** — 影响市场状态分析：
```sql
ALTER TABLE decisions ADD COLUMN market_regime TEXT DEFAULT '';
ALTER TABLE decisions ADD COLUMN index_1h_pct REAL DEFAULT 0;
ALTER TABLE decisions ADD COLUMN index_1d_pct REAL DEFAULT 0;
ALTER TABLE decisions ADD COLUMN positions_before TEXT DEFAULT '';
```

**portfolio_snapshots 表** — 影响基准对比：
```sql
ALTER TABLE portfolio_snapshots ADD COLUMN benchmark_nav REAL DEFAULT 0;
ALTER TABLE portfolio_snapshots ADD COLUMN index_nav REAL DEFAULT 0;
```

> 这些增强在 red 项目的 `logging.py:_migrate_schema()` 中已有实现，可直接参考移植。

---

## 依赖安装

```bash
pip install streamlit pandas plotly numpy
```

或：

```bash
pip install -r requirements.txt
```

---

## 启动前端

```bash
cd ~/Desktop/AI-Trader-Frontend
streamlit run frontend/app.py
```

浏览器访问 `http://localhost:8501`

---

## 添加新模型

**无需修改前端代码。** 只需用新模型跑一次回测：

```bash
cd ~/Desktop/blue
python runners/run_backtest.py --model qwen-max --start 2026-02-03 --end 2026-03-03
```

新模型的 run_id 会自动写入 `benchmark_runs` 表，前端侧边栏下拉框自动出现。

---

## 同时对比多个后端项目

如果 blue 和 red 分别有各自的 benchmark.db，最简单的方式是将它们合并到一个目录：

```bash
mkdir -p ~/Desktop/benchmark_results
cp ~/Desktop/blue/output/results/benchmark.db ~/Desktop/benchmark_results/blue_benchmark.db
cp ~/Desktop/red/output/results/benchmark.db ~/Desktop/benchmark_results/red_benchmark.db
```

然后分别启动两个前端实例（不同端口）：

```bash
# 终端 1 — 看 blue
BENCHMARK_DB_PATH=~/Desktop/benchmark_results/blue_benchmark.db streamlit run frontend/app.py --server.port 8501

# 终端 2 — 看 red
BENCHMARK_DB_PATH=~/Desktop/benchmark_results/red_benchmark.db streamlit run frontend/app.py --server.port 8502
```

---

## 架构总结

```
                    Mint Green 主仓库
===========================================================

┌─────────────────────────────────────────────────────────┐
│                    blue (v3.1 后端)                      │
│                                                         │
│  src/platform/experiment.py    回测主循环                │
│  src/platform/logging.py       → 写入 SQLite             │
│  src/agent/runner.py           → LLM 调用 + 工具调用      │
│  src/portfolio/portfolio.py    → 交易执行                │
│                                                         │
│  输出: output/results/benchmark.db                       │
└──────────────────────┬──────────────────────────────────┘
                       │ SQLite 文件
                       ▼
┌─────────────────────────────────────────────────────────┐
│           本文件夹 (AI-Trader-Frontend)                  │
│                                                         │
│  frontend/app.py               Streamlit 入口            │
│  frontend/data_layer.py        SQL → pandas DataFrame   │
│  frontend/components.py        Plotly 图表 + KPI 卡片    │
│  frontend/page_modules/        6 个分析页面             │
│                                                         │
│  读取: ~/Desktop/blue/output/results/benchmark.db        │
└─────────────────────────────────────────────────────────┘
```

前端与后端完全解耦，只通过 SQLite 表结构约定通信。任何产生相同表结构的回测项目都可以对接。
