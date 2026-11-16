"""临时候选校验：用真实模型产出的中英文终审文本测结论抽取。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.verify import judge_verdict, llm_judge_verify  # noqa: E402

cases = [
    ("【终审结论】PASS\n核对条目：F2/F3", True),
    ("【终审结论】FAIL\n存在无法溯源的数字", False),
    ("核对完成。发现 3 处数字缺少出处。结论：通过，可发布。", True),
    ("核对完成。结论：不通过，需返修。", False),
    ("经逐条核对，报告数字全部可溯源，终审结论：合格。", True),
    ("该报告不符合要求，驳回。", False),
    ("本报告未通过审核，请补充出处。", False),
    ("报告结构完整，数字均有出处，准予发布。", True),
    ("无法判断。", None),
]

bad = 0
for text, expect in cases:
    got = judge_verdict(text)
    ok = got == expect
    bad += 0 if ok else 1
    print(f"{'✅' if ok else '❌'} 期望={expect!s:<6} 实际={got!s:<6} | {text[:40]}")

r = llm_judge_verify("经核对，全部数字可溯源，结论：通过。F2 F3 F4")
print("\nllm_judge 样例：", r.passed, round(r.confidence, 2), r.evidence)
print("失败数：", bad)
