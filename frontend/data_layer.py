"""
Data layer for AI-Trader Benchmark Frontend.
============================================
所有数据库查询集中在此。每个函数接受可选的 model 参数筛选模型，
新增模型无需修改此层 — 只需从 UI 传入不同 model 名。

返回 pandas DataFrames，供 Streamlit / Plotly 直接使用。

兼容性:
  同时兼容 red 项目（v2）和 blue 项目（v3）的数据库 schema。
  查询时自动检测可用列，缺失列返回默认值而不报错。

用法:
    from frontend.data_layer import DataLayer
    dl = DataLayer("path/to/benchmark.db")
    df = dl.get_runs_summary(model="deepseek-v4-pro")
"""

from __future__ import annotations
import sqlite3
import pandas as pd
from pathlib import Path


class DataLayer:
    """集中式数据访问层，为前端提供所有数据。"""

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
        """关闭并重新打开（用于轮询实时更新）。"""
        self.close()
        return self.conn

    def _get_columns(self, table: str) -> set[str]:
        """获取表的列名集合（缓存）。"""
        if table not in self._schema_cache:
            try:
                rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
                self._schema_cache[table] = {r["name"] for r in rows}
            except sqlite3.OperationalError:
                self._schema_cache[table] = set()
        return self._schema_cache[table]

    def _safe_cols(self, table: str, desired: list[str]) -> list[str]:
        """返回 desired 中实际存在于 table 的列名列表。"""
        available = self._get_columns(table)
        return [c for c in desired if c in available]

    def _ensure_cols(self, df: pd.DataFrame, defaults: dict[str, object]) -> pd.DataFrame:
        """为 DataFrame 填充缺失列（默认值）。"""
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default
        return df

    def _query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """执行查询并返回 DataFrame。"""
        return pd.read_sql_query(sql, self.conn, params=params)

    # ------------------------------------------------------------------
    # Run-level queries
    # ------------------------------------------------------------------

    def get_runs_summary(self, model: str | None = None) -> pd.DataFrame:
        """获取所有已完成运行的摘要，按最近优先排列。"""
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
        """获取所有运行（含运行中）的简要信息。"""
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
        """获取单次运行的完整详情。"""
        row = self.conn.execute(
            "SELECT * FROM benchmark_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else {}

    def get_run_list(self, model: str | None = None) -> list[str]:
        """获取运行 ID 列表（最新优先）。"""
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
        """获取数据库中所有不重复的模型名称。"""
        rows = self.conn.execute(
            "SELECT DISTINCT model FROM benchmark_runs ORDER BY model"
        ).fetchall()
        return [r["model"] for r in rows]

    # ------------------------------------------------------------------
    # Portfolio / NAV queries
    # ------------------------------------------------------------------

    def get_nav_series(self, run_id: str) -> pd.DataFrame:
        """获取 NAV 时间序列（含基准和指数）。"""
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
        """获取所有决策（含市场背景）。"""
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
        """仅获取含交易的决策。"""
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
        """按市场状态聚合决策统计。"""
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
        """获取所有交易记录。"""
        desired = [
            "id", "timestamp", "symbol", "market", "side", "quantity",
            "price", "cost", "fees", "success", "error", "rejection_code",
            "buy_timestamp", "holding_minutes", "realized_pnl", "realized_pnl_pct",
        ]
        cols = self._safe_cols("trades", desired)
        if not cols:
            return pd.DataFrame()
        df = self._query(
            f"SELECT {', '.join(cols)} FROM trades "
            f"WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        )
        df = self._ensure_cols(df, {
            "realized_pnl": 0.0, "realized_pnl_pct": 0.0,
            "holding_minutes": 0, "rejection_code": "",
        })
        return df

    def get_completed_trades(self, run_id: str) -> pd.DataFrame:
        """仅获取已完成的卖出交易（含 P&L）。"""
        desired = [
            "id", "timestamp", "symbol", "market", "side", "quantity",
            "price", "cost", "fees", "buy_timestamp", "holding_minutes",
            "realized_pnl", "realized_pnl_pct", "rejection_code", "success",
        ]
        cols = self._safe_cols("trades", desired)
        if not cols:
            return pd.DataFrame()
        df = self._query(
            f"SELECT {', '.join(cols)} FROM trades "
            f"WHERE run_id = ? AND side = 'sell' AND success = 1 "
            f"ORDER BY timestamp",
            (run_id,),
        )
        df = self._ensure_cols(df, {
            "realized_pnl": 0.0, "realized_pnl_pct": 0.0,
            "holding_minutes": 0, "rejection_code": "",
        })
        return df

    def get_trade_pnl_summary(self, run_id: str) -> pd.DataFrame:
        """按市场汇总 P&L。"""
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
        """获取交易拒绝汇总。"""
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
        """获取所有 LLM 调用记录。"""
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
        """按轮次聚合 LLM 调用统计。"""
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
        """获取 Token 用量时间线。"""
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
        """获取所有工具调用记录。"""
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
        """获取工具使用频率汇总。"""
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
        """按轮次拆分工具调用。"""
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
        """获取所有 agent 轮次记录。"""
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
        """获取模型级别的聚合对比指标。"""
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
        """一键获取单次运行的完整数据包。

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
