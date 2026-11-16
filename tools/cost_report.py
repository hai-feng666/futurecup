import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parent.parent / "runs.db"
c = sqlite3.connect(db)
c.row_factory = sqlite3.Row
rows = list(c.execute("select id,config,status,total_tokens,total_cost,success from runs "
                      "order by started"))
real = [r for r in rows if "openai" in (r["config"] or "")]
mock = [r for r in rows if "mock" in (r["config"] or "")]
tok = sum(r["total_tokens"] or 0 for r in real)
cost = sum(r["total_cost"] or 0 for r in real)
print(f"总记录 {len(rows)} 条：真模型 {len(real)} 条，mock {len(mock)} 条")
print(f"真模型累计 tokens = {tok}   按配置单价估算 = {cost:.4f} 元")
for r in real:
    print(f"  {r['id'][-13:]}  success={r['success']}  "
          f"tok={r['total_tokens'] or 0:>6}  cost={r['total_cost'] or 0:.4f}")
