import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.tools import compute_facts, run_tool  # noqa: E402

f = compute_facts(ROOT / "data" / "sales.csv")
known = set()
for k in ("total_revenue", "avg_order_value", "max_order_value", "order_count"):
    known.add(round(float(f[k]), 2))
for k in ("by_region", "by_region_avg", "by_region_orders", "by_product"):
    known |= {round(float(v), 2) for v in (f.get(k) or {}).values()}

targets = [12046.23, 12363.33, 28858.19, 185450.0, 461731.0]
res = run_tool("sql_query", {
    "dataset": "data/sales.csv",
    "query": ("SELECT product, channel, ROUND(SUM(revenue),2) AS rev, COUNT(*) AS n "
              "FROM sales GROUP BY product, channel ORDER BY rev DESC"),
})
slices = {(r["product"], r["channel"]): r["rev"] for r in res["data"]}

print(f"品类×渠道切片共 {len(slices)} 个，合计 {round(sum(slices.values()), 2)}")
for t in targets:
    hit = [k for k, v in slices.items() if abs(v - t) / max(1, t) <= 0.005]
    print(f"  {t:<12} 在事实表: {t in known}   命中切片: {hit if hit else '无'}")
