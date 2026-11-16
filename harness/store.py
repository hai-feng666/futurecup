"""追踪存储层：一次运行的完整可观测记录。

设计要点（对应赛题「执行日志 / 状态快照 / 结果校验 / 回滚」要求）：
- runs     : 一次运行一行，含配置快照、模型版本、总成本
- nodes    : 每个节点每个 attempt 一行，含调度决策、输出、tokens、耗时
- verdicts : 每次验证的结论、置信度、证据
- metrics  : 任意量化指标（评测与决赛量化对比直接取用）

只依赖 SQLite，评审专家不需要装数据库即可复现。
并发写入用一把进程内锁保护，保证 DAG 并行节点不会写坏 trace。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  flow TEXT, title TEXT, scenario TEXT, config TEXT,
  status TEXT, started TEXT, finished TEXT,
  total_tokens INTEGER DEFAULT 0, total_cost REAL DEFAULT 0,
  rounds INTEGER DEFAULT 0, success INTEGER
);
CREATE TABLE IF NOT EXISTS nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT, node_id TEXT, agent_id TEXT, role TEXT, attempt INTEGER,
  status TEXT, model TEXT,
  prompt_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0,
  latency_ms INTEGER DEFAULT 0, cost REAL DEFAULT 0,
  tool_calls TEXT, decision TEXT, output TEXT, error TEXT,
  started TEXT, finished TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT, node_id TEXT, verifier TEXT,
  passed INTEGER, confidence REAL, evidence TEXT, created TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT, name TEXT, value REAL
);
CREATE INDEX IF NOT EXISTS ix_nodes_run ON nodes(run_id);
CREATE INDEX IF NOT EXISTS ix_verdicts_run ON verdicts(run_id);
"""


class Store:
    def __init__(self, path: str | Path = "runs.db") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def _ex(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        with self._lock:
            self.conn.execute(sql, args)
            self.conn.commit()

    def close(self) -> None:
        """显式关闭连接（测试与长时间运行时避免 ResourceWarning）。"""
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass

    def _q(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # ---------- 写入 ----------
    def start_run(self, run_id: str, flow: str, title: str, scenario: str,
                  config: dict[str, Any], started: str) -> None:
        self._ex(
            "INSERT INTO runs(id,flow,title,scenario,config,status,started,rounds)"
            " VALUES(?,?,?,?,?,?,?,0)",
            (run_id, flow, title, scenario, json.dumps(config, ensure_ascii=False),
             "running", started),
        )

    def finish_run(self, run_id: str, status: str, finished: str,
                   total_tokens: int, total_cost: float, rounds: int,
                   success: bool | None) -> None:
        self._ex(
            "UPDATE runs SET status=?,finished=?,total_tokens=?,total_cost=?,rounds=?,"
            "success=? WHERE id=?",
            (status, finished, total_tokens, total_cost, rounds,
             None if success is None else int(success), run_id),
        )

    def add_node(self, run_id: str, node_id: str, agent_id: str, role: str,
                 attempt: int, status: str, model: str, prompt_tokens: int,
                 completion_tokens: int, latency_ms: int, cost: float,
                 tool_calls: list[str], output: str, error: str | None,
                 started: str, finished: str,
                 decision: dict[str, Any] | None = None) -> None:
        self._ex(
            "INSERT INTO nodes(run_id,node_id,agent_id,role,attempt,status,model,"
            "prompt_tokens,completion_tokens,latency_ms,cost,tool_calls,decision,"
            "output,error,started,finished) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, node_id, agent_id, role, attempt, status, model,
             prompt_tokens, completion_tokens, latency_ms, cost,
             json.dumps(tool_calls, ensure_ascii=False),
             json.dumps(decision or {}, ensure_ascii=False),
             output, error, started, finished),
        )

    def add_verdict(self, run_id: str, node_id: str, verifier: str, passed: bool,
                    confidence: float, evidence: Any, created: str) -> None:
        self._ex(
            "INSERT INTO verdicts(run_id,node_id,verifier,passed,confidence,evidence,created)"
            " VALUES(?,?,?,?,?,?,?)",
            (run_id, node_id, verifier, int(passed), confidence,
             json.dumps(evidence, ensure_ascii=False), created),
        )

    def add_metric(self, run_id: str, name: str, value: float) -> None:
        self._ex("INSERT INTO metrics(run_id,name,value) VALUES(?,?,?)",
                 (run_id, name, float(value)))

    # ---------- 读取（回放 + 控制台） ----------
    def run(self, run_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM runs WHERE id=?", (run_id,))
        return rows[0] if rows else None

    def runs(self, limit: int = 30) -> list[dict[str, Any]]:
        return self._q("SELECT * FROM runs ORDER BY started DESC LIMIT ?", (limit,))

    def nodes(self, run_id: str) -> list[dict[str, Any]]:
        return self._q("SELECT * FROM nodes WHERE run_id=? ORDER BY id", (run_id,))

    def verdicts(self, run_id: str) -> list[dict[str, Any]]:
        return self._q("SELECT * FROM verdicts WHERE run_id=? ORDER BY id", (run_id,))

    def metrics(self, run_id: str) -> dict[str, float]:
        rows = self._q("SELECT name,value FROM metrics WHERE run_id=?", (run_id,))
        return {r["name"]: r["value"] for r in rows}

    def export(self, run_id: str) -> dict[str, Any]:
        """导出一个完整快照，可搬到另一台机器回放。"""
        return {
            "run": self.run(run_id),
            "nodes": self.nodes(run_id),
            "verdicts": self.verdicts(run_id),
            "metrics": self.metrics(run_id),
        }

    def profile_stats(self) -> dict[str, dict[str, float]]:
        """从历史运行统计每个 Agent 的能力画像（调度器的输入）。"""
        rows = self._q(
            """
            SELECT n.agent_id AS agent_id,
                   COUNT(*) AS n,
                   AVG(CASE WHEN n.status='ok' THEN 1.0 ELSE 0.0 END) AS ok_rate,
                   AVG(n.latency_ms) AS avg_latency,
                   AVG(n.prompt_tokens + n.completion_tokens) AS avg_tokens,
                   AVG(n.cost) AS avg_cost
            FROM nodes n
            WHERE n.agent_id IS NOT NULL AND n.agent_id <> ''
            GROUP BY n.agent_id
            """
        )
        out: dict[str, dict[str, float]] = {}
        for r in rows:
            out[r["agent_id"]] = {
                "n": float(r["n"] or 0.0),
                "ok_rate": float(r["ok_rate"] or 0.0),
                "avg_latency": float(r["avg_latency"] or 0.0),
                "avg_tokens": float(r["avg_tokens"] or 0.0),
                "avg_cost": float(r["avg_cost"] or 0.0),
            }
        return out
