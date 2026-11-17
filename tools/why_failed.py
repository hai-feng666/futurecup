"""检查一次运行的节点状态与错误，判断失败原因。"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
c = sqlite3.connect(ROOT / "runs.db")
c.row_factory = sqlite3.Row
rid = "run-1794878420473-2086"
run = c.execute("select * from runs where id=?", (rid,)).fetchone()
if not run:
    run = c.execute("select * from runs order by started desc limit 1").fetchone()
    rid = run["id"]
print("run:", rid, run["started"], "success=", run["success"], "attempts=", run["rounds"])
print()
for r in c.execute("select node_id,agent_id,attempt,status,error,latency_ms,"
                   "prompt_tokens+completion_tokens tok from nodes where run_id=? order by id",
                   (rid,)):
    err = (r["error"] or "")[:60]
    print(f"  {r['node_id']:<10}{r['agent_id']:<13}第{r['attempt']}轮 "
          f"{r['status']:<6}{r['latency_ms']:>6}ms {r['tok']:>5}tok  {err}")
print()
print("是否注入了演练错误值 7090000：",
      "是" if c.execute("select count(*) from nodes where run_id=? and prompt like '%7,090,000%'",
                        (rid,)).fetchone()[0] else "否")
