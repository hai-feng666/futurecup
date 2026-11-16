"""冒烟测试：确保核心链路不会在演示当天崩掉。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import verify as V          # noqa: E402
from harness.engine import Executor, eval_when, infer_deps, levels_of  # noqa: E402
from harness.models import MockBackend   # noqa: E402
from harness.store import Store          # noqa: E402
from harness.tools import compute_facts  # noqa: E402


class TestFlow(unittest.TestCase):
    def test_levels_follow_dependencies(self):
        from harness.engine import load_flow
        flow = load_flow(ROOT / "flows" / "data_insight.json")
        lv = levels_of(flow)
        self.assertEqual(len(lv), 6, "profile→clean→analyze→deep_dive→report→review 共 6 层")
        first = [n["id"] for n in lv[0]]
        self.assertEqual(first, ["profile"])

    def test_when_expression(self):
        self.assertTrue(eval_when("outlier_count > 0", {"outlier_count": 3}))
        self.assertFalse(eval_when("outlier_count > 0", {"outlier_count": 0}))
        self.assertTrue(eval_when(None, {}))

    def test_terminal_node(self):
        from harness.engine import load_flow
        flow = load_flow(ROOT / "flows" / "data_insight.json")
        self.assertEqual(Executor._terminal_node(flow), "report")


class TestFacts(unittest.TestCase):
    def test_cleaning_drops_bad_rows(self):
        f = compute_facts(ROOT / "data" / "sales.csv")
        self.assertGreater(f["rows_raw"], f["rows_clean"])
        self.assertGreater(f["rows_dropped"], 0)
        self.assertGreater(f["total_revenue"], 0)

    def test_facts_are_deterministic(self):
        a = compute_facts(ROOT / "data" / "sales.csv")
        b = compute_facts(ROOT / "data" / "sales.csv")
        self.assertEqual(a, b)


class TestVerifiers(unittest.TestCase):
    def setUp(self):
        self.facts = compute_facts(ROOT / "data" / "sales.csv")

    def test_recompute_passes_on_grounded_text(self):
        f = self.facts
        text = (f"总营收 {f['total_revenue']} 元，订单 {f['order_count']} 笔，"
                f"客单价 {f['avg_order_value']} 元，{f['top_region']} 最高。")
        v = V.recompute_verify(text, f)
        self.assertTrue(v.passed, v.evidence)

    def test_recompute_catches_hallucinated_number(self):
        f = self.facts
        text = (f"总营收 {f['total_revenue'] * 1.37} 元，订单 {f['order_count']} 笔，"
                f"客单价 {f['avg_order_value']} 元，{f['top_region']} 最高。")
        v = V.recompute_verify(text, f)
        self.assertFalse(v.passed)
        flagged = v.evidence["hallucinated_numbers"] + v.evidence["unverified_numbers"]
        self.assertTrue(flagged, v.evidence)

    def test_recompute_accepts_realistic_derived_numbers(self):
        """真实模型会算区域单均、差值、合计——这些不该被误判成幻觉。"""
        f = self.facts
        text = (
            f"西南 {f['by_region']['西南']} 元，{f['by_region_orders']['西南']} 单；"
            f"华北 {f['by_region']['华北']} 元，{f['by_region_orders']['华北']} 单；"
            f"全盘客单价 {f['avg_order_value']} 元，总营收 {f['total_revenue']} 元，"
            f"有效订单 {f['order_count']} 单。"
            f"西南单均 {f['by_region_avg']['西南']} 元，华北单均 {f['by_region_avg']['华北']} 元。"
            f"区域间最大/最小营收比约 "
            f"{round(f['by_region']['西南'] / f['by_region']['华北'], 1)} 倍。"
        )
        v = V.recompute_verify(text, f)
        self.assertTrue(v.passed, v.evidence)
        self.assertEqual(v.evidence["unverified_numbers"], [], v.evidence)

    def test_gate_rejects_low_confidence(self):
        v = V.Verdict("recompute", False, 0.2, {})
        self.assertFalse(V.gate([v]).passed)


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 用项目内的临时目录（普通子目录，权限继承自父级，避免受限环境下的权限问题）
        cls.tmp = ROOT / "tests" / "_tmp"
        try:
            cls.tmp.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise unittest.SkipTest("测试临时目录不可写（受限环境），跳过端到端测试")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_full_run_succeeds(self):
        store = Store(self.tmp / "t1.db")
        self.addCleanup(store.close)
        ex = Executor(store, MockBackend())
        res = ex.run(ROOT / "flows" / "data_insight.json")
        self.assertTrue(res["success"], res["hallucinated_numbers"])
        self.assertGreaterEqual(res["attempts"], 6)
        nodes = store.nodes(res["run_id"])
        self.assertEqual({n["node_id"] for n in nodes},
                         {"profile", "clean", "analyze", "deep_dive", "report", "review"})
        verdicts = store.verdicts(res["run_id"])
        self.assertTrue(any(v["verifier"] == "recompute" for v in verdicts))

    def test_forced_fault_triggers_repair(self):
        import os
        os.environ["HARNESS_FORCE_FAULT"] = "1"
        try:
            store = Store(self.tmp / "t2.db")
            self.addCleanup(store.close)
            ex = Executor(store, MockBackend())
            res = ex.run(ROOT / "flows" / "data_insight.json")
        finally:
            os.environ["HARNESS_FORCE_FAULT"] = "0"
        self.assertTrue(res["success"])
        attempts = [n["attempt"] for n in store.nodes(res["run_id"])
                    if n["node_id"] == "analyze"]
        self.assertGreater(max(attempts), 1, "强制故障下 analyze 应该出现返修轮次")


class TestRealModelReport(unittest.TestCase):
    """用真实 DeepSeek 输出做回归。

    样本是 11/11 一次**失败**的真实运行：报告引用了 deep_dive 节点 SQL 返回的
    品类×渠道切片金额，但旧版校验器只认基础事实表，于是判成幻觉。
    修复后（事实表 + 本次运行工具证据池）必须通过。
    """

    @classmethod
    def setUpClass(cls):
        cls.facts = compute_facts(ROOT / "data" / "sales.csv")
        fixture = ROOT / "tests" / "fixtures" / "report_real_model.md"
        if not fixture.exists():
            raise unittest.SkipTest("真实报告样本缺失（tests/fixtures/report_real_model.md）")
        cls.text = fixture.read_text(encoding="utf-8")
        allowed: list[float] = []
        from harness.tools import run_tool
        for q in (
            "SELECT region, ROUND(SUM(revenue),2) AS rev, COUNT(*) AS orders "
            "FROM sales GROUP BY region ORDER BY rev DESC",
            "SELECT product, channel, ROUND(SUM(revenue),2) AS rev, COUNT(*) AS orders, "
            "ROUND(SUM(revenue)/COUNT(*),2) AS avg_rev FROM sales "
            "GROUP BY product, channel ORDER BY rev DESC",
        ):
            res = run_tool("sql_query", {"dataset": "data/sales.csv", "query": q})
            allowed += V.extract_numbers(res["text"])
        cls.allowed = allowed

    def test_year_is_not_a_business_number(self):
        """"2026 年前三季度"里的 2026 不能被当成业务数字（中文让 \\b 失效的坑）。"""
        nums = V.extract_numbers("2026 年前三季度，2026年总营收 5,455,910.0 元")
        self.assertNotIn(2026.0, nums)
        self.assertIn(5455910.0, nums)

    def test_scenario_numbers_are_exempt(self):
        """情景推演句里的数字归到 scenario，不判幻觉。"""
        text = ("若单均提升至 26,500 元，同单量下营收可达 6,200,000 元。"
                "报告期内总营收 5,455,910.0 元。")
        scenario, rest = V._split_scenario(text, [26500.0, 6200000.0, 5455910.0])
        self.assertEqual(sorted(scenario), [26500.0, 6200000.0])
        self.assertEqual(rest, [5455910.0])

    def test_rule_accepts_real_report(self):
        v = V.rule_verify(self.text, {"min_len": 300, "min_headings": 3})
        self.assertTrue(v.passed, v.evidence)

    def test_evidence_pool_rescues_tool_cited_numbers(self):
        without = V.recompute_verify(self.text, self.facts)
        with_pool = V.recompute_verify(self.text, self.facts, self.allowed)
        self.assertFalse(without.passed, "没有证据池时应当报出问题（证明池子真的起作用）")
        self.assertTrue(with_pool.passed, with_pool.evidence)
        self.assertEqual(with_pool.evidence["hallucinated_numbers"], [])


if __name__ == "__main__":
    unittest.main()
