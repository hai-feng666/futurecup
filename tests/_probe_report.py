import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.tools import compute_facts          # noqa: E402
from harness.verify import recompute_verify      # noqa: E402

facts = compute_facts(ROOT / "data" / "sales.csv")
print("事实表关键值：")
for k in ("total_revenue", "avg_order_value", "order_count", "max_order_value"):
    print("  ", k, facts[k])
print("   区域营收", facts["by_region"])
print("   区域单均", facts["by_region_avg"])

# 取自真实 DeepSeek 输出的一段报告（数字照抄用户截图）
REPORT = """
## 区域营收结构

| 区域 | 营收（元） | 订单数 | 营收占比 |
|---|---|---|---|
| 西南 | 1,527,708.0 | 61 | 28.0% |
| 华南 | 1,142,778.0 | 44 | 20.9% |
| 东北 | 1,052,611.0 | 43 | 19.3% |
| 华东 | 1,003,865.0 | 47 | 18.4% |
| 华北 | 728,948.0 | 40 | 13.4% |
| **合计** | **5,455,910.0** | **235** | **100%** |

全盘客单价 23,216.64 元，有效订单 235 单，总营收 5,455,910.0 元 [F2、F3、F4]。
最大单笔 136,000.0 元，约为客单价的 5.86 倍。

西南单均营收 25,044 元，华南 25,972 元，两者相差 928 元。
华东单均营收 21,358 元，低于五区均值 23,217 元，低 1,859 元。
若提升至均值，47 单可增收约 87,373 元。

区域间最大/最小营收比约为 2.1 倍（1,527,708.0 ÷ 728,948.0），集中度中等偏高。
"""

v = recompute_verify(REPORT, facts)
print("\n复算结果 passed =", v.passed, " conf =", round(v.confidence, 3))
for k, val in v.evidence.items():
    print(f"  {k}: {val}")
