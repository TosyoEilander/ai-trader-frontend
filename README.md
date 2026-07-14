# AI-Trader Benchmark Frontend

Frontend dashboard for the **Mint Green main repository** (`https://github.com/Mint-green/llm-trading-benchmark`).

Built with Streamlit + Plotly. 6 analysis pages, multi-model comparison support.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Launch frontend
streamlit run frontend/app.py

# 3. Open http://localhost:8501 in browser
```

**Before first launch**, make sure you have a `benchmark.db` file from a backtest run:

```bash
# Place this folder next to blue/ — it auto-detects the DB
ls ~/Desktop/
# AI-Trader-Frontend/   blue/   red/   ...

# Or specify manually:
export BENCHMARK_DB_PATH=~/Desktop/blue/output/results/benchmark.db
```

---

## Pages

| Page | Description | Tables Required |
|------|------|------------|
| **1. Model Comparison** | Multi-model KPI cards, radar chart, cost-return scatter, comparison table | benchmark_runs |
| **2. Single Run Detail** | NAV curve, drawdown chart, position Gantt, market exposure, trade log | portfolio_snapshots, trades |
| **3. Decision Analytics** | Decision timeline, tool usage distribution, token usage, latency, regime analysis | decisions, llm_calls, tool_calls, agent_rounds |
| **4. Cost & Efficiency** | Cost composition, efficiency leaderboard, token efficiency, latency deep-dive | benchmark_runs, llm_calls |
| **5. Trade Analysis** | P&L distribution, holding period vs P&L scatter, win rate segments, P&L waterfall | trades |
| **6. Experiment Manager** | Backtest config form, run queue, live log, results preview | benchmark_runs |

---

## Directory Structure

```
AI-Trader-Frontend/
├── .streamlit/
│   └── config.toml          # Streamlit server config
├── frontend/
│   ├── app.py               # Main entry, DB_PATH config, sidebar nav
│   ├── data_layer.py        # All SQL queries, returns pandas DataFrames
│   ├── components.py        # Reusable: KPI cards, Plotly charts, Morandi theme
│   └── page_modules/        # 6 individual page renderers
│       ├── page1_overview.py      # Model Comparison Dashboard
│       ├── page2_detail.py        # Single Run Detail
│       ├── page3_decisions.py     # Decision Process Analytics
│       ├── page4_efficiency.py    # Cost & Efficiency Analytics
│       ├── page5_trades.py        # Trade Pair Analysis
│       └── page6_experiment.py    # Experiment Manager
├── requirements.txt         # Python dependencies
├── HOW_TO_CONNECT.md        # Backend integration guide (required reading)
└── README.md                # This file
```

---

## Data Flow

```
Backend (blue/red)               SQLite DB                  Frontend (this folder)
─────────────────                ──────────                 ──────────────────────
ExperimentLogger                 benchmark.db               DataLayer
  .init_run()         ──write──▶ benchmark_runs    ◀──read──  .get_runs_summary()
  .log_llm_call()     ──write──▶ llm_calls        ◀──read──  .get_llm_calls()
  .log_tool_call()    ──write──▶ tool_calls       ◀──read──  .get_tool_calls()
  .log_decision()     ──write──▶ decisions        ◀──read──  .get_decisions()
  .log_trade()        ──write──▶ trades           ◀──read──  .get_trades()
  .log_snapshot()     ──write──▶ portfolio_snapshots ◀──read── .get_nav_series()
  .log_round()        ──write──▶ agent_rounds     ◀──read──  .get_agent_rounds()
```

Frontend and backend are fully decoupled — communication happens only through the 7-table SQLite schema.

---

## Connecting Your Backend

See **[HOW_TO_CONNECT.md](./HOW_TO_CONNECT.md)** for:

- Full data flow (from ExperimentRunner → SQLite → frontend pages)
- Complete field reference for 7 core tables
- 4 DB path configuration methods
- Blue project compatibility matrix
- Optional enhancement column SQL (improves frontend display)
- Multi-project comparison setup

---

## Adding a New Model

No frontend code changes needed. Run a backtest with the new model and it appears automatically:

```bash
cd ~/Desktop/blue
python runners/run_backtest.py --model qwen-max --start 2026-02-03 --end 2026-03-03
```

---

## Tech Stack

- **Streamlit** — Python data dashboard framework
- **Plotly** — Interactive charts (zoom, pan, hover tooltips)
- **Pandas** — Data processing
- **SQLite** — Data storage (shared between frontend and backend)

---

## Color Palette

**Morandi color scheme** — low saturation, gray undertones, suitable for extended analysis sessions:

| Color | Usage |
|------|------|
| `#7b8fa1` Dusty Blue | Primary, US market |
| `#8aa38a` Sage Green | Profit, HK market |
| `#b8907a` Terracotta | Loss, CN market |
| `#c4a882` Warm Taupe | CRYPTO, warnings |
| `#f3f0ec` Warm Off-White | Background |

---

## License

Mint Green main repository project. This frontend folder is for local use.
