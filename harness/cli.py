"""命令行入口：一个人用终端就能完成全部演示动作。

  python -m harness.cli run --fault      # 跑一次（--fault 强制注入一次数字漂移，演示自循环）
  python -m harness.cli runs             # 看历史
  python -m harness.cli replay <run_id>  # 离线回放一次运行
  python -m harness.cli eval             # 基线对比评测
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine import Executor, infer_deps
from .models import get_backend
from .store import Store
from .util import load_json, project_root

ROOT = project_root()
LINE = "─" * 78


def _fmt_run(store: Store, run_id: str, show_output: bool = True) -> str:
    run = store.run(run_id)
    if not run:
        return f"未找到 run: {run_id}"
    nodes = store.nodes(run_id)
    verdicts = store.verdicts(run_id)
    metrics = store.metrics(run_id)
    out = [LINE]
    out.append(f"RUN {run_id}   flow={run['flow']}   status={run['status']}   "
               f"success={run['success']}")
    out.append(f"backend={json.loads(run['config']).get('backend')}   "
               f"tokens={run['total_tokens']}   cost={run['total_cost']}   "
               f"attempts={run['rounds']}   wall={int(metrics.get('wall_ms', 0))}ms")
    out.append(LINE)
    out.append(f"{'节点':<10}{'Agent':<14}{'轮':<3}{'耗时ms':<8}{'tok':<7}{'状态':<8}调度依据")
    seen: set[tuple[str, int]] = set()
    for n in nodes:
        key = (n["node_id"], n["attempt"])
        if key in seen:
            continue
        seen.add(key)
        dec = json.loads(n["decision"] or "{}")
        reason = (dec.get("reason") or "")[:34]
        out.append(f"{n['node_id']:<10}{n['agent_id']:<14}{n['attempt']:<3}"
                   f"{n['latency_ms']:<8}{n['prompt_tokens'] + n['completion_tokens']:<7}"
                   f"{n['status']:<8}{reason}")
    out.append(LINE)
    if verdicts:
        out.append("验证记录（★ = 未通过，触发返修）：")
        for v in verdicts:
            ev = json.loads(v["evidence"] or "{}")
            flag = " " if v["passed"] else "★"
            extra = ""
            if v["verifier"] == "recompute":
                extra = f" 缺失={ev.get('missing_required')} 幻觉数字={ev.get('hallucinated_numbers')}"
            elif v["verifier"] == "rule":
                extra = f" 问题={ev.get('problems')}"
            out.append(f"  {flag} {v['node_id']:<10}{v['verifier']:<10}"
                       f"passed={bool(v['passed'])!s:<6}conf={v['confidence']:.2f}{extra}")
    if metrics.get("human_interventions"):
        out.append(f"人工介入：{int(metrics['human_interventions'])} 次")
    if show_output:
        out.append(LINE)
        out.append("最终交付物：")
        out.append(run_final_output(store, run_id))
    return "\n".join(out)


def run_final_output(store: Store, run_id: str) -> str:
    run = store.run(run_id)
    flow_name = run["flow"] if run else ""
    flows = list((ROOT / "flows").glob("*.json"))
    final_id = "report"
    for f in flows:
        data = load_json(f)
        if data.get("name") == flow_name:
            final_id = data.get("final_node") or "report"
    nodes = [n for n in store.nodes(run_id) if n["node_id"] == final_id]
    return nodes[-1]["output"] if nodes else "（无输出）"


def cmd_run(args: argparse.Namespace) -> int:
    if args.fault:
        os.environ["HARNESS_FORCE_FAULT"] = "1"
    store = Store(args.db)
    backend = get_backend(args.backend)
    ex = Executor(store, backend)
    flow_path = Path(args.flow)
    if not flow_path.is_absolute():
        flow_path = ROOT / flow_path
    res = ex.run(flow_path, mode=args.mode)
    print(_fmt_run(store, res["run_id"], show_output=not args.json))
    if args.json:
        print(json.dumps({k: v for k, v in res.items() if k != "facts"}, ensure_ascii=False,
                         indent=2))
    return 0 if res["success"] else 2


def cmd_runs(args: argparse.Namespace) -> int:
    store = Store(args.db)
    rows = store.runs(args.limit)
    print(f"{'run_id':<28}{'flow':<16}{'状态':<10}{'成功':<6}{'尝试':<6}{'开始时间'}")
    for r in rows:
        print(f"{r['id']:<28}{r['flow']:<16}{r['status']:<10}"
              f"{str(r['success']):<6}{r['rounds']:<6}{r['started']}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    store = Store(args.db)
    print(_fmt_run(store, args.run_id))
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from eval.run_eval import main as eval_main
    return eval_main([])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="harness", description="多 Agent 编排调度平台")
    ap.add_argument("--db", default=os.getenv("HARNESS_DB", "runs.db"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="跑一次流程")
    r.add_argument("--flow", default="flows/data_insight.json")
    r.add_argument("--mode", default="harness", choices=["harness", "serial", "single"])
    r.add_argument("--backend", default=None, help="mock / openai")
    r.add_argument("--fault", action="store_true", help="强制注入一次数字漂移")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_run)

    l = sub.add_parser("runs", help="列出历史运行")
    l.add_argument("--limit", type=int, default=20)
    l.set_defaults(func=cmd_runs)

    p = sub.add_parser("replay", help="回放一次运行")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_replay)

    e = sub.add_parser("eval", help="基线对比评测")
    e.set_defaults(func=cmd_eval)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
