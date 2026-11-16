"""能力画像调度器。

这是决赛「架构设计与调度算法」10 分的主要落点，设计上刻意做到可解释：

    score(agent | node) =   w_cap  · capability(agent, role)
                          + w_score · UCB1(历史成功率)          ← 利用 + 探索
                          - w_cost  · 归一化预估成本
                          - w_lat   · 归一化历史延迟
                          - w_load  · 当前并发负载

选中的 Agent 会把完整的打分明细写进 trace，界面上能直接回答
「为什么这一步派给 B 而不是 A」——这是答辩时最容易被追问的地方。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

DEFAULT_WEIGHTS = {
    "capability": 1.0,
    "score": 1.2,
    "cost": 0.35,
    "latency": 0.35,
    "load": 0.8,
}
EXPLORE_C = 0.30  # UCB 探索系数


@dataclass
class Decision:
    node_id: str
    role: str
    chosen: str
    reason: str
    weights: dict[str, float] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "chosen": self.chosen,
            "reason": self.reason,
            "weights": self.weights,
            "candidates": self.candidates,
        }


def _ucb(ok_rate: float, n: float, total: float, c: float = EXPLORE_C) -> float:
    """UCB1：样本越少，探索奖励越大，避免新 Agent 被永久冷落。"""
    if n <= 0:
        return 1.0  # 未跑过 = 全新，给最高探索奖励
    return ok_rate + c * math.sqrt(math.log(total + 1.0) / n)


def pick(node_id: str, role: str, candidates: list[dict[str, Any]],
         stats: dict[str, dict[str, float]], load: dict[str, int],
         weights: dict[str, float] | None = None) -> Decision:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total_n = sum(s.get("n", 0.0) for s in stats.values()) or 1.0

    raw: list[dict[str, Any]] = []
    for ag in candidates:
        aid = ag["id"]
        st = stats.get(aid, {})
        n = st.get("n", 0.0)
        ok_rate = st.get("ok_rate", 0.0)
        est_cost = st.get("avg_cost", 0.0) or (ag.get("cost_per_1k_in", 0.0) * 2)
        est_lat = st.get("avg_latency", 0.0) or 1500.0
        cap = 1.0 if ag.get("role") == role else 0.45
        raw.append({
            "id": aid,
            "name": ag.get("name", aid),
            "capability": cap,
            "ucb": round(_ucb(ok_rate, n, total_n), 4),
            "ok_rate": round(ok_rate, 4),
            "n": n,
            "est_cost": round(est_cost, 6),
            "est_latency": round(est_lat, 1),
            "load": load.get(aid, 0),
        })

    max_cost = max((r["est_cost"] for r in raw), default=1.0) or 1.0
    max_lat = max((r["est_latency"] for r in raw), default=1.0) or 1.0
    max_load = max((r["load"] for r in raw), default=0) or 1

    for r in raw:
        r["score"] = round(
            w["capability"] * r["capability"]
            + w["score"] * r["ucb"]
            - w["cost"] * (r["est_cost"] / max_cost)
            - w["latency"] * (r["est_latency"] / max_lat)
            - w["load"] * (r["load"] / max_load),
            4,
        )

    raw.sort(key=lambda r: -r["score"])
    best = raw[0]
    runner = raw[1] if len(raw) > 1 else None
    reason = (
        f"能力匹配 {best['capability']:.2f} + UCB {best['ucb']:.3f}"
        f"（历史成功率 {best['ok_rate']:.0%}，样本 {int(best['n'])}）"
        f" − 成本项 − 延迟项 − 负载项"
    )
    if runner:
        reason += f"；领先 {runner['id']} {best['score'] - runner['score']:.3f} 分"
    return Decision(node_id=node_id, role=role, chosen=best["id"], reason=reason,
                    weights=w, candidates=raw)
