"""
Data layer for AI-Trader Benchmark Frontend.
============================================
All database queries are centralized here. Each function accepts an optional
model filter — adding a new model requires zero changes to this layer.

Returns pandas DataFrames for direct use in Streamlit/Plotly.

Compatibility:
  Compatible with both red (v2) and blue (v3) backend database schemas.
  Automatically detects available columns on read; missing columns get
  default values rather than causing errors.

Usage:
    from frontend.data_layer import DataLayer
    dl = DataLayer("path/to/benchmark.db")
    df = dl.get_runs_summary(model="deepseek-v4-pro")
"""

from __future__ import annotations
import sqlite3
import pandas as pd
from pathlib import Path


class DataLayer:
    """Centralized data access layer for the benchmark frontend."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._schema_cache: dict[str, set[str]] = {}  # table -> set of column names

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
            self._schema_cache = {}

    def reload(self):
        """Close and reopen (for polling live updates)."""
        self.close()
        return self.conn

    def _get_columns(self, table: str) -> set[str]:
        """Get column names for a table (cached)."""
        if table not in self._schema_cache:
            try:
                rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
                self._schema_cache[table] = {r["name"] for r in rows}
            except sqlite3.OperationalError:
                self._schema_cache[table] = set()
        return self._schema_cache[table]

    def _safe_cols(self, table: str, desired: list[str]) -> list[str]:
        """Return columns from desired that actually exist in the table."""
        available = self._get_columns(table)
        return [c for c in desired if c in available]

    def _ensure_cols(self, df: pd.DataFrame, defaults: dict[str, object]) -> pd.DataFrame:
        """Fill missing columns in DataFrame with default values."""
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default
        return df

    def _query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """Run a query and return a DataFrame."""
        return pd.read_sql_query(sql, self.conn, params=params)

    # ------------------------------------------------------------------
    # Run-level queries
    # ------------------------------------------------------------------

    def get_runs_summary(self, model: str | None = None) -> pd.DataFrame:
        """Get summary of all completed runs, most recent first."""
        cols = self._safe_cols("benchmark_runs", [
            "run_id", "model", "start_date", "end_date", "interval_min",
            "initial_cash", "thinking_enabled", "status", "decisions_made",
            "total_decisions", "current_nav", "total_trades", "successful_trades",
            "api_cost_total", "trading_fees_total", "slippage_total", "total_cost",
            "total_prompt_tokens", "total_completion_tokens", "avg_latency_ms",
            "tokens_per_decision", "cost_per_decision", "return_per_dollar_cost",
            "result", "created_at",
        ])

        if not cols:
            return pd.DataFrame()

        where = "WHERE status = 'completed'"
        params: tuple = ()
        if model:
            where += " AND model = ?"
            params = (model,)

        cols_str = ", ".join(cols)
        sql = f"SELECT {cols_str} FROM benchmark_runs {where} ORDER BY created_at DESC"
        df = self._query(sql, params)
        # Fill missing enhanced columns with defaults (blue v3.1 compatibility)
        df = self._ensure_cols(df, {
            "api_cost_total": 0.0, "trading_fees_total": 0.0,
            "slippage_total": 0.0, "total_cost": 0.0,
            "total_prompt_tokens": 0, "total_completion_tokens": 0,
            "avg_latency_ms": 0.0, "tokens_per_decision": 0.0,
            "cost_per_decision": 0.0, "return_per_dollar_cost": 0.0,
            "result": "{}",
        })
        return df

    def get_all_runs_brief(self) -> pd.DataFrame:
        """Get brief info for all runs including running ones."""
        desired = [
            "run_id", "model", "start_date", "end_date", "status",
            "decisions_made", "current_nav", "total_trades", "successful_trades",
            "api_cost_total", "total_cost", "avg_latency_ms",
            "tokens_per_decision", "cost_per_decision", "return_per_dollar_cost",
        ]
        cols = self._safe_cols("benchmark_runs", desired)
        if not cols:
            return pd.DataFrame()
        df = self._query(
            f"SELECT {', '.join(cols)} FROM benchmark_runs ORDER BY created_at DESC"
        )
        df = self._ensure_cols(df, {
            "api_cost_total": 0.0, "total_cost": 0.0,
            "avg_latency_ms": 0.0, "tokens_per_decision": 0.0,
            "cost_per_decision": 0.0, "return_per_dollar_cost": 0.0,
        })
        return df

    def get_run_detail(self, run_id: str) -> dict:
        """Get full detail for a single run."""
        row = self.conn.execute(
            "SELECT * FROM benchmark_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else {}

    def get_run_list(self, model: str | None = None) -> list[str]:
        """Get list of run IDs for a model, newest first."""
        where = ""
        params: tuple = ()
        if model:
            where = "WHERE model = ?"
            params = (model,)
        rows = self.conn.execute(
            f"SELECT run_id FROM benchmark_runs {where} ORDER BY created_at DESC", params
        ).fetchall()
        return [r["run_id"] for r in rows]

    def get_available_models(self) -> list[str]:
        """Get distinct model names from the database."""
        rows = self.conn.execute(
            "SELECT DISTINCT model FROM benchmark_runs ORDER BY model"
        ).fetchall()
        return [r["model"] for r in rows]

    # ------------------------------------------------------------------
    # Portfolio / NAV queries
    # ------------------------------------------------------------------

    def get_nav_series(self, run_id: str) -> pd.DataFrame:
        """Get NAV time series with benchmark and index."""
        desired = [
            "timestamp", "nav", "cash", "benchmark_nav", "index_nav",
            "positions", "market_exposure",
        ]
        cols = self._safe_cols("portfolio_snapshots", desired)
        if not cols:
            return pd.DataFrame()
        return self._query(
            f"SELECT {', '.join(cols)} FROM portfolio_snapshots "
            f"WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        )

    # ------------------------------------------------------------------
    # Decision queries
    # ------------------------------------------------------------------

    def get_decisions(self, run_id: str) -> pd.DataFrame:
        """Get all decisions for a run with market context."""
        desired = [
            "id", "timestamp", "action", "trades", "reason", "portfolio_nav",
            "market_regime", "index_1h_pct", "index_1d_pct", "positions_before",
            "decision_type",
        ]
        cols = self._safe_cols("decisions", desired)
        if not cols:
            return pd.DataFrame()
        return self._query(
            f"SELECT {', '.join(cols)} FROM decisions "
            f"WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        )

    def get_trade_decisions(self, run_id: str) -> pd.DataFrame:
        """Get only trade decisions (action=trade)."""
        desired = [
            "timestamp", "trades", "reason", "portfolio_nav",
            "market_regime", "index_1h_pct", "index_1d_pct",
        ]
        cols = self._safe_cols("decisions", desired)
        if not cols:
            return pd.DataFrame()
        return self._query(
            f"SELECT {', '.join(cols)} FROM decisions "
            f"WHERE run_id = ? AND action = 'trade' ORDER BY timestamp",
            (run_id,),
        )

    def get_decisions_by_regime(self, run_id: str) -> pd.DataFrame:
        """Get aggregated decision stats by market regime."""
        if "market_regime" not in self._get_columns("decisions"):
            return pd.DataFrame()
        return self._query("""
            SELECT
                market_regime,
                COUNT(*) as decision_count,
                SUM(CASE WHEN action = 'trade' THEN 1 ELSE 0 END) as trade_count,
                SUM(CASE WHEN action = 'hold' THEN 1 ELSE 0 END) as hold_count,
                AVG(portfolio_nav) as avg_nav
            FROM decisions
            WHERE run_id = ?
            GROUP BY market_regime
            ORDER BY
                CASE market_regime
                    WHEN 'GREEN' THEN 1 WHEN 'YELLOW' THEN 2 WHEN 'RED' THEN 3
                    ELSE 4
                END
        """, (run_id,))

    # ------------------------------------------------------------------
    # Trade queries
    # ------------------------------------------------------------------

    def get_trades(self, run_id: str) -> pd.DataFrame:
        """Get all trades for a run."""
        desired = [
            "id", "timestamp", "symbol", "market", "side", "quantity",
            "price", "cost", "fees", "success", "error", "rejection_code",
            "buy_timestamp", "holding_minutes", "realized_pnl", "realized_pnl_pct",
        ]
        cols = self._safe_cols("trades", desired)
        if not cols:
            return pd.DataFrame()
        return self._query(
            f"SELECT {', '.join(cols)} FROM trades "
            f"WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        )

    def get_completed_trades(self, run_id: str) -> pd.DataFrame:
        """Get only completed sell trades with P&L."""
        desired = [
            "id", "timestamp", "symbol", "market", "side", "quantity",
            "price", "cost", "fees", "buy_timestamp", "holding_minutes",
            "realized_pnl", "realized_pnl_pct", "rejection_code", "success",
        ]
        cols = self._safe_cols("trades", desired)
        if not cols:
            return pd.DataFrame()
        return self._query(
            f"SELECT {', '.join(cols)} FROM trades "
            f"WHERE run_id = ? AND side = 'sell' AND success = 1 "
            f"ORDER BY timestamp",
            (run_id,),
        )

    def get_trade_pnl_summary(self, run_id: str) -> pd.DataFrame:
        """Get P&L summary by market."""
        if "realized_pnl" not in self._get_columns("trades"):
            return pd.DataFrame()
        return self._query("""
            SELECT
                market,
                COUNT(*) as trade_count,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                ROUND(AVG(realized_pnl), 2) as avg_pnl,
                ROUND(SUM(realized_pnl), 2) as total_pnl,
                ROUND(AVG(holding_minutes), 0) as avg_holding_min
            FROM trades
            WHERE run_id = ? AND side = 'sell' AND success = 1
            GROUP BY market
        """, (run_id,))

    def get_rejection_summary(self, run_id: str) -> pd.DataFrame:
        """Get trade rejection summary."""
        if "rejection_code" not in self._get_columns("trades"):
            # Fallback: use error field
            return self._query("""
                SELECT
                    error as rejection_code,
                    COUNT(*) as count
                FROM trades
                WHERE run_id = ? AND success = 0
                GROUP BY error
                ORDER BY count DESC
            """, (run_id,))
        return self._query("""
            SELECT
                rejection_code,
                COUNT(*) as count
            FROM trades
            WHERE run_id = ? AND success = 0 AND rejection_code != ''
            GROUP BY rejection_code
            ORDER BY count DESC
        """, (run_id,))

    # ------------------------------------------------------------------
    # LLM call queries
    # ------------------------------------------------------------------

    def get_llm_calls(self, run_id: str) -> pd.DataFrame:
        """Get all LLM calls for a run."""
        desired = [
            "id", "decision_timestamp", "round_num", "model",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "latency_ms", "reasoning", "response",
        ]
        cols = self._safe_cols("llm_calls", desired)
        if not cols:
            return pd.DataFrame()
        return self._query(
            f"SELECT {', '.join(cols)} FROM llm_calls "
            f"WHERE run_id = ? ORDER BY decision_timestamp, round_num",
            (run_id,),
        )

    def get_llm_round_summary(self, run_id: str) -> pd.DataFrame:
        """Get LLM call stats aggregated by round number."""
        if "round_num" not in self._get_columns("llm_calls"):
            return pd.DataFrame()
        return self._query("""
            SELECT
                round_num,
                COUNT(*) as call_count,
                ROUND(AVG(prompt_tokens), 0) as avg_prompt_tokens,
                ROUND(AVG(completion_tokens), 0) as avg_completion_tokens,
                ROUND(AVG(total_tokens), 0) as avg_total_tokens,
                ROUND(AVG(latency_ms), 0) as avg_latency_ms,
                ROUND(MAX(latency_ms), 0) as max_latency_ms,
                ROUND(MIN(latency_ms), 0) as min_latency_ms
            FROM llm_calls
            WHERE run_id = ?
            GROUP BY round_num
            ORDER BY round_num
        """, (run_id,))

    def get_token_timeline(self, run_id: str) -> pd.DataFrame:
        """Get token usage over time for trend analysis."""
        if "decision_timestamp" not in self._get_columns("llm_calls"):
            return pd.DataFrame()
        return self._query("""
            SELECT
                decision_timestamp,
                SUM(prompt_tokens) as prompt_tokens,
                SUM(completion_tokens) as completion_tokens,
                SUM(total_tokens) as total_tokens,
                ROUND(AVG(latency_ms), 0) as avg_latency_ms
            FROM llm_calls
            WHERE run_id = ?
            GROUP BY decision_timestamp
            ORDER BY decision_timestamp
        """, (run_id,))

    # ------------------------------------------------------------------
    # Tool call queries
    # ------------------------------------------------------------------

    def get_tool_calls(self, run_id: str) -> pd.DataFrame:
        """Get all tool calls for a run."""
        desired = [
            "id", "decision_timestamp", "round_num", "tool_name",
            "tool_args", "tool_result_summary", "latency_ms",
            "tool_result",
        ]
        cols = self._safe_cols("tool_calls", desired)
        if not cols:
            return pd.DataFrame()

        # Build ORDER BY dynamically based on available columns (blue vs red schema)
        order_parts = ["decision_timestamp"]
        if "round_num" in cols:
            order_parts.append("round_num")
        if "id" in cols:
            order_parts.append("id")
        elif "tool_call_id" in self._get_columns("tool_calls"):
            order_parts.append("tool_call_id")

        order_clause = ", ".join(order_parts)
        return self._query(
            f"SELECT {', '.join(cols)} FROM tool_calls "
            f"WHERE run_id = ? ORDER BY {order_clause}",
            (run_id,),
        )

    def get_tool_usage_summary(self, run_id: str) -> pd.DataFrame:
        """Get aggregated tool usage stats."""
        if "tool_name" not in self._get_columns("tool_calls"):
            return pd.DataFrame()
        return self._query("""
            SELECT
                tool_name,
                COUNT(*) as call_count,
                ROUND(AVG(latency_ms), 1) as avg_latency_ms,
                ROUND(SUM(latency_ms), 0) as total_latency_ms
            FROM tool_calls
            WHERE run_id = ?
            GROUP BY tool_name
            ORDER BY call_count DESC
        """, (run_id,))

    def get_tool_calls_by_round(self, run_id: str) -> pd.DataFrame:
        """Get tool call counts broken down by round."""
        if "round_num" not in self._get_columns("tool_calls"):
            return pd.DataFrame()
        return self._query("""
            SELECT
                round_num,
                tool_name,
                COUNT(*) as call_count,
                ROUND(AVG(latency_ms), 1) as avg_latency_ms
            FROM tool_calls
            WHERE run_id = ?
            GROUP BY round_num, tool_name
            ORDER BY round_num, call_count DESC
        """, (run_id,))

    # ------------------------------------------------------------------
    # Agent round queries
    # ------------------------------------------------------------------

    def get_agent_rounds(self, run_id: str) -> pd.DataFrame:
        """Get all agent rounds."""
        desired = [
            "id", "decision_timestamp", "round_num", "action",
            "llm_response", "tool_results", "latency_ms",
        ]
        cols = self._safe_cols("agent_rounds", desired)
        if not cols:
            return pd.DataFrame()
        return self._query(
            f"SELECT {', '.join(cols)} FROM agent_rounds "
            f"WHERE run_id = ? ORDER BY decision_timestamp, round_num",
            (run_id,),
        )

    # ------------------------------------------------------------------
    # Cross-model comparison queries
    # ------------------------------------------------------------------

    def get_model_comparison(self) -> pd.DataFrame:
        """Get aggregated metrics per model for comparison."""
        return self._query("""
            SELECT
                model,
                COUNT(*) as run_count,
                ROUND(AVG(current_nav - initial_cash) / AVG(initial_cash) * 100, 2) as avg_return_pct,
                ROUND(AVG(total_trades), 0) as avg_trades,
                ROUND(AVG(successful_trades), 0) as avg_successful
            FROM benchmark_runs
            WHERE status = 'completed'
            GROUP BY model
            ORDER BY avg_return_pct DESC
        """)

    # ------------------------------------------------------------------
    # Convenience: get all data for a run in one call
    # ------------------------------------------------------------------

    def get_run_package(self, run_id: str, model: str | None = None) -> dict[str, pd.DataFrame]:
        """Return a dict of all DataFrames for a single-run deep dive.

        Keys: nav, decisions, trades, completed_trades, llm_calls, tool_calls,
              tool_summary, token_timeline, rejection_summary, round_summary,
              regime_summary, pnl_by_market
        """
        return {
            "nav": self.get_nav_series(run_id),
            "decisions": self.get_decisions(run_id),
            "trades": self.get_trades(run_id),
            "completed_trades": self.get_completed_trades(run_id),
            "llm_calls": self.get_llm_calls(run_id),
            "tool_calls": self.get_tool_calls(run_id),
            "tool_summary": self.get_tool_usage_summary(run_id),
            "tool_calls_by_round": self.get_tool_calls_by_round(run_id),
            "token_timeline": self.get_token_timeline(run_id),
            "rejection_summary": self.get_rejection_summary(run_id),
            "round_summary": self.get_llm_round_summary(run_id),
            "regime_summary": self.get_decisions_by_regime(run_id),
            "pnl_by_market": self.get_trade_pnl_summary(run_id),
        }
