"""生成演示用销售数据集（确定性，可复现）。

运行：python futurecup/data/make_dataset.py
"""
import csv
import random
from pathlib import Path

REGIONS = ["华东", "华南", "华北", "西南", "东北"]
PRODUCTS = ["智能网关", "边缘计算盒", "数据采集卡", "工业传感器", "控制器模组"]
CHANNELS = ["直销", "渠道", "电商"]

OUT = Path(__file__).with_name("sales.csv")


def main(n: int = 240, seed: int = 20261109) -> None:
    rnd = random.Random(seed)
    rows = []
    for i in range(1, n + 1):
        month = rnd.randint(1, 9)
        day = rnd.randint(1, 28)
        qty = rnd.choice([1, 2, 3, 5, 8, 12, 20])
        price = rnd.choice([880.0, 1580.0, 2600.0, 4200.0, 6800.0])
        discount = rnd.choice([0.0, 0.05, 0.1, 0.15])
        # 故意留 3 条脏数据，用于演示清洗环节
        if i % 79 == 0:
            qty = ""
        if i % 113 == 0:
            price = -1.0
        rows.append(
            {
                "order_id": f"SO{20260000 + i}",
                "date": f"2026-{month:02d}-{day:02d}",
                "region": rnd.choice(REGIONS),
                "product": rnd.choice(PRODUCTS),
                "channel": rnd.choice(CHANNELS),
                "qty": qty,
                "unit_price": price,
                "discount": discount,
            }
        )
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT} rows={len(rows)}")


if __name__ == "__main__":
    main()
