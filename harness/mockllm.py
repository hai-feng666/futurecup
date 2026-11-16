"""离线确定性 Mock 后端。

用途有两个，都很关键：
1. 让评审专家在没有 API key 的机器上也能完整跑通流程（可复现性）；
2. 让「验证失败 → 自动重跑 → 修好」这个 Self-Loop 能稳定复现，不必等运气。

注意：mock 产生的数字是**模拟值**，用于验证工程链路，不能当作评测结论。
评测脚本会在输出里显式标注数据来源。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

FAIL_TAG = "【本段含未经事实表核对的数字】"


def _find(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text or "")
    return float(m.group(1)) if m else None


def _h(*parts: str) -> float:
    """稳定哈希 → [0,1)，保证同一任务每次跑出同样的结果。"""
    d = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(d[:4], "big") / 2**32


def _corrupt(value: float) -> str:
    """把数字改成"看起来很像但是错的"，模拟 LLM 的算术漂移。"""
    return f"{round(value * 1.1 + 137.0, 2)}"


def _facts_block(f: dict[str, Any]) -> str:
    return (
        f"总营收 {f['total_revenue']} 元；订单数 {f['order_count']}；"
        f"客单价 {f['avg_order_value']} 元；第一区域 {f['top_region']}"
    )


def generate(role: str, prompt: str, facts: dict[str, Any] | None,
             attempt: int, meta: dict[str, Any]) -> str:
    """按角色生成确定性文本。attempt>1 时视为"已收到返修意见"。"""
    f = facts or {}
    task_key = str(meta.get("task_key", "default"))
    # 第 1 次尝试按任务哈希决定是否漂移；被注入故障时一定漂移
    drift = meta.get("inject_fault") or (_h(task_key, role) < 0.34)
    repaired = attempt > 1

    total = float(f.get("total_revenue", 1000000.0))
    avg = float(f.get("avg_order_value", 5000.0))
    orders = int(f.get("order_count", 200))
    region = f.get("top_region", "华东")
    regions = f.get("by_region", {}) or {}
    products = f.get("by_product", {}) or {}
    outliers = int(f.get("outlier_count", 0))

    show_total = f"{total}" if (repaired or not drift) else _corrupt(total)
    show_avg = f"{avg}" if (repaired or not drift) else _corrupt(avg)

    head = "[返修后重算]" if repaired else "[首次计算]"

    if role == "data_profiler":
        return (
            f"【数据画像】{head}\n"
            f"1. 记录规模：原始 {f.get('rows_raw')} 行，字段 {len(f.get('by_region', {})) + 6} 列。\n"
            f"2. 缺失情况：qty 存在空值，unit_price 存在非正取值，已定位到具体 order_id。\n"
            f"3. 数据质量：剔除 {f.get('rows_dropped')} 行（原因：{'; '.join(f.get('dropped_samples', [])) or '数值缺失'}）。\n"
            f"4. 有效订单 {orders} 笔，总营收 {total} 元。\n"
            f"5. 离群：营收离群订单 {outliers} 笔（{', '.join(f.get('outlier_orders', [])) or '无'}）。"
        )

    if role == "cleaner":
        return (
            "【清洗规则清单】\n"
            f"R1 丢弃 qty 为空或非正整数的记录（影响 {f.get('rows_dropped')} 行，最高优先级）。\n"
            "R2 丢弃 unit_price<=0 的记录（防止负营收污染汇总）。\n"
            "R3 对 discount 做 [0,1) 区间校验，越界置 0 并打标。\n"
            "R4 新增 revenue = qty*unit_price*(1-discount) 派生列，不覆盖原始列。\n"
            "R5 清洗过程全量留痕，原始文件只读，可随时回滚。"
        )

    if role == "analyst":
        top3 = list(regions.items())[:3]
        prod_top = list(products.items())[:2]
        body = (
            f"【经营分析】{head}\n"
            f"结论1：有效订单 {orders} 笔，总营收 {show_total} 元（依据 F2/F3）。\n"
            f"结论2：客单价 {show_avg} 元，接近行业中枢水平（依据 F4）。\n"
            f"结论3：{region} 区域营收最高（依据 F6），区域结构："
            + "；".join(f"{k}={v}" for k, v in top3) + "。\n"
            f"结论4：品类集中度较高，前二品类为 "
            + "；".join(f"{k}={v}" for k, v in prod_top) + "（依据 F7）。\n"
            f"结论5：存在 {outliers} 笔营收离群订单，需复核是否为大客户集采或录入错误（依据 F8）。\n"
            f"建议1：对{region}复制打法，优先投放头部品类。\n"
            "建议2：对离群订单做单独复核，避免冲击客单价口径。\n"
            "建议3：把 qty 缺失设为入库强校验，源头治理。"
        )
        if drift and not repaired:
            body += "\n" + FAIL_TAG
        return body

    if role == "writer":
        # 真实 LLM 会把上游数字「原样搬运」，所以这里也从上游文本里取数，
        # 这样上游漂移会真实地传到报告里，才能演示「返修 + 回事实表核对」。
        up_total = _find(prompt, r"总营收\s*([0-9]+(?:\.[0-9]+)?)\s*元")
        up_avg = _find(prompt, r"客单价\s*([0-9]+(?:\.[0-9]+)?)\s*元")
        if not repaired and up_total is not None:
            show_total = f"{up_total}"
        if not repaired and up_avg is not None:
            show_avg = f"{up_avg}"
        vals = list(regions.values())
        ratio = round(vals[0] / vals[-1], 2) if len(vals) > 1 and vals[-1] else 0.0
        lowest = list(regions.items())[-1] if regions else ("—", 0.0)
        body = (
            "【管理层诊断报告】\n"
            "一、总体盘面\n"
            f"报告期内有效订单 {orders} 笔，实现总营收 {show_total} 元，"
            f"客单价 {show_avg} 元 [F2][F3][F4]。\n"
            "二、结构特征\n"
            f"{region} 区域贡献营收 {next(iter(regions.values()), 0.0)} 元，为第一增长极；"
            f"{lowest[0]} 区域营收 {lowest[1]} 元为末位 [F6]。\n"
            f"区域间最大/最小营收比约 {ratio} 倍，集中度中等偏高；"
            "品类端头部两款贡献过半营收 [F7]。\n"
            "三、风险提示\n"
            f"存在 {outliers} 笔营收离群订单，若不单独复核，客单价口径会被高估 [F8]。\n"
            f"清洗阶段剔除 {f.get('rows_dropped')} 行记录，需在入库环节加校验 [F1]。\n"
            "四、行动建议\n"
            "1) 在头部区域复制投放策略，优先匹配头部品类；\n"
            "2) 建立离群订单复核队列，单独口径统计，避免冲击均值；\n"
            "3) 入库阶段强制校验数量与单价字段，从源头治理数据质量；\n"
            "4) 对单均偏低区域做量价拆解，定位是折扣过深还是小单占比过高。"
        )
        if drift and not repaired:
            body += "\n" + FAIL_TAG
        return body

    if role == "reviewer":
        ok = repaired or not drift
        verdict = "PASS" if ok else "FAIL"
        notes = (
            "所有数字均可在事实表 F1-F9 中找到出处，口径一致。"
            if ok
            else "发现 1 处数字无法在事实表中找到出处，判定需要返修。"
        )
        return f"【终审结论】{verdict}\n{notes}\n核对条目：F2/F3/F4/F6/F8。"

    # 通用型 Agent（基线用）：没有分环节核对，容易出算术漂移
    if drift:
        return (
            f"2026 年前三季度累计营收约 {show_total} 元，订单 {orders} 笔，"
            f"客单价约 {show_avg} 元。{region}表现最好。建议加大投放、优化结构。"
        )
    return (
        f"2026 年前三季度累计营收 {total} 元，订单 {orders} 笔，"
        f"客单价 {avg} 元。{region}表现最好。建议加大投放、优化结构。"
    )
