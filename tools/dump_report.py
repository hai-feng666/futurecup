"""把库里一次真实运行的报告导出为测试样本（一次性工具）。"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rid = sys.argv[1]
node = sys.argv[2] if len(sys.argv) > 2 else "report"
out = ROOT / "tests" / "fixtures" / "report_real_model.md"
out.parent.mkdir(parents=True, exist_ok=True)

c = sqlite3.connect(ROOT / "runs.db")
c.row_factory = sqlite3.Row
rows = c.execute("select output from nodes where run_id=? and node_id=? order by attempt",
                 (rid, node)).fetchall()
out.write_text(rows[-1]["output"], encoding="utf-8")
print(f"wrote {out} ({len(rows[-1]['output'])} chars)")
