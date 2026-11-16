"""工具层：Agent 可调用的外部能力。

刻意只用标准库实现（csv / sqlite3 / statistics），这样评审专家 clone 下来
不装任何第三方包就能跑——这是「可复现性」最省事也最硬的证明。

包含三个工具：
- csv_profile : 数据画像 + 清洗 + 事实表（事实表是复算校验的唯一事实来源）
- sql_query   : 把 CSV 载入内存 SQLite 后执行只读 SQL，让 LLM 用真 SQL 取数
- python_eval : 受限 Python 求值，用于生成清洗/统计片段
"""
from __future__ import annotations

import atexit
import csv
import io
import json
import sqlite3
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_SQL = ("select", "with")


# --------------------------------------------------------------------------
# 数据装载与清洗（工具与校验器共用同一套规则，保证「复算」有确定基准）
# --------------------------------------------------------------------------
def _read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def clean_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (干净行, 被剔除行)。规则写死在代码里，不交给 LLM 决定。"""
    good: list[dict[str, Any]] = []
    bad: list[dict[str, Any]] = []
    for r in rows:
        try:
            qty = int(str(r.get("qty", "")).strip())
            price = float(str(r.get("unit_price", "")).strip())
            disc = float(str(r.get("discount", "0")).strip() or 0)
        except (TypeError, ValueError):
            bad.append({**r, "_reason": "数值字段缺失或非数值"})
            continue
        if qty <= 0 or price <= 0:
            bad.append({**r, "_reason": "数量或单价非正"})
            continue
        if not (0 <= disc < 1):
            bad.append({**r, "_reason": "折扣越界"})
            continue
        revenue = round(qty * price * (1 - disc), 2)
        good.append({**r, "qty": qty, "unit_price": price, "discount": disc,
                     "revenue": revenue})
    return good, bad


def compute_facts(path: str | Path) -> dict[str, Any]:
    """事实表：一次运行里所有数字的唯一出处。"""
    raw = _read_rows(path)
    good, bad = clean_rows(raw)
    revenues = [r["revenue"] for r in good]
    total = round(sum(revenues), 2)
    mean = statistics.fmean(revenues) if revenues else 0.0
    stdev = statistics.pstdev(revenues) if len(revenues) > 1 else 0.0
    outliers = [r for r in good if abs(r["revenue"] - mean) > 3 * stdev] if stdev else []

    def agg(key: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in good:
            out[str(r[key])] = round(out.get(str(r[key]), 0.0) + r["revenue"], 2)
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    by_region = agg("region")
    by_product = agg("product")

    def agg_count(key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in good:
            out[str(r[key])] = out.get(str(r[key]), 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    region_orders = agg_count("region")
    region_avg = {k: round(by_region[k] / region_orders[k], 2)
                  for k in by_region if region_orders.get(k)}

    return {
        "rows_raw": len(raw),
        "rows_clean": len(good),
        "rows_dropped": len(bad),
        "dropped_samples": [b["_reason"] for b in bad][:5],
        "order_count": len(good),
        "total_revenue": total,
        "avg_order_value": round(total / len(good), 2) if good else 0.0,
        "max_order_value": round(max(revenues), 2) if revenues else 0.0,
        "by_region": by_region,
        "by_region_orders": region_orders,
        "by_region_avg": region_avg,
        "by_product": by_product,
        "top_region": next(iter(by_region), ""),
        "top_product": next(iter(by_product), ""),
        "outlier_count": len(outliers),
        "outlier_orders": [o["order_id"] for o in outliers],
    }


def facts_as_text(f: dict[str, Any]) -> str:
    """把事实表渲染成给 LLM 看的文本（编号 F1..Fn，便于引用与核对）。"""
    orders = f.get("by_region_orders") or {}
    avg = f.get("by_region_avg") or {}
    lines = [
        f"F1 原始记录数={f['rows_raw']}；清洗后={f['rows_clean']}；剔除={f['rows_dropped']}",
        f"F2 有效订单数={f['order_count']}",
        f"F3 总营收={f['total_revenue']}",
        f"F4 客单价={f['avg_order_value']}",
        f"F5 最大单笔={f['max_order_value']}",
        "F6 区域营收：" + "；".join(f"{k}={v}" for k, v in f["by_region"].items()),
        "F7 品类营收：" + "；".join(f"{k}={v}" for k, v in f["by_product"].items()),
        f"F8 营收离群订单数={f['outlier_count']}（订单号：{', '.join(f['outlier_orders']) or '无'}）",
        f"F9 营收第一区域={f['top_region']}；第一品类={f['top_product']}",
        "F10 区域订单数：" + "；".join(f"{k}={v}" for k, v in orders.items()),
        "F11 区域单均营收：" + "；".join(f"{k}={v}" for k, v in avg.items()),
        "",
        "【引用规则】",
        "1. 任何绝对值都必须来自 F1–F11，并在其后标注编号，例如 1,527,708.0 元 [F6]。",
        "2. 派生值（差值、倍数、占比、合计）必须写出计算式，例如 928 元（25,972−25,044）。",
        "3. 不允许出现既无编号也无计算式的绝对值。",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 工具实现
# --------------------------------------------------------------------------
def tool_csv_profile(dataset: str) -> dict[str, Any]:
    facts = compute_facts(ROOT / dataset if not Path(dataset).is_absolute() else dataset)
    return {"ok": True, "data": facts, "text": facts_as_text(facts)}


_SQL_CACHE: dict[str, sqlite3.Connection] = {}


@atexit.register
def _close_sql_cache() -> None:
    """进程退出时关闭内存数据库连接。

    不注册这个钩子的话，Python 会在解释器退出时打印
    ResourceWarning: unclosed database —— 功能没问题，但演示时很难看。
    """
    while _SQL_CACHE:
        _, conn = _SQL_CACHE.popitem()
        try:
            conn.close()
        except sqlite3.Error:
            pass


def _memdb(dataset: str) -> sqlite3.Connection:
    key = str(ROOT / dataset)
    if key in _SQL_CACHE:
        return _SQL_CACHE[key]
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    good, _ = clean_rows(_read_rows(key))
    if not good:
        raise ValueError("数据集为空")
    cols = list(good[0].keys())
    conn.execute(f"CREATE TABLE sales({','.join(c + ' REAL' if c in ('qty','unit_price','discount','revenue') else c + ' TEXT' for c in cols)})")
    conn.executemany(
        f"INSERT INTO sales VALUES({','.join('?' * len(cols))})",
        [tuple(r[c] for c in cols) for r in good],
    )
    conn.commit()
    _SQL_CACHE[key] = conn
    return conn


def tool_sql_query(dataset: str, query: str) -> dict[str, Any]:
    q = (query or "").strip().rstrip(";")
    if q.split(" ")[0].lower() not in ALLOWED_SQL:
        return {"ok": False, "error": "只允许只读查询（SELECT/WITH）", "text": ""}
    try:
        cur = _memdb(dataset).execute(q)
        rows = cur.fetchall()
        names = [d[0] for d in cur.description] if cur.description else []
        data = [dict(zip(names, r)) for r in rows[:200]]
        return {"ok": True, "data": data, "text": json.dumps(data[:200], ensure_ascii=False)}
    except sqlite3.Error as e:
        return {"ok": False, "error": f"SQL 执行失败：{e}", "text": ""}


def tool_python_eval(code: str) -> dict[str, Any]:
    """受限执行：只有白名单内置函数，结果写入变量 result。"""
    safe_builtins = {
        "len": len, "sum": sum, "min": min, "max": max, "round": round,
        "abs": abs, "sorted": sorted, "float": float, "int": int, "str": str,
    }
    ns: dict[str, Any] = {"__builtins__": safe_builtins}
    try:
        exec(code, ns, ns)  # noqa: S102 —— 演示用受限沙箱，局限已在文档中说明
        out = ns.get("result", "")
        return {"ok": True, "data": out,
                "text": out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"执行失败：{e}", "text": ""}


TOOLS = {
    "csv_profile": tool_csv_profile,
    "sql_query": tool_sql_query,
    "python_eval": tool_python_eval,
}


def run_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = TOOLS.get(name)
    if not fn:
        return {"ok": False, "error": f"未注册的工具：{name}", "text": ""}
    try:
        return fn(**args)
    except TypeError as e:
        return {"ok": False, "error": f"参数错误：{e}", "text": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"工具异常：{e}", "text": ""}
