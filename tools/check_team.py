# -*- coding: utf-8 -*-
"""校验三份文档封面上的队伍名称是否已改为「阿巴阿巴」。"""
from pathlib import Path

from docx import Document
from pptx import Presentation

ROOT = Path(r"D:\deepseek\one\futurecup\docs")


def first_lines(docx_path, n=14):
    d = Document(docx_path)
    return [p.text.strip() for p in d.paragraphs[:n] if p.text.strip()]


for name in ["方案书.docx", "项目白皮书.docx"]:
    print(f"--- {name} ---")
    for line in first_lines(ROOT / name, 16):
        print("   ", line)
    print()

print("--- 方案讲解PPT.pptx 第1页 ---")
prs = Presentation(ROOT / "方案讲解PPT.pptx")
for shape in prs.slides[0].shapes:
    if shape.has_text_frame and shape.text_frame.text.strip():
        for line in shape.text_frame.text.splitlines():
            if line.strip():
                print("   ", line.strip())

print()
for name in ["方案书.docx", "项目白皮书.docx", "方案讲解PPT.pptx"]:
    p = ROOT / name
    blob = ""
    if p.suffix == ".docx":
        d = Document(p)
        blob = "\n".join(x.text for x in d.paragraphs)
        blob += "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
    else:
        prs = Presentation(p)
        blob = "\n".join(sh.text_frame.text for s in prs.slides for sh in s.shapes
                         if sh.has_text_frame)
    print(f"{name:<22} 阿巴阿巴: {'✓' if '阿巴阿巴' in blob else '✗'}   "
          f"旧名 hai-feng666: {'仍有' if 'hai-feng666' in blob else '无'}")
