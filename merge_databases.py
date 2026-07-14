"""
Merge multiple benchmark SQLite databases into one for multi-model comparison.

Usage:
    python merge_databases.py --output merged.db db1.db db2.db db3.db ...

The first database in the list provides the base schema. All subsequent
databases are merged in by copying rows table by table, skipping auto-increment
IDs to avoid primary key conflicts.

Example:
    python merge_databases.py \\
        --output artifacts/runs/all_models.db \\
        artifacts/deepseek-v4-pro/run.db \\
        artifacts/mimo-v2.5-pro/run.db \\
        artifacts/qwen3.6-max/run.db \\
        artifacts/gpt-5.5/run.db
"""

from __future__ import annotations
import argparse
import os
import shutil
import sqlite3
from pathlib import Path

# Tables where we skip the auto-increment 'id' column when inserting
AUTO_ID_TABLES = {
    "llm_calls": "id",
    "decisions": "id",
    "trades": "id",
    "portfolio_snapshots": "id",
    "agent_rounds": "id",
    "futures_marks": "id",
    "futures_roll_events": "id",
}

# Tables with TEXT primary keys — use INSERT OR IGNORE to skip duplicates
TEXT_PK_TABLES = [
    "tool_calls",
    "decision_events",
    "active_plans",
    "plan_versions",
    "plan_triggers",
    "watchlist_items",
    "avoid_items",
    "daily_thesis_versions",
    "summaries",
    "metrics_daily",
    "run_checkpoints",
    "benchmark_runs",
]


def merge_db(src_path: str, dst_path: str) -> None:
    """Merge all tables from source DB into destination DB.

    Skips auto-increment ID columns on tables that have them.
    Uses INSERT OR IGNORE for TEXT primary key tables.
    """
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    src.row_factory = sqlite3.Row

    # Merge tables with auto-increment id column
    for table, id_col in AUTO_ID_TABLES.items():
        try:
            src_cols = [
                r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            dst_cols = [
                r[1] for r in dst.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            common = [c for c in src_cols if c in dst_cols and c != id_col]
            if not common:
                continue
            rows = src.execute(
                f"SELECT {','.join(common)} FROM {table}"
            ).fetchall()
            if not rows:
                continue
            placeholders = ",".join(["?"] * len(common))
            dst.executemany(
                f"INSERT INTO {table} ({','.join(common)}) VALUES ({placeholders})",
                [tuple(r) for r in rows],
            )
            dst.commit()
            print(f"  {table}: {len(rows)} rows")
        except Exception as e:
            print(f"  {table}: skipped ({e})")

    # Merge tables with TEXT primary key (no id conflict)
    for table in TEXT_PK_TABLES:
        try:
            src_cols = [
                r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            dst_cols = [
                r[1] for r in dst.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            common = [c for c in src_cols if c in dst_cols]
            if not common:
                continue
            rows = src.execute(
                f"SELECT {','.join(common)} FROM {table}"
            ).fetchall()
            if not rows:
                continue
            placeholders = ",".join(["?"] * len(common))
            dst.executemany(
                f"INSERT OR IGNORE INTO {table} ({','.join(common)}) VALUES ({placeholders})",
                [tuple(r) for r in rows],
            )
            dst.commit()
            print(f"  {table}: {len(rows)} rows")
        except Exception as e:
            print(f"  {table}: skipped ({e})")

    src.close()
    dst.close()


def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple benchmark SQLite databases for multi-model comparison"
    )
    parser.add_argument(
        "--output", "-o", required=True, help="Output merged database path"
    )
    parser.add_argument(
        "inputs", nargs="+", help="Input database files (first one is used as schema base)"
    )
    args = parser.parse_args()

    output = args.output
    inputs = args.inputs

    if len(inputs) < 2:
        print("ERROR: Need at least 2 databases to merge.")
        return

    # Remove existing output
    if os.path.exists(output):
        os.remove(output)

    # Copy first DB as schema base
    shutil.copy(inputs[0], output)
    print(f"Base: {os.path.basename(inputs[0])}")

    # Merge remaining DBs
    for db_path in inputs[1:]:
        name = os.path.basename(db_path)
        print(f"\nMerging: {name}")
        merge_db(db_path, output)

    # Show final summary
    dst = sqlite3.connect(output)
    dst.row_factory = sqlite3.Row
    print("\n=== Final State ===")
    for r in dst.execute(
        "SELECT model, current_nav, total_trades, decisions_made FROM benchmark_runs ORDER BY current_nav DESC"
    ).fetchall():
        print(
            f"  {r['model']:25s}  NAV=${r['current_nav']:,.0f}  "
            f"Trades={r['total_trades']:4d}  Decisions={r['decisions_made']:4d}"
        )
    for r in dst.execute(
        "SELECT model, COUNT(*) as cnt FROM llm_calls GROUP BY model"
    ).fetchall():
        print(f"  {r['model']:25s}  LLM calls: {r['cnt']}")
    dst.close()

    size_mb = os.path.getsize(output) / 1024 / 1024
    print(f"\nOutput: {output} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
