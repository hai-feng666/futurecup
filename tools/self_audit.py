"""整体自审：测试、前端语法、截图匹配、文件一致性。"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PY = r"D:\develop\python\python.exe"
NODE = (r"C:\Users\Fan120120\.dsh\dsh-runtimes\dsh-primary-runtime"
        r"\dependencies\node\bin\node.exe")


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="ignore", **kw)


print("=== A) 单元测试 ===")
r = run([PY, "-m", "unittest", "discover", "-s", "tests"])
print([ln for ln in r.stderr.splitlines() if ln.startswith("Ran ") or ln.strip() == "OK"
       or ln.startswith("OK") or ln.startswith("FAILED")][-3:] or r.stderr[-300:])

print("=== B) 控制台前端语法 ===")
from harness.console import PAGE  # noqa: E402
js = re.search(r"<script>(.*)</script>", PAGE, re.S).group(1)
tmp = ROOT / "c.js"
tmp.write_text(js, encoding="utf-8")
r = run([NODE, "--check", str(tmp)])
print("JS OK" if r.returncode == 0 else f"JS 错误: {r.stderr[:200]}")
tmp.unlink(missing_ok=True)

print("=== C) 截图文件名是否与生成脚本匹配 ===")
src = ((ROOT / "tools/make_proposal.py").read_text(encoding="utf-8")
       + (ROOT / "tools/make_deck.py").read_text(encoding="utf-8"))
need = set(re.findall(r'"(0[1-5]-[^"]+\.png)"', src))
have = {p.name for p in (ROOT / "docs/截图").glob("*.png")}
print("需要:", sorted(need))
print("已有:", sorted(have))
print("缺:", sorted(need - have) or "无", " 多:", sorted(have - need) or "无")

print("=== D) 文档中的过期表述 ===")
bad = []
for f in ["README.md", "docs/参赛作战手册.md"]:
    for i, line in enumerate((ROOT / f).read_text(encoding="utf-8").splitlines(), 1):
        for kw in ("6 个 Agent", "6 个节点", "六个角色", "素材说明"):
            if kw in line:
                bad.append(f"{f}:{i}  {line.strip()[:60]}")
print("\n".join(bad) or "无")

print("=== E) 交付物清单 ===")
for f in ["docs/方案书.pdf", "docs/方案书.docx", "docs/方案讲解PPT.pptx"]:
    p = ROOT / f
    print(f"  {f:<28}{'OK' if p.exists() else '缺失':<6}"
          f"{p.stat().st_size/1024:.0f} KB" if p.exists() else f"  {f} 缺失")
