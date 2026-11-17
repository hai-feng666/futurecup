"""删除被中断的运行（status=running 或 success 为空）留下的僵尸记录。"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
c = sqlite3.connect(ROOT / "runs.db")
bad = [r[0] for r in c.execute(
    "select id from runs where status='running' or success is null")]
print("待清理：", bad)
for rid in bad:
    for tbl in ("verdicts", "nodes", "metrics", "runs"):
        c.execute(f"delete from {tbl} where run_id=?" if tbl != "runs"
                  else "delete from runs where id=?", (rid,))
c.commit()
print("剩余运行数：", c.execute("select count(*) from runs").fetchone()[0])
for r in c.execute("select id,started,status,success from runs order by started desc limit 5"):
    print("  ", r)
