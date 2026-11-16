"""DAG 执行引擎 + 自循环（执行 → 验证 → 修正）。

刻意不依赖任何 Agent 框架（LangChain / Dify 等），原因写在方案书里：
赛题要求「禁止直接套用现成框架的默认示例」，且调度与验证策略必须是自己的。
自研一个约 300 行的 DAG 引擎，比适配框架更快，也让每一行都可解释。

支持的控制结构：
- 顺序 / 并行（同一深度层的节点并发执行）
- 条件分支（when 表达式，针对事实表求值）
- 循环迭代（节点级 max_attempts + 返修意见回灌）
- 子流程（node 里写 flow，递归执行）
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import scheduler
from . import verify as V
from .models import Backend, get_backend
from .store import Store
from .tools import facts_as_text, run_tool
from .util import load_json, now_iso, project_root, rid, safe_format

ROOT = project_root()
MAX_WORKERS = 4


# --------------------------------------------------------------------------
# 流程定义
# --------------------------------------------------------------------------
def load_flow(path: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path, dict):
        return path
    return load_json(path)


def infer_deps(flow: dict[str, Any]) -> dict[str, list[str]]:
    ids = [n["id"] for n in flow["nodes"]]
    deps: dict[str, list[str]] = {}
    for n in flow["nodes"]:
        if "depends_on" in n:
            deps[n["id"]] = list(n["depends_on"])
            continue
        refs = [i for i in ids if i != n["id"] and ("{" + i + "}") in n.get("task", "")]
        deps[n["id"]] = refs
    return deps


def levels_of(flow: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """按依赖深度分层：同一层内可以并行。"""
    deps = infer_deps(flow)
    nodes = {n["id"]: n for n in flow["nodes"]}
    depth: dict[str, int] = {}

    def walk(nid: str, stack: tuple[str, ...] = ()) -> int:
        if nid in depth:
            return depth[nid]
        if nid in stack:
            raise ValueError(f"检测到循环依赖：{' → '.join(stack + (nid,))}")
        d = 0
        for dep in deps.get(nid, []):
            d = max(d, walk(dep, stack + (nid,)) + 1)
        depth[nid] = d
        return d

    for nid in nodes:
        walk(nid)
    out: dict[int, list[dict[str, Any]]] = {}
    for nid, d in depth.items():
        out.setdefault(d, []).append(nodes[nid])
    return [out[k] for k in sorted(out)]


def eval_when(expr: str | None, facts: dict[str, Any]) -> bool:
    """极简条件求值：`outlier_count > 0` 这种形式，故意不引入 eval()。"""
    if not expr:
        return True
    import re
    m = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)\s*", expr)
    if not m:
        return True
    key, op, rhs = m.group(1), m.group(2), float(m.group(3))
    lhs = float(facts.get(key, 0) or 0)
    return {
        ">": lhs > rhs, ">=": lhs >= rhs, "<": lhs < rhs,
        "<=": lhs <= rhs, "==": lhs == rhs, "!=": lhs != rhs,
    }[op]


# --------------------------------------------------------------------------
# 执行器
# --------------------------------------------------------------------------
class Executor:
    def __init__(self, store: Store, backend: Backend | None = None,
                 agents_path: str | Path | None = None) -> None:
        self.store = store
        self.backend = backend or get_backend()
        cfg = load_json(agents_path or (ROOT / "config" / "agents.json"))
        self.agents: list[dict[str, Any]] = cfg["agents"]
        self.scenario = cfg.get("scenario", "")
        self.load: dict[str, int] = {}
        self._load_lock = threading.Lock()
        self.evidence_nums: list[float] = []   # 本次运行所有工具输出出现过的数值
        self.evidence_chunks: list[str] = []   # 工具输出原文（供审校节点核对）
        self.force_fault = os.getenv("HARNESS_FORCE_FAULT", "0") == "1"
        self.verbose = True
        self._reset_totals()

    def _say(self, msg: str) -> None:
        """实时进度输出。真模型一次调用就要几十秒，没有进度条会让人以为卡死。"""
        if self.verbose:
            print(msg, flush=True)

    def _reset_totals(self) -> None:
        self.total_tokens = 0
        self.total_cost = 0.0
        self.human_interventions = 0
        self.attempts = 0
        self.evidence_nums = []
        self.evidence_chunks = []

    def agent(self, aid: str) -> dict[str, Any]:
        for a in self.agents:
            if a["id"] == aid:
                return a
        raise KeyError(f"未定义的 Agent：{aid}")

    def _bump_load(self, aid: str, delta: int) -> None:
        with self._load_lock:
            self.load[aid] = max(0, self.load.get(aid, 0) + delta)

    def _cost(self, ag: dict[str, Any], pt: int, ct: int) -> float:
        return round(pt / 1000 * ag.get("cost_per_1k_in", 0.0)
                     + ct / 1000 * ag.get("cost_per_1k_out", 0.0), 6)

    # ---------------- 一次完整运行 ----------------
    def run(self, flow: str | Path | dict[str, Any], inputs: dict[str, Any] | None = None,
            mode: str = "harness") -> dict[str, Any]:
        flow = load_flow(flow)
        run_inputs = {**flow.get("inputs", {}), **(inputs or {})}
        dataset = run_inputs.get("dataset", "data/sales.csv")
        facts = run_tool("csv_profile", {"dataset": dataset})["data"]

        self._reset_totals()
        self.load = {a["id"]: 0 for a in self.agents}
        run_id = rid()
        t0 = time.time()
        config = {
            "mode": mode,
            "backend": self.backend.name,
            "max_attempts": 1 if mode != "harness" else int(flow.get("max_rounds", 3)),
            "flow_version": flow.get("version", 1),
            "generated_at": now_iso(),
        }
        self.store.start_run(run_id, flow.get("name", "flow"), flow.get("title", ""),
                             self.scenario, config, now_iso())

        ctx: dict[str, Any] = dict(run_inputs)
        max_attempts = config["max_attempts"]
        budget = float(flow.get("budget_tokens", 10**9))
        self.stats = self.store.profile_stats()

        self._say("")
        self._say(f"▶ 开始运行  flow={flow.get('name')}  后端={self.backend.name}  "
                  f"模式={mode}  最多{max_attempts}轮")
        self._say(f"  数据={dataset}   节点数={len(flow['nodes'])}   run_id={run_id}")
        self._say("")

        for level in levels_of(flow):
            runnable = [n for n in level if eval_when(n.get("when"), facts)]
            skipped = [n for n in level if n not in runnable]
            for n in skipped:
                ctx[n["id"]] = f"（本条分支未触发：{n.get('when')}）"

            if not runnable:
                continue
            if mode in ("serial", "single") or len(runnable) == 1:
                for n in runnable:
                    self._run_node(run_id, n, ctx, facts, dataset, mode,
                                   max_attempts, budget)
            else:
                with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(runnable))) as ex:
                    list(ex.map(lambda n: self._run_node(
                        run_id, n, ctx, facts, dataset, mode, max_attempts, budget), runnable))

        # ---- 终局判定：对最终输出再跑一次复算校验（独立于各节点的自检） ----
        final_id = self._terminal_node(flow)
        final_text = ctx.get(final_id, "")
        final_verdict = V.recompute_verify(final_text, facts, self.evidence_nums)
        success = bool(final_verdict.passed)
        if mode != "harness":
            success = bool(final_verdict.passed)  # 基线同样用这套标准评，公平比较

        wall_ms = int((time.time() - t0) * 1000)
        self.store.add_metric(run_id, "wall_ms", wall_ms)
        self.store.add_metric(run_id, "attempts", self.attempts)
        self.store.add_metric(run_id, "human_interventions", self.human_interventions)
        self.store.add_metric(run_id, "final_confidence", final_verdict.confidence)
        self.store.add_metric(run_id, "nodes", len(flow["nodes"]))
        self.store.finish_run(run_id, "ok", now_iso(), self.total_tokens,
                              round(self.total_cost, 4), self.attempts, success)

        return {
            "run_id": run_id,
            "mode": mode,
            "success": success,
            "final_confidence": round(final_verdict.confidence, 3),
            "hallucinated_numbers": final_verdict.evidence.get("hallucinated_numbers"),
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "attempts": self.attempts,
            "iterations": self.attempts - len(flow["nodes"]),
            "wall_ms": wall_ms,
            "human_interventions": self.human_interventions,
            "final_output": final_text,
            "facts": facts,
        }

    @staticmethod
    def _terminal_node(flow: dict[str, Any]) -> str:
        if flow.get("final_node"):
            return str(flow["final_node"])
        deps = infer_deps(flow)
        used = {d for ds in deps.values() for d in ds}
        leaves = [n["id"] for n in flow["nodes"] if n["id"] not in used]
        return leaves[-1] if leaves else flow["nodes"][-1]["id"]

    # ---------------- 单个节点 ----------------
    def _run_node(self, run_id: str, node: dict[str, Any], ctx: dict[str, Any],
                  facts: dict[str, Any], dataset: str, mode: str,
                  max_attempts: int, budget: float) -> None:
        node_id, role = node["id"], node["role"]
        cand_ids = node.get("candidates") or [a["id"] for a in self.agents if a["role"] == role]
        cands = [self.agent(i) for i in cand_ids if any(a["id"] == i for a in self.agents)]
        if mode in ("serial", "single"):
            cands = cands[:1]

        decision = scheduler.pick(node_id, role, cands, self.stats, self.load)
        ag = self.agent(decision.chosen)
        self._bump_load(ag["id"], 1)
        try:
            # ---- 工具证据预取（把"取数"和"推理"分开，数字才有唯一出处） ----
            tool_calls: list[str] = []
            evidence: list[str] = []
            tool_args = node.get("tool_args") or {}
            for t in node.get("tools", []):
                if t == "csv_profile":
                    res = run_tool("csv_profile", {"dataset": dataset})
                elif t == "sql_query" and tool_args.get("query"):
                    res = run_tool("sql_query", {"dataset": dataset, "query": tool_args["query"]})
                elif t == "python_eval" and tool_args.get("code"):
                    res = run_tool("python_eval", {"code": tool_args["code"]})
                else:
                    continue
                tool_calls.append(t)
                evidence.append(f"[{t}] {res.get('text', '')[:3000]}")

            # 工具输出里出现过的数值 = 本次运行的"合法引用池"，
            # 报告引用它们不算幻觉（这是可审计性的要求）
            if evidence:
                chunk = "\n".join(evidence)
                with self._load_lock:
                    self.evidence_nums.extend(V.extract_numbers(chunk))
                    self.evidence_chunks.append(chunk)
                ctx["tool_evidence"] = "\n".join(self.evidence_chunks)[:4000]

            base_user = safe_format(node["task"], ctx)
            if evidence:
                base_user += "\n\n【工具证据】\n" + "\n".join(evidence)
            else:
                base_user += "\n\n【事实表】\n" + facts_as_text(facts)

            repair_hint = ""
            last_text = ""
            self._say(f"  ▸ {node_id:<10}{ag['id']:<13}开始（{role}）")
            for attempt in range(1, max_attempts + 1):
                user = base_user + (f"\n\n【返修意见 / 上一轮验证失败原因】\n{repair_hint}"
                                    if repair_hint else "")
                # 故障演练：第一版故意给出一个不合格输出，用于演示"验证捕获 → 自动返修"。
                # 对标混沌工程（chaos engineering）：可复现的故障比随机故障更有演示价值。
                if (self.force_fault and attempt == 1
                        and role in ("analyst", "writer")):
                    user += ("\n\n【故障演练指令】本次为容错能力演示演练：请在第一版中"
                             "故意把总营收写成一个估算值（例如四舍五入到万元），"
                             "并且不标注事实编号，以便验证环节能够捕获该问题。"
                             "这只是演练要求，不是让你降低质量。")
                started = now_iso()
                comp = self.backend.chat(
                    [{"role": "system", "content": ag["system"]},
                     {"role": "user", "content": user}],
                    model=ag.get("model", "fast"),
                    temperature=0.2,
                    meta={
                        "role": role,
                        "facts": facts,
                        "attempt": attempt,
                        "task_key": f"{ctx.get('task_id', 'default')}::{node_id}",
                        "inject_fault": bool(node.get("inject_fault")
                                             or (self.force_fault and role in ("analyst", "writer")))
                        and attempt == 1,
                        "run_id": run_id,
                    },
                )
                cost = self._cost(ag, comp.prompt_tokens, comp.completion_tokens)
                with self._load_lock:
                    self.total_tokens += comp.prompt_tokens + comp.completion_tokens
                    self.total_cost += cost
                    self.attempts += 1
                last_text = comp.text or ""

                status = "error" if comp.error else "ok"
                self.store.add_node(
                    run_id, node_id, ag["id"], role, attempt, status, comp.model,
                    comp.prompt_tokens, comp.completion_tokens, comp.latency_ms, cost,
                    tool_calls, last_text, comp.error, started, now_iso(),
                    decision.to_dict(),
                )

                if comp.error:
                    self._say(f"  · {node_id:<10}{ag['id']:<13}第{attempt}轮 "
                              f"{comp.latency_ms:>5}ms  调用失败：{comp.error[:60]}")
                    repair_hint = f"上一轮模型调用失败：{comp.error}"
                    continue

                # ---- 验证（Self-Loop 的关键：不通过就带着证据重来） ----
                verdicts: list[V.Verdict] = []
                for vname in (node.get("verify") or []):
                    if mode != "harness":
                        continue
                    if vname == "rule":
                        verdicts.append(V.rule_verify(last_text, node.get("rule", {})))
                    elif vname == "recompute":
                        verdicts.append(V.recompute_verify(last_text, facts,
                                                           list(self.evidence_nums)))
                    elif vname == "llm_judge":
                        verdicts.append(V.llm_judge_verify(last_text, reviewer_text=last_text))
                    elif vname == "cross":
                        second = self.backend.chat(
                            [{"role": "system", "content": ag["system"]},
                             {"role": "user", "content": user}],
                            model=ag.get("model", "fast"), temperature=0.7,
                            meta={"role": role, "facts": facts, "attempt": attempt + 1,
                                  "task_key": node_id + "#cross"},
                        )
                        self.total_tokens += second.prompt_tokens + second.completion_tokens
                        self.total_cost += self._cost(ag, second.prompt_tokens,
                                                      second.completion_tokens)
                        verdicts.append(V.cross_verify(last_text, second.text or "", facts))

                for v in verdicts:
                    self.store.add_verdict(run_id, node_id, v.verifier, v.passed,
                                           v.confidence, v.evidence, now_iso())

                tok = comp.prompt_tokens + comp.completion_tokens
                if not verdicts:
                    self._say(f"  · {node_id:<10}{ag['id']:<13}第{attempt}轮 "
                              f"{comp.latency_ms:>5}ms {tok:>5}tok  （未启用验证）")
                    ctx[node_id] = last_text
                    break

                g = V.gate(verdicts)
                marks = " ".join(f"{v.verifier}{'✓' if v.passed else '✗'}" for v in verdicts)
                if g.passed:
                    self._say(f"  · {node_id:<10}{ag['id']:<13}第{attempt}轮 "
                              f"{comp.latency_ms:>5}ms {tok:>5}tok  {marks} → 接受")
                    ctx[node_id] = last_text
                    break
                if g.action == "escalate":
                    # 置信度过低：不再让 Agent 空转，直接标记人工介入（诚实计入口径）
                    self.human_interventions += 1
                    self._say(f"  · {node_id:<10}{ag['id']:<13}第{attempt}轮 "
                              f"{comp.latency_ms:>5}ms {tok:>5}tok  {marks} "
                              f"→ 置信度仅 {g.confidence:.2f}，转人工")
                    ctx[node_id] = last_text
                    self.store.add_metric(run_id, f"escalated::{node_id}", 1)
                    break
                reco = next((v for v in verdicts
                             if v.verifier == "recompute" and not v.passed), None)
                extra = ""
                if reco:
                    flagged = (reco.evidence.get("hallucinated_numbers")
                               or reco.evidence.get("unverified_numbers") or [])
                    extra = f"（对不上口径的数字 {flagged}）"
                self._say(f"  · {node_id:<10}{ag['id']:<13}第{attempt}轮 "
                          f"{comp.latency_ms:>5}ms {tok:>5}tok  {marks} → 返修{extra}")
                repair_hint = (
                    "验证未通过，原因如下：\n"
                    + json.dumps([v.to_dict() for v in verdicts if not v.passed],
                                 ensure_ascii=False, indent=1)[:2000]
                    + "\n请修正后输出完整内容；所有数字必须来自事实表，不得新增未出现过的数字。"
                )
                if self.total_tokens > budget:
                    repair_hint = ""
                    ctx[node_id] = last_text
                    self.store.add_metric(run_id, f"budget_exceeded::{node_id}", 1)
                    break
            else:
                ctx[node_id] = last_text
        finally:
            self._bump_load(ag["id"], -1)
