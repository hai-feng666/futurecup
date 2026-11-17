"""列出最近的运行，便于挑选截图基准。"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
c = sqlite3.connect(ROOT / "runs.db")
c.row_factory = sqlite3.Row
print(f"{'run_id':<16}{'开始':<10}{'尝试':<6}{'tokens':<9}{'成本':<10}{'成功'}")
for r in c.execute("select id,started,rounds,total_tokens,total_cost,success from runs "
                   "order by started desc limit 8"):
    print(f"{r['id'][-13:]:<16}{r['started'][11:]:<10}{r['rounds']:<6}"
          f"{r['total_tokens']:<9}{r['total_cost']:<10.4f}{r['success']}")
