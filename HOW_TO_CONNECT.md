# Frontend-Backend Integration — Complete Guide

## Overview

This frontend is for the **Mint Green main repository** (`https://github.com/Mint-green/llm-trading-benchmark`) visualization dashboard.

**Core principle: the frontend does not connect to backend code directly — it reads backtest results from SQLite database files.** The frontend only reads; the backend only writes. They communicate through shared SQLite files.

```
┌──────────────┐            ┌──────────────────┐          ┌──────────────────────────┐
│  Backend     │ ──write──▶│  SQLite DB File   │◀──read──│  Frontend Dashboard      │
│  (blue/red)  │            │  benchmark.db    │          │  (this folder)           │
└──────────────┘            └──────────────────┘          └──────────────────────────┘
```

---

## Full Data Flow

### Step 1: Backend Writes Data (blue project example)

During backtesting, `ExperimentRunner` writes every step through `ExperimentLogger` into SQLite:

```
ExperimentRunner.run()
  │
  ├─ logger.init_run()           → INSERT INTO benchmark_runs      (Run metadata)
  │
  ├─ each decision point:
  │   ├─ agent.run()             → call LLM, get decision
  │   ├─ logger.log_llm_call()   → INSERT INTO llm_calls           (API call records)
  │   ├─ logger.log_tool_call()  → INSERT INTO tool_calls          (Tool call records)
  │   ├─ logger.log_decision()   → INSERT INTO decisions           (Decision records)
  │   ├─ portfolio.process_order()
  │   │   └─ logger.log_trade()  → INSERT INTO trades              (Trade records)
  │   ├─ logger.log_round()      → INSERT INTO agent_rounds        (Agent rounds)
  │   └─ logger.log_snapshot()   → INSERT INTO portfolio_snapshots (Portfolio snapshots)
  │
  └─ logger.save_results()       → UPDATE benchmark_runs           (Final results)
     logger.mark_completed()     → UPDATE benchmark_runs           (Mark completed)
```

Key files:
- `blue/src/platform/experiment.py` — Backtest main loop, calls logger to write
- `blue/src/platform/logging.py` — ExperimentLogger, executes SQL writes
- `blue/src/agent/runner.py` — AgentRunner, produces tool_call and llm_call data

### Step 2: SQLite Database Schema

The frontend reads the following **7 core tables**:

#### 1. benchmark_runs — Run metadata
| Column | Type | Description |
|------|------|------|
| run_id | TEXT PK | Run ID, e.g. `20260711_143022` |
| model | TEXT | Model name, e.g. `deepseek-v4-pro` |
| start_date | TEXT | Backtest start date `2026-02-03` |
| end_date | TEXT | Backtest end date |
| interval_min | INTEGER | Decision interval (minutes) |
| initial_cash | REAL | Initial capital |
| thinking_enabled | BOOLEAN | Thinking mode on/off |
| status | TEXT | running / completed / failed |
| decisions_made | INTEGER | Decisions made |
| current_nav | REAL | Current NAV |
| total_trades | INTEGER | Total trades |
| successful_trades | INTEGER | Successful trades |
| config | TEXT | Config JSON |
| result | TEXT | Result JSON (sharpe, max_drawdown, etc.) |

**Enhanced columns (present in red, partially missing in blue)：**
| Column | Description |
|------|------|
| api_cost_total | Total API cost |
| trading_fees_total | Total trading fees |
| total_cost | Total cost |
| avg_latency_ms | Avg Latency |
| tokens_per_decision | Avg tokens per decision |
| return_per_dollar_cost | Return per dollar cost |

> The frontend DataLayer auto-detects column existence. Missing columns return empty DataFrames rather than throwing errors.

#### 2. llm_calls — LLM API call records
| Column | Description |
|------|------|
| run_id | Parent run |
| decision_timestamp | Decision timestamp |
| round_num | Round number |
| model | Actual API model used |
| prompt_tokens | Input token count |
| completion_tokens | Output token count |
| total_tokens | Total token count |
| latency_ms | Latency (ms) |
| response | LLM response content |

#### 3. decisions — Decision records
| Column | Description |
|------|------|
| run_id | Parent run |
| timestamp | Decision timestamp |
| action | hold / trade / query |
| trades | Trade list JSON |
| reason | Decision reason |
| portfolio_nav | NAV at decision time |
| market_regime | Market regime GREEN/YELLOW/RED (optional) |
| positions_before | Positions before decision JSON (optional) |

#### 4. trades — Trade records
| Column | Description |
|------|------|
| run_id | Parent run |
| timestamp | Trade timestamp |
| symbol | Ticker/contract symbol |
| market | Market: US/HK/CN/CRYPTO/GOLD/FUTURES |
| side | buy / sell |
| quantity | Quantity |
| price | Fill price |
| cost | Fill cost |
| fees | Fees |
| success | 0=Failed 1=Success |
| error | Failure reason |
| rejection_code | Rejection code (optional) |
| realized_pnl | Realized P&L (optional) |
| holding_minutes | Holding minutes (optional) |

#### 5. portfolio_snapshots — Portfolio snapshots
| Column | Description |
|------|------|
| run_id | Parent run |
| timestamp | Snapshot timestamp |
| cash | Cash balance |
| nav | Total NAV |
| positions | Positions JSON |
| market_exposure | Market exposure JSON |
| benchmark_nav | Equal-weight benchmark NAV (optional) |
| index_nav | Index NAV (optional) |

#### 6. agent_rounds — Agent interaction rounds
| Column | Description |
|------|------|
| run_id | Parent run |
| decision_timestamp | Decision timestamp |
| round_num | Round number |
| action | Action type |
| llm_response | LLM response |
| tool_results | Tool results |
| latency_ms | Latency |

#### 7. tool_calls — Tool call details
| Column | Description |
|------|------|
| run_id | Parent run |
| decision_timestamp | Decision timestamp |
| round_num | Round number |
| tool_name | Tool name |
| tool_args | Tool arguments JSON |
| tool_result / tool_result_summary | Tool result |
| latency_ms | Latency |

### Step 3: Frontend Reads Data

The frontend DataLayer reads the above tables via `sqlite3` + `pandas`:

```
Streamlit Page
  │
  ├─ app.py ──→ DataLayer(db_path)        # Initialize connection
  │               │
  │               ├─ get_runs_summary()    → SELECT * FROM benchmark_runs
  │               ├─ get_nav_series()      → SELECT * FROM portfolio_snapshots
  │               ├─ get_trades()          → SELECT * FROM trades
  │               ├─ get_decisions()       → SELECT * FROM decisions
  │               ├─ get_llm_calls()       → SELECT * FROM llm_calls
  │               ├─ get_tool_calls()      → SELECT * FROM tool_calls
  │               └─ get_run_package()     → All-in-one convenience wrapper for the above
  │
  └─ components.py ──→ Plotly charts (NAV curve, P&L waterfall, etc.)
       page_modules/* → Page rendering logic
```

---

## How to Use This Frontend with Blue (or Any Backend)

### Method 1: Environment Variable (Recommended)

```bash
# Windows PowerShell
$env:BENCHMARK_DB_PATH = "C:\Users\TOSYO\Desktop\blue\output\results\bench_v2_weekD.db"
streamlit run frontend/app.py

# Linux/Mac/Git Bash
export BENCHMARK_DB_PATH="/c/Users/TOSYO/Desktop/blue/output/results/bench_v2_weekD.db"
streamlit run frontend/app.py
```

### Method 2: Auto-Detection

On startup, `app.py` searches for databases in this order:

1. `../blue/output/results/bench_v2_weekD.db`
2. `../blue/output/results/benchmark.db`
3. `../red/output/results/benchmark.db`
4. `./output/results/benchmark.db`

Place this folder next to `blue` on the desktop and it auto-detects.

### Method 3: Symlink

```bash
# Create output dir under AI-Trader-Frontend and symlink blue database
mkdir -p output/results
ln -s /c/Users/TOSYO/Desktop/blue/output/results/benchmark.db output/results/benchmark.db
```

### Method 4: Edit app.py Default Path

Edit the `_resolve_db_path()` function in `frontend/app.py` to add custom paths.

---

## Blue Project Compatibility

### Compatible Features

| Frontend Page | Blue Support | Description |
|----------|:-----------:|------|
| Page 1: Model Comparison | Yes | benchmark_runs table complete |
| Page 2: Single Run NAV Curve | Yes | portfolio_snapshots table complete |
| Page 2: Trade Log | Yes | trades table complete (incl. error) |
| Page 3: Decision Analytics | Yes | decisions + agent_rounds |
| Page 3: LLM Call Analysis | Yes | llm_calls table complete |
| Page 3: Tool Call Analysis | Yes | tool_calls table complete (blue v3) |
| Page 4: Cost Analysis | Partial | Needs enhanced columns (see below) |
| Page 5: Trade Pair Analysis | Partial | Needs P&L columns (see below) |
| Page 6: Experiment Manager | Partial | Needs CLI launch support |

### Blue Enhancement Columns (Optional — Core Features Work Without Them)

Blue logging.py lacks the following enhanced columns compared to red. When missing, the frontend gracefully degrades or hides affected charts:

**benchmark_runs table** — Affects Page 4 cost analysis:
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

**trades table** — Affects Page 5 trade analysis:
```sql
ALTER TABLE trades ADD COLUMN rejection_code TEXT DEFAULT '';
ALTER TABLE trades ADD COLUMN buy_timestamp TEXT DEFAULT '';
ALTER TABLE trades ADD COLUMN holding_minutes INTEGER DEFAULT 0;
ALTER TABLE trades ADD COLUMN realized_pnl REAL DEFAULT 0;
ALTER TABLE trades ADD COLUMN realized_pnl_pct REAL DEFAULT 0;
```

**decisions table** — Affects market regime analysis:
```sql
ALTER TABLE decisions ADD COLUMN market_regime TEXT DEFAULT '';
ALTER TABLE decisions ADD COLUMN index_1h_pct REAL DEFAULT 0;
ALTER TABLE decisions ADD COLUMN index_1d_pct REAL DEFAULT 0;
ALTER TABLE decisions ADD COLUMN positions_before TEXT DEFAULT '';
```

**portfolio_snapshots table** — Affects benchmark comparison:
```sql
ALTER TABLE portfolio_snapshots ADD COLUMN benchmark_nav REAL DEFAULT 0;
ALTER TABLE portfolio_snapshots ADD COLUMN index_nav REAL DEFAULT 0;
```

> These enhancements are already implemented in the red project logging.py:_migrate_schema() for reference.

---

## Dependencies

```bash
pip install streamlit pandas plotly numpy
```

Or:

```bash
pip install -r requirements.txt
```

---

## Launch Frontend

```bash
cd ~/Desktop/AI-Trader-Frontend
streamlit run frontend/app.py
```

Open `http://localhost:8501`

---

## Adding a New Model

**No frontend code changes needed.** Just run a backtest with the new model:

```bash
cd ~/Desktop/blue
python runners/run_backtest.py --model qwen-max --start 2026-02-03 --end 2026-03-03
```

The new model run_id is automatically written to the benchmark_runs table and appears in the sidebar dropdown.

---

## Comparing Multiple Backend Projects Simultaneously

If blue and red each have their own benchmark.db, the simplest approach is to place them in one directory:

```bash
mkdir -p ~/Desktop/benchmark_results
cp ~/Desktop/blue/output/results/benchmark.db ~/Desktop/benchmark_results/blue_benchmark.db
cp ~/Desktop/red/output/results/benchmark.db ~/Desktop/benchmark_results/red_benchmark.db
```

Then launch two frontend instances (different ports):

```bash
# Terminal 1 — View blue
BENCHMARK_DB_PATH=~/Desktop/benchmark_results/blue_benchmark.db streamlit run frontend/app.py --server.port 8501

# Terminal 2 — View red
BENCHMARK_DB_PATH=~/Desktop/benchmark_results/red_benchmark.db streamlit run frontend/app.py --server.port 8502
```

---

## Architecture Summary

```
                    Mint Green Main Repo
===========================================================

┌─────────────────────────────────────────────────────────┐
│                    blue (v3.1 backend)                  │
│                                                         │
│  src/platform/experiment.py    Backtest main loop       │
│  src/platform/logging.py       → write SQLite           │
│  src/agent/runner.py           → LLM calls + tool calls │
│  src/portfolio/portfolio.py    → Trade execution        │
│                                                         │
│  Output: output/results/benchmark.db                    │
└──────────────────────┬──────────────────────────────────┘
                       │ SQLite file
                       ▼
┌─────────────────────────────────────────────────────────┐
│           this folder (AI-Trader-Frontend)              │
│                                                         │
│  frontend/app.py               Streamlit entry          │
│  frontend/data_layer.py        SQL → pandas DataFrame   │
│  frontend/components.py        Plotly charts + KPI cards│
│  frontend/page_modules/        6 analysis pages         │
│                                                         │
│  read: ~/Desktop/blue/output/results/benchmark.db       │
└─────────────────────────────────────────────────────────┘
```

Frontend and backend are fully decoupled, communicating only through the SQLite table schema. Any backtest project producing the same table structure can integrate.
