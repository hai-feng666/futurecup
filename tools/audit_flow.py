"""技术审计：检查并行度、验证器与工具的实际使用情况。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.engine import levels_of, load_flow  # noqa: E402

flow = load_flow(ROOT / "flows" / "data_insight.json")
levels = levels_of(flow)

print("分层情况：")
for i, level in enumerate(levels):
    ids = [n["id"] for n in level]
    print(f"  第{i}层: {ids}")

print()
print("最大并行度 =", max(len(lv) for lv in levels))
print()
print("各节点配置：")
for n in flow["nodes"]:
    print(f"  {n['id']:<10} verify={str(n.get('verify')):<22} tools={n.get('tools')}")
print()

used_v = {v for n in flow["nodes"] for v in (n.get("verify") or [])}
used_t = {t for n in flow["nodes"] for t in (n.get("tools") or [])}
print("实际启用的验证器：", sorted(used_v))
print("实际启用的工具  ：", sorted(used_t))
print("verify.py 中定义的验证器：", ["rule", "recompute", "cross", "llm_judge"])
print("tools.py 中注册的工具   ：", ["csv_profile", "sql_query", "python_eval"])
