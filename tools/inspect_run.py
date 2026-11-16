import json
import sqlite3
import sys

rid = sys.argv[1] if len(sys.argv) > 1 else "run-1794368444191-6c24"
c = sqlite3.connect("runs.db")
c.row_factory = sqlite3.Row
run = c.execute("select * from runs where id=?", (rid,)).fetchone()
if not run:
    print("not found:", rid)
    raise SystemExit(1)
print(f"RUN {rid}  success={run['success']}  attempts={run['rounds']}  "
      f"tokens={run['total_tokens']}  cost={run['total_cost']}")

for v in c.execute("select node_id,verifier,passed,confidence,evidence from verdicts "
                   "where run_id=? order by id", (rid,)):
    ev = json.loads(v["evidence"])
    tag = "OK " if v["passed"] else "X  "
    if v["verifier"] == "recompute":
        extra = (f"missing={ev.get('missing_required')} "
                 f"halluc={ev.get('hallucinated_numbers')} "
                 f"unver={ev.get('unverified_numbers')}")
    elif v["verifier"] == "rule":
        extra = f"problems={ev.get('problems')}"
    elif v["verifier"] == "llm_judge":
        extra = f"verdict={ev.get('verdict')} found={ev.get('verdict_found')}"
    else:
        extra = ""
    print(f"{tag}{v['node_id']:<10}{v['verifier']:<10}{v['confidence']:.2f}  {extra}")
