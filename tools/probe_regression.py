"""回归验证：真实失败报告 + 工具证据池 → 是否不再误判。"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.tools import compute_facts, run_tool  # noqa: E402
from harness.verify import recompute_verify, extract_numbers, rule_verify  # noqa: E402

rid = sys.argv[1] if len(sys.argv) > 1 else "run-1794368444191-6c24"
c = sqlite3.connect(ROOT / "runs.db")
c.row_factory = sqlite3.Row
rows = c.execute("select attempt, output from nodes where run_id=? and node_id='report' "
                 "order by attempt", (rid,)).fetchall()
text = rows[-1]["output"]
print(f"报告长度 {len(text)} 字，取第 {rows[-1]['attempt']} 轮（失败那轮）")

facts = compute_facts(ROOT / "data" / "sales.csv")

# 复现本次运行所有工具证据里出现过的数值
allowed = []
for q in (
    "SELECT region, ROUND(SUM(revenue),2) AS rev, COUNT(*) AS orders FROM sales "
    "GROUP BY region ORDER BY rev DESC",
    "SELECT product, channel, ROUND(SUM(revenue),2) AS rev, COUNT(*) AS orders, "
    "ROUND(SUM(revenue)/COUNT(*),2) AS avg_rev FROM sales GROUP BY product, channel "
    "ORDER BY rev DESC",
):
    allowed += extract_numbers(run_tool("sql_query", {"dataset": "data/sales.csv",
                                                     "query": q})["text"])
print(f"工具证据池数值个数 = {len(allowed)}")

for label, extra in (("修复前（只用事实表）", None), ("修复后（事实表+工具证据）", allowed)):
    v = recompute_verify(text, facts, extra)
    print(f"\n{label}: passed={v.passed} conf={v.confidence:.2f}")
    print(f"  缺失={v.evidence['missing_required']}")
    print(f"  幻觉={v.evidence['hallucinated_numbers']}")
    print(f"  待核={v.evidence['unverified_numbers']}")

print("\n规则校验：", rule_verify(text, {"min_len": 300, "min_headings": 3}).evidence)
