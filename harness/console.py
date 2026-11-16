"""零依赖 Web 控制台（只用标准库 http.server）。

为什么不用 Streamlit：
1. 评审专家机器上 `pip install` 经常失败，而 `python -m harness.console` 一定能开；
2. 少一个依赖，"一键复现"的说服力就强一分；
3. 我们自己画 SVG 的 DAG 图，反而更好控制视觉。

启动：python -m harness.console --port 8080
"""
from __future__ import annotations

import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .engine import Executor, levels_of, load_flow
from .models import get_backend
from .store import Store
from .util import project_root

ROOT = project_root()
FLOWS = sorted((ROOT / "flows").glob("*.json"))

COLORS = {
    "pending": ("#e2e8f0", "#94a3b8"),
    "ok": ("#dcfce7", "#16a34a"),
    "repaired": ("#fef3c7", "#d97706"),
    "failed": ("#fee2e2", "#dc2626"),
}


# --------------------------------------------------------------------------
# SVG 渲染
# --------------------------------------------------------------------------
def render_svg(flow: dict[str, Any], nodes: list[dict[str, Any]]) -> str:
    levels = levels_of(flow)
    latest: dict[str, dict[str, Any]] = {}
    attempts: dict[str, int] = {}
    for n in nodes:
        latest[n["node_id"]] = n
        attempts[n["node_id"]] = max(attempts.get(n["node_id"], 0), int(n["attempt"]))

    box_w, box_h, gap_x, gap_y = 186, 66, 92, 34
    cols = len(levels)
    rows = max((len(lv) for lv in levels), default=1)
    width = max(560, cols * box_w + (cols - 1) * gap_x + 60)
    height = max(220, rows * box_h + (rows - 1) * gap_y + 60)

    pos: dict[str, tuple[float, float]] = {}
    for ci, lv in enumerate(levels):
        col_h = len(lv) * box_h + (len(lv) - 1) * gap_y
        top = (height - col_h) / 2
        for ri, n in enumerate(lv):
            pos[n["id"]] = (30 + ci * (box_w + gap_x), top + ri * (box_h + gap_y))

    deps = {}
    for n in flow["nodes"]:
        refs = n.get("depends_on")
        if refs is None:
            ids = [x["id"] for x in flow["nodes"]]
            refs = [i for i in ids if i != n["id"] and ("{" + i + "}") in n.get("task", "")]
        deps[n["id"]] = refs

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
             f'style="max-height:{height}px" xmlns="http://www.w3.org/2000/svg">',
             '<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="8" refY="3" '
             'orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#64748b"/></marker></defs>']

    for nid, ds in deps.items():
        for d in ds:
            if d not in pos or nid not in pos:
                continue
            x1, y1 = pos[d]
            x2, y2 = pos[nid]
            ax, ay = x1 + box_w, y1 + box_h / 2
            bx, by = x2, y2 + box_h / 2
            mx = (ax + bx) / 2
            parts.append(
                f'<path d="M{ax},{ay} C{mx},{ay} {mx},{by} {bx},{by}" fill="none" '
                f'stroke="#94a3b8" stroke-width="1.6" marker-end="url(#ar)"/>'
            )

    for n in flow["nodes"]:
        nid = n["id"]
        if nid not in pos:
            continue
        x, y = pos[nid]
        node = latest.get(nid)
        att = attempts.get(nid, 0)
        if node is None:
            state = "pending"
        elif node.get("status") == "error":
            state = "failed"
        elif att > 1:
            state = "repaired"
        else:
            state = "ok"
        fill, stroke = COLORS[state]
        agent = node["agent_id"] if node else "—"
        badge = f"第{att}轮" if att else n.get("role", "")
        parts.append(
            f'<g><rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="12" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.8"/>'
            f'<text x="{x + 14}" y="{y + 25}" font-size="14" font-weight="600" '
            f'fill="#0f172a">{nid}</text>'
            f'<text x="{x + 14}" y="{y + 45}" font-size="11.5" fill="#475569">'
            f'{agent}</text>'
            f'<text x="{x + box_w - 12}" y="{y + 45}" font-size="11" fill="{stroke}" '
            f'text-anchor="end">{badge}</text></g>'
        )
        if node and att > 1:
            parts.append(
                f'<text x="{x + 14}" y="{y + 60}" font-size="10" fill="#b45309">'
                f'已返修 {att - 1} 次</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------
# 请求处理
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    store: Store
    db_path: str = "runs.db"

    def log_message(self, fmt: str, *args: Any) -> None:  # 安静一点
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if u.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if u.path == "/api/runs":
            self._json(self.store.runs(30))
            return
        if u.path == "/api/state":
            rid = (qs.get("run") or [""])[0]
            runs = self.store.runs(1)
            if not rid:
                rid = runs[0]["id"] if runs else ""
            run = self.store.run(rid) if rid else None
            if not run:
                self._json({"run": None, "nodes": [], "verdicts": [], "metrics": {},
                            "svg": "", "final": ""})
                return
            nodes = self.store.nodes(rid)
            verdicts = self.store.verdicts(rid)
            flow = None
            for f in FLOWS:
                data = load_flow(f)
                if data.get("name") == run["flow"]:
                    flow = data
                    break
            svg = render_svg(flow, nodes) if flow else ""
            final_id = (flow or {}).get("final_node", "report")
            outs = [n for n in nodes if n["node_id"] == final_id]
            self._json({
                "run": run, "nodes": nodes, "verdicts": verdicts,
                "metrics": self.store.metrics(rid), "svg": svg,
                "final": outs[-1]["output"] if outs else "",
            })
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        u = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        if u.path != "/api/run":
            self._json({"error": "not found"}, 404)
            return

        mode = body.get("mode", "harness")
        fault = bool(body.get("fault"))
        flow_file = body.get("flow")
        if fault:
            os.environ["HARNESS_FORCE_FAULT"] = "1"
        else:
            os.environ["HARNESS_FORCE_FAULT"] = "0"

        def work() -> None:
            try:
                ex = Executor(self.store, get_backend(body.get("backend")))
                flow = ROOT / flow_file if flow_file else (ROOT / "flows" / "data_insight.json")
                ex.run(flow, mode=mode)
            except Exception as e:  # noqa: BLE001
                print(f"[console] run failed: {e}")

        threading.Thread(target=work, daemon=True).start()
        self._json({"started": True, "mode": mode})


PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>数诊编排 · 多智能体编排调度平台</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
background:#f8fafc;color:#0f172a}
header{background:#0f172a;color:#fff;padding:14px 22px;display:flex;
align-items:center;gap:16px}
header h1{font-size:17px;margin:0;font-weight:600;letter-spacing:.5px}
header .sub{font-size:12px;color:#94a3b8}
header .sp{flex:1}
button{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:9px 16px;
font-size:13px;cursor:pointer;font-family:inherit}
button.ghost{background:#1e293b;color:#cbd5e1}
button:hover{filter:brightness(1.1)}
.layout{display:flex;min-height:calc(100vh - 52px)}
aside{width:250px;border-right:1px solid #e2e8f0;background:#fff;padding:12px;
overflow:auto}
aside h2{font-size:12px;color:#64748b;text-transform:uppercase;margin:6px 0 10px;
letter-spacing:.8px}
.run{padding:9px 10px;border-radius:8px;cursor:pointer;font-size:12px;
border:1px solid transparent;margin-bottom:6px}
.run:hover{background:#f1f5f9}
.run.on{background:#eff6ff;border-color:#bfdbfe}
.run .id{font-family:ui-monospace,monospace;font-size:11px;color:#334155}
.tag{display:inline-block;padding:1px 7px;border-radius:99px;font-size:10.5px;
font-weight:600}
.ok{background:#dcfce7;color:#15803d}
.bad{background:#fee2e2;color:#b91c1c}
main{flex:1;padding:18px 22px;overflow:auto}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:11px 15px;
min-width:118px}
.card .k{font-size:11px;color:#64748b}
.card .v{font-size:19px;font-weight:650;margin-top:3px}
.panel{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;
margin-bottom:16px}
.panel h3{font-size:13px;margin:0 0 12px;color:#334155}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;color:#64748b;font-weight:600;padding:6px 8px;
border-bottom:1px solid #e2e8f0;font-size:11.5px}
td{padding:7px 8px;border-bottom:1px solid #f1f5f9;vertical-align:top}
code{font-family:ui-monospace,monospace;font-size:11.5px}
pre{white-space:pre-wrap;font-size:12.5px;line-height:1.75;margin:0;
font-family:inherit;background:#f8fafc;padding:12px;border-radius:8px}
.err{color:#b91c1c;font-weight:600}
.why{font-size:11px;color:#475569;max-width:300px}
</style></head><body>
<header>
  <h1>数诊编排 · 多智能体编排调度平台</h1>
  <span class="sub">DAG 编排 / 能力画像调度 / 分层验证 / 自循环 / 可回放</span>
  <span class="sp"></span>
  <button onclick="run(false)">▶ 运行一次</button>
  <button class="ghost" onclick="run(true)">⚡ 强制故障运行（演示返修）</button>
</header>
<div class="layout">
  <aside><h2>运行历史</h2><div id="runs"><div class="sub">加载中…</div></div></aside>
  <main>
    <div class="cards" id="cards"></div>
    <div class="panel"><h3>工作流编排（DAG，按依赖自动分层；同一层并行执行）</h3>
      <div id="svg"></div></div>
    <div class="panel"><h3>节点执行记录（含调度决策）</h3><div id="nodes"></div></div>
    <div class="panel"><h3>分层验证记录</h3><div id="verdicts"></div></div>
    <div class="panel"><h3>最终交付物</h3><pre id="final">（暂无）</pre></div>
  </main>
</div>
<script>
let current="";
async function j(u,o){const r=await fetch(u,o);return r.json()}
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
async function loadRuns(){
  const rs=await j("/api/runs");
  document.getElementById("runs").innerHTML = rs.length? rs.map(r=>`
    <div class="run ${r.id===current?'on':''}" onclick="pick('${r.id}')">
      <div class="id">${r.id.slice(-14)}</div>
      <div style="margin-top:4px;display:flex;gap:6px;align-items:center">
        <span class="tag ${r.success?'ok':'bad'}">${r.success?'成功':(r.success===0?'未通过':'运行中')}</span>
        <span style="color:#94a3b8;font-size:11px">${r.started.slice(11)}</span>
      </div></div>`).join("") : "<div class='sub'>还没有运行记录</div>";
}
function pick(id){current=id;refresh()}
async function refresh(){
  const d=await j("/api/state?run="+encodeURIComponent(current));
  if(!d.run){document.getElementById("final").textContent="还没有运行记录，点右上角「运行一次」。";return}
  current=d.run.id;
  document.getElementById("svg").innerHTML=d.svg;
  const m=d.metrics||{};
  document.getElementById("cards").innerHTML=[
    ["是否通过", d.run.success? "通过":"未通过"],
    ["尝试次数", d.run.rounds],
    ["总 tokens", d.run.total_tokens],
    ["总成本", "¥"+Number(d.run.total_cost).toFixed(4)],
    ["耗时", (m.wall_ms||0)+" ms"],
    ["人工介入", m.human_interventions||0],
  ].map(([k,v])=>`<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");

  document.getElementById("nodes").innerHTML = `<table><tr>
    <th>节点</th><th>Agent</th><th>轮次</th><th>耗时</th><th>tokens</th><th>调度决策</th></tr>`+
    d.nodes.map(n=>{
      const dec=JSON.parse(n.decision||"{}");
      return `<tr><td><code>${n.node_id}</code></td><td>${n.agent_id}</td>
      <td>${n.attempt}</td><td>${n.latency_ms}ms</td>
      <td>${n.prompt_tokens+n.completion_tokens}</td>
      <td class="why">${esc(dec.reason||"")}</td></tr>`}).join("")+`</table>`;

  document.getElementById("verdicts").innerHTML = d.verdicts.length? `<table><tr>
    <th>节点</th><th>验证器</th><th>结论</th><th>置信度</th><th>证据</th></tr>`+
    d.verdicts.map(v=>{
      const ev=JSON.parse(v.evidence||"{}");
      let detail="";
      if(v.verifier==="recompute") detail=`缺失=${JSON.stringify(ev.missing_required||[])} 幻觉数字=${JSON.stringify(ev.hallucinated_numbers||[])}`;
      else if(v.verifier==="rule") detail=`问题=${JSON.stringify(ev.problems||[])}`;
      return `<tr><td><code>${v.node_id}</code></td><td>${v.verifier}</td>
      <td class="${v.passed?'':'err'}">${v.passed?'通过':'未通过'}</td>
      <td>${Number(v.confidence).toFixed(2)}</td>
      <td class="why">${esc(detail)}</td></tr>`}).join("")+`</table>`
    : "<div class='sub'>本次运行未启用验证器</div>";

  document.getElementById("final").textContent=d.final||"（暂无）";
  loadRuns();
}
async function run(fault){
  await fetch("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({mode:"harness",fault:fault})});
  setTimeout(refresh,300); setTimeout(refresh,900); setTimeout(refresh,1600);
}
loadRuns(); refresh(); setInterval(refresh, 2500);
</script></body></html>"""


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--db", default=os.getenv("HARNESS_DB", "runs.db"))
    args = ap.parse_args(argv)
    Handler.store = Store(args.db)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"控制台已启动： http://127.0.0.1:{args.port}   （Ctrl+C 停止）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
