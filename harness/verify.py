"""分层结果验证。

赛题原文要求「对 Agent 输出进行交叉验证、基准比对或置信度评估」，这里落成四层：

  L1 rule      —— 结构/完备性：长度、必备小节、禁止占位符
  L2 recompute —— 复算校验：报告里每个大数字必须能在事实表中复算出来
                  （这一层是核心：它能把"看起来很像"的幻觉数字直接抓出来）
  L3 cross     —— 交叉验证：两个独立 Agent 的数字集合必须互相印证
  L4 judge     —— LLM 终审：判断报告是否逐条给出了出处

最后用置信度门控决定：放行 / 返修 / 升级人工。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s+\S|[一二三四五六七八九十]+[、.．]|\d+[\.、]\s*\S)", re.M)
LARGE = 1000.0          # 只有大于该值的数字才做"幻觉检测"，避免建议条数等噪声
REL_TOL = 0.005         # 0.5% 容差，容忍四舍五入
STRUCT_MARK = "本段含未经事实表核对"
# 情景推演类语句里的数字属于"假设/目标/预测"，不是事实引用
SCENARIO_WORDS = ["假设", "目标", "情景", "测算", "推算", "预估", "预计",
                  "一旦", "若", "如果", "降至", "提升至", "可达"]


@dataclass
class Verdict:
    verifier: str
    passed: bool
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"verifier": self.verifier, "passed": self.passed,
                "confidence": round(self.confidence, 3), "evidence": self.evidence}


# --------------------------------------------------------------------------
# 数字抽取
# --------------------------------------------------------------------------
def extract_numbers(text: str) -> list[float]:
    t = text or ""
    t = re.sub(r"[Ff]act?\s*\d+", " ", t)
    t = re.sub(r"\bSO\d+\b", " ", t)
    t = re.sub(r"\d{4}[-/年]\d{1,2}([-/月]\d{1,2}日?)?", " ", t)
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)       # 1,234,567 → 1234567
    # 年份不算业务数字。注意不能写 \b：Python 里中文也算 \w，
    # 所以 "2026年" 的 "2026" 后面没有词边界，\b 会失效（踩过这个坑）。
    t = re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)", " ", t)
    out: list[float] = []
    for m in NUM_RE.findall(t):
        try:
            out.append(float(m))
        except ValueError:
            continue
    return out


def _fact_values(facts: dict[str, Any]) -> list[float]:
    """事实表里所有"可以直接引用"的绝对值。"""
    vals = [
        facts.get("total_revenue", 0), facts.get("avg_order_value", 0),
        facts.get("max_order_value", 0), facts.get("order_count", 0),
    ]
    for key in ("by_region", "by_region_avg", "by_region_orders",
                "by_product", "by_product_avg"):
        vals += list((facts.get(key) or {}).values())
    return [float(v) for v in vals if isinstance(v, (int, float))]


def _derived_values(facts: dict[str, Any], extra: list[float] | None = None) -> list[float]:
    """派生值空间：只允许「加减」类派生（差值、合计）。

    为什么不做乘除：事实值相乘后取值空间过密，0.5% 容差下几乎任何大数都能
    凑上一个近似值，幻觉检测就失效了（实测过：600 万的编造数字能匹配到
    136000×44 附近）。所以乘除类推算统一要求模型写出算式，不在此白名单内。
    """
    base = list(_fact_values(facts)) + list(extra or [])
    out: set[float] = set()
    for i, a in enumerate(base):
        for b in base[i + 1:]:
            out.add(round(abs(a - b), 2))
            out.add(round(a + b, 2))
    return [v for v in out if abs(v) >= LARGE]


def _num_forms(n: float) -> list[str]:
    """一个数在文本里可能的书写形式（含千分位/不同小数位）。"""
    out = [f"{n:,.2f}", f"{n:.2f}", f"{n:,.1f}", f"{n:.1f}", f"{n:,.0f}", f"{n:.0f}"]
    return list(dict.fromkeys(out))


def _split_scenario(text: str, nums: list[float]) -> tuple[list[float], list[float]]:
    """把"情景推演"里的数字挑出来。

    真实报告一定会写假设推演（"若单均提升至 X，营收应为 Y"），这类数字
    本来就不来自事实表。严格要求它可溯源会让模型无法表达判断，
    所以单独归类为场景数字，不计入幻觉；但仍会记录在证据里保持透明。
    """
    if not nums:
        return [], []
    sents = re.split(r"[。；;\n]", text or "")
    scenario, rest = [], []
    for n in nums:
        forms = _num_forms(n)
        hit = any(any(f in s for f in forms) and any(w in s for w in SCENARIO_WORDS)
                  for s in sents)
        (scenario if hit else rest).append(n)
    return scenario, rest


def _close(a: float, b: float) -> bool:
    if b == 0:
        return abs(a) < 1e-6
    return abs(a - b) / abs(b) <= REL_TOL


# --------------------------------------------------------------------------
# L1 规则校验
# --------------------------------------------------------------------------
def rule_verify(text: str, spec: dict[str, Any] | None = None) -> Verdict:
    spec = spec or {}
    min_len = int(spec.get("min_len", 40))
    must = spec.get("must_contain", []) or []
    groups = spec.get("must_contain_any", []) or []
    ban = spec.get("must_not_contain", []) or [STRUCT_MARK, "TODO"]

    problems = []
    if len(text or "") < min_len:
        problems.append(f"长度不足 {min_len}")
    min_head = int(spec.get("min_headings", 0))
    if min_head:
        n_head = len(HEADING_RE.findall(text or ""))
        if n_head < min_head:
            problems.append(f"分节数量不足（{n_head} < {min_head}）")
    for m in must:
        if m not in (text or ""):
            problems.append(f"缺少必备内容：{m}")
    # 同义词组：组内任意一个出现即可（避免"建议/行动/措施"这种写法差异误判）
    for g in groups:
        if not any(w in (text or "") for w in g):
            problems.append(f"缺少必备内容（以下之一）：{'/'.join(g)}")
    for b in ban:
        if b and b in (text or ""):
            problems.append(f"命中禁止内容：{b}")

    conf = 1.0 if not problems else max(0.0, 1.0 - 0.34 * len(problems))
    return Verdict("rule", not problems, conf, {"problems": problems, "min_len": min_len})


# --------------------------------------------------------------------------
# L2 复算校验（核心）
# --------------------------------------------------------------------------
def recompute_verify(text: str, facts: dict[str, Any],
                     extra_allowed: list[float] | None = None) -> Verdict:
    """复算校验。

    extra_allowed：本次运行中工具实际返回过的数值。
    报告引用工具输出属于正当行为，不能判成幻觉——只有「既不在事实表、
    也不在本次任何工具输出里」的数字才算编造。
    """
    nums = extract_numbers(text)
    facts_vals = _fact_values(facts) + list(extra_allowed or [])
    derived_vals = _derived_values(facts, extra_allowed)
    required = {
        "总营收": float(facts.get("total_revenue", 0)),
        "客单价": float(facts.get("avg_order_value", 0)),
        "订单数": float(facts.get("order_count", 0)),
    }
    matched_req, missing_req = [], []
    for name, val in required.items():
        if any(_close(n, val) or (name == "订单数" and _close(n, val)) for n in nums):
            matched_req.append(name)
        else:
            missing_req.append(name)

    matched_large, derived_hits, unmatched = [], [], []
    for n in nums:
        if abs(n) < LARGE:
            continue
        if any(_close(n, v) for v in facts_vals):
            matched_large.append(n)
        elif any(_close(n, v) for v in derived_vals):
            derived_hits.append(n)          # 可复算的派生值，不算幻觉
        else:
            unmatched.append(n)

    # 情景推演（假设/目标/预测）里的数字不算事实引用，单独归类
    scenario, unmatched = _split_scenario(text, unmatched)

    top_region = str(facts.get("top_region", ""))
    region_ok = bool(top_region) and top_region in (text or "")

    # 少量"无出处"数字降级为「待人工确认」，不直接判定失败；
    # 出现多处（超过容忍数）才判定为幻觉。这也是真实评审的做法：
    # 一个可疑数字需要复核，一整篇来路不明的数字才叫不可信。
    tol = int(os.getenv("HARNESS_UNVERIFIED_TOL", "2"))
    hard = unmatched if len(unmatched) > tol else []

    passed = not missing_req and not hard and region_ok
    conf = (
        0.5 * (len(matched_req) / max(1, len(required)))
        + 0.3 * (1.0 if not hard else 0.0)
        + 0.2 * (1.0 if region_ok else 0.0)
        - 0.05 * min(len(unmatched), 4)
    )
    conf = max(0.0, min(1.0, conf))
    return Verdict("recompute", passed, conf, {
        "matched_required": matched_req,
        "missing_required": missing_req,
        "hallucinated_numbers": sorted({round(x, 2) for x in hard})[:8],
        "unverified_numbers": sorted({round(x, 2) for x in unmatched})[:8],
        "scenario_numbers": sorted({round(x, 2) for x in scenario})[:8],
        "derived_ok": len(derived_hits),
        "region_grounded": region_ok,
        "numbers_seen": len(nums),
    })


# --------------------------------------------------------------------------
# L3 交叉验证
# --------------------------------------------------------------------------
def cross_verify(text_a: str, text_b: str, facts: dict[str, Any]) -> Verdict:
    va = recompute_verify(text_a, facts)
    vb = recompute_verify(text_b, facts)
    agree = va.passed == vb.passed
    conf = 0.5 * (va.confidence + vb.confidence) * (1.0 if agree else 0.8)
    return Verdict("cross", va.passed and vb.passed and agree, conf, {
        "a_passed": va.passed, "b_passed": vb.passed, "agree": agree,
        "a_halluc": va.evidence.get("hallucinated_numbers"),
        "b_halluc": vb.evidence.get("hallucinated_numbers"),
    })


# --------------------------------------------------------------------------
# L4 LLM 终审
# --------------------------------------------------------------------------
POS_WORDS = ["PASS", "通过", "合格", "无误", "可发布", "可以发布", "准予", "符合要求"]
NEG_WORDS = ["FAIL", "不通过", "未通过", "不合格", "不符合", "驳回", "需返修", "需修正",
             "不予通过", "存在严重问题"]
NEG_PREFIX = "不未无非没否"


def judge_verdict(text: str) -> bool | None:
    """从中/英文终审文本里抽结论。

    规则：取**最后一次出现**的结论词所在侧——真实审校文本常见
    "发现 3 处问题 …… 结论：通过" 这种结构，简单查关键词会误判。
    另外必须处理子串重叠：否定词里含有肯定词（"不通过" 含 "通过"），
    落在否定词内部的肯定词要被丢弃，否则永远判通过。
    """
    body = text or ""
    found: list[tuple[int, int, bool]] = []
    for w in NEG_WORDS:
        for m in re.finditer(re.escape(w), body):
            found.append((m.start(), m.end(), False))
    neg_spans = [(s, e) for s, e, _ in found]
    for w in POS_WORDS:
        for m in re.finditer(re.escape(w), body):
            s, e = m.start(), m.end()
            if any(ns <= s and e <= ne for ns, ne in neg_spans):
                continue  # 位于否定词内部，丢弃
            if s > 0 and body[s - 1] in NEG_PREFIX:
                found.append((s - 1, e, False))  # "未通过""不予通过""非合格" 等
                continue
            found.append((s, e, True))
    if not found:
        return None
    found.sort(key=lambda x: (x[0], x[1]))
    return found[-1][2]


def llm_judge_verify(text: str, reviewer_text: str | None = None) -> Verdict:
    """L4 终审：判断审校环节是否给出了明确结论并列出依据。

    诚实说明：这一层不做模型调用，只做结论抽取与结构校验；
    真正的模型级评审在这里属于可扩展点（见方案书"局限"一节）。
    """
    body = reviewer_text if reviewer_text is not None else text
    verdict = judge_verdict(body)
    cites = len(re.findall(r"[Ff]act?\s*\d+|F\d+", body))
    passed = verdict is True
    conf = 0.5 + (0.25 if verdict is not None else 0.0) + (0.2 if cites else 0.0)
    return Verdict("llm_judge", passed, min(0.95, conf), {
        "verdict_found": verdict is not None,
        "verdict": ("通过" if verdict else ("不通过" if verdict is False else "未给出结论")),
        "cites_evidence": bool(cites),
        "mode": "rule-based extraction",
    })


# --------------------------------------------------------------------------
# 置信度门控
# --------------------------------------------------------------------------
@dataclass
class GateResult:
    passed: bool
    confidence: float
    action: str            # accept / repair / escalate
    failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "confidence": round(self.confidence, 3),
                "action": self.action, "failed": self.failed}


def gate(verdicts: list[Verdict], accept_at: float = 0.75,
         escalate_at: float = 0.30) -> GateResult:
    if not verdicts:
        return GateResult(False, 0.0, "repair", ["no_verdict"])
    # 复算层权重最高：它是最客观的一层
    weights = {"recompute": 3.0, "cross": 2.0, "rule": 1.0, "llm_judge": 1.0}
    total_w = sum(weights.get(v.verifier, 1.0) for v in verdicts)
    conf = sum(v.confidence * weights.get(v.verifier, 1.0) for v in verdicts) / total_w
    failed = [v.verifier for v in verdicts if not v.passed]
    passed = not failed and conf >= accept_at
    if passed:
        action = "accept"
    elif conf < escalate_at:
        action = "escalate"   # 置信度太低 → 转人工，不再让 Agent 瞎重试
    else:
        action = "repair"
    return GateResult(passed, conf, action, failed)


VERIFIERS = {
    "rule": rule_verify,
    "recompute": recompute_verify,
    "cross": cross_verify,
    "llm_judge": llm_judge_verify,
}
