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
        self.last_verdicts: dict[str, list[Any]] = {}
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
        self.last_verdicts = {}

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
                                   self._node_attempts(n, max_attempts), budget)
            else:
                with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(runnable))) as ex:
                    list(ex.map(lambda n: self._run_node(
                        run_id, n, ctx, facts, dataset, mode,
                        self._node_attempts(n, max_attempts), budget), runnable))

        # ---- 交叉节点回溯：审校判否时，带着具体意见回到撰写节点重写一次 ----
        review_id = flow.get("review_node")
        back_id = flow.get("backtrack_to")
        if mode == "harness" and review_id and back_id:
            for cycle in range(1, int(flow.get("backtrack_rounds", 1)) + 1):
                rv = self.last_verdicts.get(review_id) or []
                failed = [v for v in rv if not v.passed]
                if not failed:
                    break
                self._say(f"  ⟲ 审校未通过，回溯重写 {back_id}（第 {cycle} 次）")
                hint = ("上文审校环节指出了以下问题，请据此重写正文（不要复述意见本身）：\n"
                        + json.dumps([v.to_dict() for v in failed], ensure_ascii=False,
                                     indent=1)[:1800])
                back = next(n for n in flow["nodes"] if n["id"] == back_id)
                self._run_node(run_id, back, ctx, facts, dataset, mode,
                               int(flow.get("backtrack_attempts", 1)), budget,
                               preface=hint, attempt_start=2)
                rev = next(n for n in flow["nodes"] if n["id"] == review_id)
                self._run_node(run_id, rev, ctx, facts, dataset, mode, 1, budget,
                               attempt_start=2)

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
    def _node_attempts(node: dict[str, Any], flow_max: int) -> int:
        """节点级重试上限：审校类节点重试没有意义（它不改产出），默认只跑一次。"""
        return max(1, min(flow_max, int(node.get("max_attempts", flow_max))))

    @staticmethod
    def _terminal_node(flow: dict[str, Any]) -> str:
        if flow.get("final_node"):
            return str(flow["final_node"])
        deps = infer_deps(flow)
        used = {d for ds in deps.values() for d in ds}
        leaves = [n["id"] for n in flow["nodes"] if n["id"] not in used]
        return leaves[-1] if leaves else flow["nodes"][-1]["id"]

    # ---------------- 验证器辅助 ----------------
    def _judge(self, node: dict[str, Any], text: str, facts: dict[str, Any],
               role: str, run_id: str, ag: dict[str, Any]) -> V.Verdict:
        """L4 终审：可选地真正调用一次模型做独立评审。

        node.judge_by_model = true 时发起一次真实评审调用（mock 后端自动退化为
        规则抽取，保证离线可跑）；否则使用结论抽取。
        """
        if not node.get("judge_by_model") or self.backend.name == "mock":
            return V.llm_judge_verify(text, reviewer_text=text)

        judge_prompt = (
            "你是独立评审。逐条核对下列报告中的数字能否在「事实表」或「工具证据」中找到依据，"
            "并检查结论是否存在自相矛盾。\n\n"
            f"【事实表】\n{facts_as_text(facts)[:1500]}\n\n"
            f"【本次工具证据（上游节点实际取到的数据，引用它们属于合法；"
            f"若证据尾部被截断，请对截断段的数字标注「无法核对」而非直接判不通过）】\n"
            f"{''.join(self.evidence_chunks)[:6000]}\n\n"
            f"【待审报告】\n{text[:4000]}\n\n"
            "判定口径（务必严格遵守，越界即误判）：\n"
            "· 只判两类问题：① 数字能否在【事实表】或【工具证据】中找到出处；"
            "② 报告中数字与数字之间是否自相矛盾（含排序方向、增减方向写反）。\n"
            "· **不要**评价措辞、格式、篇幅、行文风格；**不要**因报告未写计算式而判不通过；"
            "**不要**因报告对“哪些数据可用/不可用”的评论而判不通过（那是作者的表述习惯，不是数字错误）。\n"
            "· 小于 1000 的数字（百分比、比值、笔数）不要求计算式。\n"
            "· 若两类问题都不存在，即使你觉得写得不好，也必须判通过。\n\n"
            "输出格式（必须严格遵守）：\n第一行只写 结论：通过 或 结论：不通过\n"
            "随后 3 行以内说明依据（哪几个数字有问题、什么问题）。"
        )
        comp = self.backend.chat(
            [{"role": "system", "content": "你是严谨的审计员，只依据给定事实判断。"},
             {"role": "user", "content": judge_prompt}],
            model="strong", temperature=0.0,
            meta={"role": "reviewer", "facts": facts, "attempt": 1,
                  "task_key": f"{node['id']}#judge"},
        )
        cost = self._cost(ag, comp.prompt_tokens, comp.completion_tokens)
        with self._load_lock:
            self.total_tokens += comp.prompt_tokens + comp.completion_tokens
            self.total_cost += cost
        if comp.error:
            return V.llm_judge_verify(text, reviewer_text=text)

        verdict = V.judge_verdict(comp.text or "")
        if verdict is None:
            return V.llm_judge_verify(text, reviewer_text=text)
        return V.Verdict("llm_judge", bool(verdict), 0.9, {
            "mode": "model", "verdict": "通过" if verdict else "不通过",
            "judge_excerpt": (comp.text or "")[:200],
            "judge_latency_ms": comp.latency_ms,
        })

    def _cross(self, node: dict[str, Any], text: str, facts: dict[str, Any],
               ctx: dict[str, Any], ag: dict[str, Any]) -> V.Verdict:
        """L3 交叉验证：比对两路**独立**产出的结论是否互相印证。

        node.cross_with 指定要比对的两个上游节点（两条独立分析的输出），
        不消耗额外模型调用。
        """
        pair = node.get("cross_with") or []
        if isinstance(pair, str):
            pair = [pair]
        nums = list(self.evidence_nums)
        texts = [str(ctx.get(p, "")) for p in pair[:2]]
        if len(texts) == 2 and all(texts):
            v = V.cross_verify(texts[0], texts[1], facts, nums)
            v.evidence["compared"] = pair[:2]
            return v
        if len(texts) == 1 and texts[0]:
            v = V.cross_verify(text, texts[0], facts, nums)
            v.evidence["compared"] = [node["id"], pair[0]]
            return v
        return V.Verdict("cross", False, 0.0, {"error": "cross_with 未配置或上游为空"})

    # ---------------- 单个节点 ----------------
    def _run_node(self, run_id: str, node: dict[str, Any], ctx: dict[str, Any],
                  facts: dict[str, Any], dataset: str, mode: str,
                  max_attempts: int, budget: float, preface: str = "",
                  attempt_start: int = 1) -> None:
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
            # 事实表与工具证据必须同时给：只给工具输出时，模型看不到未查询的口径
            # （例如只查了品类，就不知道各区域订单数），会自行编造后被判幻觉。
            base_user += "\n\n【事实表】\n" + facts_as_text(facts)
            if evidence:
                base_user += "\n\n【工具证据】\n" + "\n".join(evidence)

            repair_hint = ""
            last_text = ""
            if preface:
                repair_hint = preface
            self._say(f"  ▸ {node_id:<10}{ag['id']:<13}开始（{role}）")
            for attempt in range(attempt_start, attempt_start + max_attempts):
                user = base_user + (f"\n\n【返修意见 / 上一轮验证失败原因】\n{repair_hint}"
                                    if repair_hint else "")
                # 故障演练：只在报告环节注入一次「输出截断」（max_tokens=120）。
                # 不在分析链注入错误——它会被下游反复加工，导致整条链路发散。
                # 截断属环境级故障，确定性可复现，对标混沌工程的做法。
                started = now_iso()
                comp = self.backend.chat(
                    [{"role": "system", "content": ag["system"]},
                     {"role": "user", "content": user}],
                    model=ag.get("model", "fast"),
                    temperature=0.2,
                    max_tokens=(120 if (self.force_fault and attempt == attempt_start
                                        and node_id == "report")
                                else int(node.get("max_tokens", 3500))),
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
                    decision.to_dict(), prompt=user,
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
                        verdicts.append(V.recompute_verify(
                            last_text, facts, list(self.evidence_nums),
                            required=node.get("required_facts")))
                    elif vname == "llm_judge":
                        verdicts.append(self._judge(node, last_text, facts, role,
                                                    run_id, ag))
                    elif vname == "cross":
                        verdicts.append(self._cross(node, last_text, facts, ctx, ag))

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
                # 「参考项」只记录不阻塞：例如仲裁节点的 cross 用于呈现上游分歧，
                # 不该因为上游本身有问题就把仲裁员的输出判死。
                advisory = set(node.get("advisory") or [])
                blocking = [v for v in verdicts if v.verifier not in advisory]
                if advisory and blocking:
                    g = V.gate(blocking)
                self.last_verdicts[node_id] = verdicts
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
                    + "\n请修正后输出完整内容；所有数字必须来自事实表。"
                    + "\n注意：以上仅为修改要求，**不要在正文里复述这些要求或罗列“不合格项”**，"
                      "直接输出修改后的完整正文。"
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
