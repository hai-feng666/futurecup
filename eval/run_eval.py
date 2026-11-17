"""基线对比评测：把「量化」这件事一次做对。

三组配置跑同一批任务、同一套评分标准（终局复算校验）：
  A. single  —— 单 Agent 直连（有数据访问，但一次性输出，无验证）
  B. serial  —— 固定串行流水线（多 Agent，但无验证、无返修）
  C. harness —— 本平台（能力画像调度 + 分层验证 + 自循环）

诚实声明：mock 后端下数字是模拟的，只用于验证工程链路；
真实结论请用 HARNESS_BACKEND=openai 跑一遍，脚本会在表头标注数据来源。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.engine import Executor          # noqa: E402
from harness.models import get_backend       # noqa: E402
from harness.store import Store              # noqa: E402
from harness.util import read_jsonl          # noqa: E402

MODES = [("single", "A 单 Agent 直连"), ("serial", "B 固定串行"), ("harness", "C 本平台")]


def single_flow(task: dict) -> dict:
    return {
        "name": "baseline_single",
        "title": "基线：单 Agent 直连",
        "final_node": "answer",
        "max_rounds": 1,
        "inputs": {"dataset": task["dataset"], "question": task["question"]},
        "nodes": [{
            "id": "answer",
            "role": "generalist",
            "depends_on": [],
            "candidates": ["generalist-x"],
            "task": "请回答业务问题：{question}",
            "tools": ["csv_profile"],
            "verify": [],
        }],
    }


def agg(rows: list[dict]) -> dict[str, float]:
    def mean(key: str) -> float:
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        return statistics.fmean(vals) if vals else 0.0

    return {
        "tasks": len(rows),
        "success_rate": sum(1 for r in rows if r["success"]) / max(1, len(rows)),
        "avg_tokens": mean("total_tokens"),
        "avg_cost": mean("total_cost"),
        "avg_wall_ms": mean("wall_ms"),
        "avg_attempts": mean("attempts"),
        "avg_confidence": mean("final_confidence"),
        "human_rate": sum(1 for r in rows if r["human_interventions"]) / max(1, len(rows)),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--backend", default=None)
    ap.add_argument("--db", default=str(ROOT / "eval" / "eval_runs.db"))
    args = ap.parse_args(argv)

    tasks = read_jsonl(ROOT / "eval" / "tasks.jsonl")[: args.limit]
    if not tasks:
        print("没有任务集，请检查 eval/tasks.jsonl")
        return 1
    backend = get_backend(args.backend)
    store = Store(args.db)

    summary: dict[str, dict[str, float]] = {}
    detail: dict[str, list[dict]] = {}
    for mode, label in MODES:
        rows = []
        for t in tasks:
            ex = Executor(store, backend)
            flow = single_flow(t) if mode == "single" else (ROOT / "flows" / "data_insight.json")
            res = ex.run(flow, inputs=t, mode=mode)
            rows.append(res)
            print(f"  [{label}] {t['task_id']} success={res['success']} "
                  f"attempts={res['attempts']} conf={res['final_confidence']}")
        summary[label] = agg(rows)
        detail[label] = [{k: v for k, v in r.items() if k != "facts"} for r in rows]

    source = "MOCK 模拟值（仅验证链路，不可作为结论）" if backend.name == "mock" else f"真实模型：{backend.name}"
    lines = [
        "# 基线对比评测结果",
        "",
        f"- 数据来源：**{source}**",
        f"- 任务数：{len(tasks)}（eval/tasks.jsonl）",
        "- 判定标准：终局对最终交付物执行 L2 复算校验（数字必须能在事实表复算出来）",
        "",
        "> **本文件的性质**：它证明的是「验证层能把漂移数字捞回来」这条工程链路，",
        "> 不是真实模型的效果结论。真实模型的单次实测数据见 README 第五节与方案书 6.4 节。",
        "",
        "| 配置 | 成功率 | 平均输出置信度 | 平均尝试次数 | 平均 tokens | 平均耗时(ms) | 人工介入率 |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, label in MODES:
        s = summary[label]
        lines.append(
            f"| {label} | {s['success_rate']:.1%} | {s['avg_confidence']:.2f} | "
            f"{s['avg_attempts']:.1f} | {s['avg_tokens']:.0f} | "
            f"{s['avg_wall_ms']:.0f} | {s['human_rate']:.0%} |"
        )

    base = summary["A 单 Agent 直连"]["success_rate"]
    ours = summary["C 本平台"]["success_rate"]
    lines += [
        "",
        f"**成功率提升：{ours - base:+.1%}（相对基线）**",
        "",
        "> 说明：mock 模式下的差异来自确定性故障注入与返修闭环，",
        "> 目的是证明「验证层能把漂移数字捞回来」这条链路真实有效；",
        "> 换真实模型后重跑本脚本即可得到可写进决赛材料的数字。",
    ]
    out_md = ROOT / "eval" / "results.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "eval" / "results.json").write_text(
        json.dumps({"source": source, "summary": summary, "detail": detail},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print(f"\n已写出：{out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
