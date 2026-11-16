import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rid = sys.argv[1]
node = sys.argv[2] if len(sys.argv) > 2 else "analyze"
targets = [t for t in sys.argv[3:]] or ["928664", "1377442", "21000"]

c = sqlite3.connect(ROOT / "runs.db")
c.row_factory = sqlite3.Row
for r in c.execute("select attempt, output from nodes where run_id=? and node_id=? "
                   "order by attempt", (rid, node)):
    text = r["output"] or ""
    hits = []
    for line in text.splitlines():
        for t in targets:
            if t in line.replace(",", ""):
                hits.append(line.strip()[:200])
                break
    print(f"--- attempt {r['attempt']} （{len(text)} 字）---")
    for h in hits[:6]:
        print("   ", h)
    if not hits:
        print("    （未出现目标数字）")
