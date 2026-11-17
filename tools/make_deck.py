# -*- coding: utf-8 -*-
"""基于官方模版生成 15 页参赛 PPT。

设计约束（来自模版）：
- 13.33 x 7.5 英寸，深蓝科技背景，顶部三个 logo + 赛事名称
- 字体：思源黑体 CN；正文白字；截图垫白色圆角卡片承载深色文字
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt
from PIL import Image as PILImage

TPL = Path(r"C:\Users\Fan120120\Downloads\2026未来杯PPT模版.pptx")
IMG = Path(__file__).resolve().parent.parent / "docs" / "截图"
OUT = Path(__file__).resolve().parent.parent / "docs" / "方案讲解PPT.pptx"

FONT = "思源黑体 CN"
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SOFT = RGBColor(0xD8, 0xE6, 0xFF)
CYAN = RGBColor(0x5F, 0xD4, 0xFF)
DARK = RGBColor(0x14, 0x24, 0x4C)
GRAY = RGBColor(0x4A, 0x55, 0x68)
LIGHT = RGBColor(0xF4, 0xF7, 0xFC)
AMBER = RGBColor(0xD9, 0x77, 0x06)
GREEN = RGBColor(0x15, 0x80, 0x3D)
RED = RGBColor(0xB9, 0x1C, 0x1C)

W, H = 13.333, 7.5
MX = 0.45              # 左右边距
CW = W - 2 * MX        # 内容宽度
TITLE_Y = 0.55
BODY_Y = 1.42
BOTTOM = 7.04


def new_deck():
    prs = Presentation(str(TPL))
    # 清空示例页
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        prs.part.drop_rel(sldId.rId)
        sldIdLst.remove(sldId)
    return prs


def _tf(shape, size, color=WHITE, bold=False, align=PP_ALIGN.LEFT,
        spacing=1.0, font=FONT):
    tf = shape.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    r.font.name = font
    p.line_spacing = spacing
    return tf


def text(slide, x, y, w, h, content, size=16, color=WHITE, bold=False,
         align=PP_ALIGN.LEFT, spacing=1.15, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = _tf(box, size, color, bold, align, spacing)
    tf.vertical_anchor = anchor
    tf.paragraphs[0].runs[0].text = content
    return box


def lines(slide, x, y, w, h, items, size=15, color=WHITE, spacing=1.35,
          bullet=False, anchor=MSO_ANCHOR.TOP):
    """多行文本；items 支持 (文本, 颜色, 粗体) 三元组或纯字符串。"""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    first = True
    for it in items:
        if isinstance(it, tuple):
            body, col, bold = (it + (WHITE, False))[:3]
        else:
            body, col, bold = it, color, False
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.line_spacing = spacing
        p.space_after = Pt(5)
        if bullet:
            body = "· " + body
        r = p.add_run()
        r.text = body
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = col
        r.font.name = FONT
    return box


def title(slide, text_, sub=None):
    text(slide, MX, 0.50, CW, 0.60, text_, size=25, bold=True)
    bar = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(MX),
                                 Inches(1.14), Inches(0.62), Inches(0.055))
    bar.fill.solid()
    bar.fill.fore_color.rgb = CYAN
    bar.line.fill.background()
    bar.shadow.inherit = False
    if sub:
        text(slide, MX, 1.21, CW, 0.30, sub, size=12.5, color=SOFT)


def card(slide, x, y, w, h, fill=WHITE, line=None, radius=0.06):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                                Inches(w), Inches(h))
    sh.adjustments[0] = radius
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line:
        sh.line.color.rgb = line
        sh.line.width = Pt(1)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.text = ""
    return sh


def table_card(slide, x, y, w, h, headers, rows, widths, head_size=11.5,
               body_size=11, col_colors=None):
    """白卡片 + 原生表格（深色文字）。"""
    card(slide, x, y, w, h)
    inner_x, inner_y = x + 0.14, y + 0.12
    inner_w = w - 0.28
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(inner_x),
                                   Inches(inner_y), Inches(inner_w),
                                   Inches(h - 0.24))
    tbl = shape.table
    total = sum(widths)
    for i, cw in enumerate(widths):
        tbl.columns[i].width = Inches(inner_w * cw / total)
    tbl.rows[0].height = Inches(0.34)
    for j, htxt in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(0xE8, 0xEF, 0xFB)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = cell.margin_right = Inches(0.05)
        p = cell.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = htxt
        r.font.size = Pt(head_size)
        r.font.bold = True
        r.font.color.rgb = DARK
        r.font.name = FONT
    for i, row in enumerate(rows, 1):
        tbl.rows[i].height = Inches(0.30)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 else LIGHT
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.05)
            p = cell.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = str(val)
            r.font.size = Pt(body_size)
            r.font.color.rgb = DARK
            r.font.name = FONT
            if col_colors and j in col_colors:
                r.font.color.rgb = col_colors[j].get(str(val), DARK)
                if str(val) in col_colors[j]:
                    r.font.bold = True
    return shape


def picture(slide, filename, x, y, w=None, h=None, caption=None):
    path = IMG / filename
    if not path.exists():
        text(slide, x, y, 4, 0.4, f"（缺少 {filename}）", size=11, color=SOFT)
        return
    kw = {}
    if w:
        kw["width"] = Inches(w)
    if h:
        kw["height"] = Inches(h)
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), **kw)
    if caption:
        text(slide, x, y + (h or 0) + 0.02, w or 4, 0.28, caption, size=10, color=SOFT)


def fit(slide, filename, x, y, max_w, max_h):
    """按最大外框等比缩放放置截图；缺失时画一个醒目的占位框。"""
    path = IMG / filename
    if not path.exists():
        box = card(slide, x, y, max_w, max_h, fill=RGBColor(0xFF, 0xF4, 0xF4))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = f"［待补截图］\n{filename}"
        r.font.size = Pt(13)
        r.font.bold = True
        r.font.color.rgb = RED
        r.font.name = FONT
        return 0.0, 0.0
    with PILImage.open(path) as im:
        iw, ih = im.size
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    slide.shapes.add_picture(str(path), Inches(x), Inches(y),
                             width=Inches(w), height=Inches(h))
    return w, h


def bullet_line(slide, x, y, w, head, body, head_color=CYAN, hsize=16, bsize=13):
    text(slide, x, y, w, 0.36, head, size=hsize, bold=True, color=head_color)
    text(slide, x, y + 0.40, w, 0.9, body, size=bsize, color=SOFT, spacing=1.3)


prs = new_deck()
L_TITLE = prs.slide_layouts[0]   # 标题幻灯片
L_SECTION = prs.slide_layouts[3]  # 节标题

# ---------------- 1 封面 ----------------
s = prs.slides.add_slide(L_TITLE)
text(s, 0.9, 1.75, W - 1.8, 0.8, "数诊编排 DataDx", size=42, bold=True,
     align=PP_ALIGN.CENTER)
text(s, 0.9, 2.62, W - 1.8, 0.55, "面向经营数据诊断的多智能体编排调度平台",
     size=20, color=SOFT, align=PP_ALIGN.CENTER)
lines(s, 0.9, 3.75, W - 1.8, 2.0,
      ["团队名称：hai-feng666",
       "演讲人：hai-feng666",
       "指导教师：无（个人参赛）",
       "学    校：（按报名信息填写）"],
      size=17, spacing=1.75, anchor=MSO_ANCHOR.TOP)
for p in s.shapes[-1].text_frame.paragraphs:
    p.alignment = PP_ALIGN.CENTER

# ---------------- 2 目录 ----------------
s = prs.slides.add_slide(L_SECTION)
text(s, 0.75, 2.15, 2.2, 1.4, "目\n录", size=52, bold=True)
lines(s, 3.3, 1.9, 8.8, 4.6,
      ["01   问题：一份脏数据，三天没人敢下结论",
       "02   方案：六个 Agent，一条可执行 DAG",
       "03   内核：把任务派给谁，由算法决定",
       "04   质量：让 AI 写的每个数字都可证伪",
       "05   证据：38 秒、5 分钱、逐轮可回放"],
      size=19, spacing=2.05)

# ---------------- 3 场景 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "一个具体的场景", "中小贸易公司的月度经营分析")
card(s, 0.45, 1.95, 5.95, 4.55)
text(s, 0.75, 2.15, 5.4, 0.4, "他手上的东西", size=15, bold=True, color=DARK)
lines(s, 0.75, 2.62, 5.4, 2.0,
      ["240 行订单流水，7 个字段", "区域 / 品类 / 渠道 / 数量 / 单价 / 折扣",
       "其中 5 行是脏的：数量为空、单价为负"],
      size=13, color=GRAY, spacing=1.5)
text(s, 0.75, 4.35, 5.4, 0.4, "他想知道的三件事", size=15, bold=True, color=DARK)
lines(s, 0.75, 4.82, 5.4, 1.5,
      ["哪个区域卖得好？", "哪个品类在掉？", "钱是不是被折扣吃掉了？"],
      size=13, color=GRAY, spacing=1.35)

card(s, 6.75, 1.95, 6.13, 4.55)
text(s, 7.05, 2.15, 5.6, 0.4, "他面前的三条路", size=15, bold=True, color=DARK)
rows = [["自己看 Excel", "2 天", "不保证算得对"],
        ["请咨询公司", "3–5 万", "等两周"],
        ["丢给大模型", "10 分钟", "不敢信——AI 会编数字"]]
table_card(s, 6.9, 2.62, 5.83, 1.85, ["做法", "代价", "问题"], rows,
           [2.1, 1.2, 3.0], body_size=11.5)
text(s, 7.05, 4.75, 5.6, 1.5,
     "第三条路的问题不是“AI 写不出来”，\n而是“写出来之后没人能确认它对不对”。",
     size=15, color=CYAN, bold=True, spacing=1.4)

# ---------------- 4 三个痛点 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "三个真实痛点", "这不是模型能力问题，是工程问题")
items = [("① 数据是脏的", "240 行里 5 行有质量问题。不清洗直接算，总营收被负值拉低、客单价被空值抬高。"),
         ("② AI 会编数字", "把 5,455,910.0 写成“约 546 万”、自己心算增长率、凭空引用“行业平均”。"),
         ("③ 错了没人知道", "报告越专业越容易被信。某个区域错了 10%，管理层也不会去核对。")]
for i, (h1, b1) in enumerate(items):
    y = 1.75 + i * 1.72
    card(s, 0.45, y, 12.43, 1.45)
    text(s, 0.78, y + 0.20, 3.0, 0.4, h1, size=17, bold=True, color=DARK)
    text(s, 3.95, y + 0.22, 8.6, 1.0, b1, size=13.5, color=GRAY, spacing=1.3)
text(s, 0.45, 6.72, 12.43, 0.4,
     "结论：要解决的不是“写得更像人”，而是“让每个数字都能被证伪”。",
     size=14, bold=True, color=CYAN)

# ---------------- 5 架构 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "平台架构：五层解耦", "每一层都可以单独替换，互不影响")
layers = [("观测层", "SQLite trace + 零依赖 Web 控制台", "运行可见、可回放"),
          ("质量层", "四层验证（规则 / 复算 / 交叉 / 终审）+ 置信度门控", "结果可证伪"),
          ("决策层", "能力画像 + UCB 探索 + 成本/延迟/负载打分", "派活可解释"),
          ("执行层", "自研 DAG 引擎：分层并行、条件分支、节点级循环", "流程可编排"),
          ("数据配置层", "flows/*.json + agents.json + data/", "场景可替换")]
for i, (name, what, why) in enumerate(layers):
    y = 1.62 + i * 1.04
    card(s, 0.45, y, 2.35, 0.86, fill=CYAN)
    text(s, 0.45, y + 0.24, 2.35, 0.4, name, size=15, bold=True,
         color=DARK, align=PP_ALIGN.CENTER)
    card(s, 2.92, y, 6.55, 0.86)
    text(s, 3.15, y + 0.25, 6.1, 0.4, what, size=13, color=DARK)
    card(s, 9.6, y, 3.28, 0.86)
    text(s, 9.6, y + 0.25, 3.28, 0.4, why, size=13, color=GREEN, bold=True,
         align=PP_ALIGN.CENTER)

# ---------------- 6 七个 Agent ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "七个 Agent，八个节点", "同一份数据由两位分析师独立分析，再交仲裁员合并")
rows = [["探查", "profiler-a", "结构、缺失、异常定位", "csv_profile"],
        ["清洗", "cleaner-a", "清洗规则与影响行数", "规则库"],
        ["分析 A", "analyst-a", "规模与排名：区域营收/订单/单均排序", "sql_query"],
        ["分析 B", "analyst-b", "异常与交叉：背离均值者、结构异常", "sql_query"],
        ["仲裁", "arbiter-a", "比对 A/B 结论，消解分歧，输出唯一结论", "—"],
        ["深挖", "analyst-a / b", "区域 × 品类交叉", "sql_query"],
        ["撰写", "writer-a", "管理层语言，数字原样搬运", "—"],
        ["审校", "reviewer-a", "调模型逐条核出处，通过/不通过", "—"]]
table_card(s, 0.45, 1.55, 12.43, 4.62,
           ["节点", "Agent", "职责", "工具"], rows, [1.0, 2.0, 4.9, 1.4], body_size=10.5)
text(s, 0.45, 6.36, 12.43, 0.55,
     "A 与 B 在同一层并行执行、互不参考 —— 这是“多 Agent 协作”而非流水线拼接的关键。",
     size=13.5, color=CYAN)

# ---------------- 7 DAG 截图 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "一条可执行的 DAG", "8 节点 / 7 层依赖 / 双分析师并行 / 仲裁汇聚 / 条件分支")
card(s, 0.45, 1.55, 8.05, 4.45)
fit(s, "02-DAG-8节点.png", 0.60, 1.68, 7.75, 4.2)
card(s, 8.68, 1.55, 4.2, 4.45)
text(s, 8.92, 1.72, 3.75, 0.35, "这一屏说明了什么", size=14, bold=True, color=DARK)
lines(s, 8.92, 2.18, 3.72, 3.6,
      ["第 2 层两个框 = 双分析师并行",
       "第 3 层 arbitrate 汇聚两路结论",
       "框内 Agent 名各不相同 → 真多 Agent",
       "顶部指标卡：通过 / 8 次 / 58,210 tokens / ¥0.1967",
       "左侧历史 = 每次运行都可回放"],
      size=11.5, color=GRAY, spacing=1.5)
text(s, 0.45, 6.20, 12.43, 0.7,
     "同层线程池并发；deep_dive 带 when 条件（outlier_count > 0）；每节点记录轮次，返修留痕。",
     size=12.5, color=SOFT, spacing=1.4)

# ---------------- 8 调度 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "把任务派给谁：由算法决定", "赛题要求“非硬编码流程”，这是我们的回答")
card(s, 0.45, 1.62, 12.43, 1.05, fill=RGBColor(0x0E, 0x1E, 0x40))
text(s, 0.75, 1.82, 11.8, 0.7,
     "score = w₁·能力匹配 + w₂·UCB1(历史成功率) − w₃·成本 − w₄·延迟 − w₅·负载",
     size=17, bold=True, color=CYAN, align=PP_ALIGN.CENTER)
rows = [["w₁ 能力匹配", "1.0", "角色与 Agent 能力标签一致记 1.0，否则 0.45"],
        ["w₂ 历史成功率", "1.2", "权重最高：干得好就多派活（UCB1 带探索项）"],
        ["w₃ / w₄ 成本·延迟", "0.35", "抑制高成本、高延迟模型被滥用"],
        ["w₅ 当前负载", "0.8", "同一 Agent 并发过高时自动分流"]]
table_card(s, 0.45, 2.85, 7.1, 3.2, ["权重项", "取值", "含义"], rows, [1.8, 0.8, 4.5])
card(s, 7.8, 2.85, 5.08, 3.2)
text(s, 8.05, 3.02, 4.6, 0.35, "真实决策日志", size=13, bold=True, color=DARK)
text(s, 8.05, 3.42, 4.6, 2.4,
     "能力匹配 1.00 + UCB 1.219\n（历史成功率 100%，样本 8）\n"
     "− 成本项 − 延迟项 − 负载项\n\n领先 analyst-a 0.028 分",
     size=12, color=GRAY, spacing=1.5)
text(s, 0.45, 6.25, 12.43, 0.6,
     "“领先 0.028 分”是关键：存在两个候选，算法算完选了其中一个 —— 而不是按顺序取第一个。",
     size=13.5, color=CYAN, bold=True)

# ---------------- 9 Self-Loop ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "自我循环：发现错了，自己改", "执行 → 验证 → 修正，最多三轮，无人介入")
card(s, 0.45, 1.55, 8.05, 4.45)
fit(s, "03-DAG返修-8节点.png", 0.60, 1.68, 7.75, 4.2)
card(s, 8.68, 1.55, 4.2, 4.45)
text(s, 8.92, 1.72, 3.75, 0.35, "黄色节点发生了什么", size=14, bold=True, color=DARK)
rows = [["第 1 轮", "验证 ✗", "缺出处 → 打回"],
        ["第 2 轮", "验证 ✓", "按意见重写 → 通过"]]
table_card(s, 8.80, 2.12, 3.96, 1.30, ["轮次", "结论", "动作"], rows, [1.0, 1.4, 1.9],
           body_size=10.5)
lines(s, 8.92, 3.60, 3.72, 2.2,
      ["返修指令由验证证据自动生成，不是简单重试",
       "终止条件：3 轮 / 预算 / 低置信度转人工",
       "图为故障演练：注入一次输出截断，让容错链路可复现"],
      size=11, color=GRAY, spacing=1.45)

# ---------------- 10 四层验证 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "四层验证：让结果可证伪", "不是“感觉它对”，而是“能证明它对”")
rows = [["L1", "rule", "长度、分节、必备小节、禁止占位符", "确定性"],
        ["L2", "recompute", "每个 ≥1000 的数字能否复算（容差 0.5%）", "确定性 ★"],
        ["L3", "cross", "两路独立结论（A / B）是否互相印证", "确定性"],
        ["L4", "llm_judge", "调模型逐条核出处，输出通过 / 不通过", "模型判定"]]
table_card(s, 0.45, 1.62, 12.43, 2.55,
           ["层", "验证器", "判什么", "机器可判"],
           rows, [0.5, 1.5, 6.0, 1.4], body_size=11.5)
card(s, 0.45, 4.35, 12.43, 2.35)
text(s, 0.75, 4.52, 11.9, 0.35, "L2 复算：四类判定规则", size=14, bold=True, color=DARK)
lines(s, 0.75, 4.95, 5.6, 1.6,
      ["必需口径：总营收/客单价/订单数必须出现且一致",
       "幻觉数字：≥1000 且既非事实值、也非派生值"],
      size=12.5, color=GRAY, spacing=1.35)
lines(s, 6.9, 4.95, 5.6, 1.6,
      ["派生空间：事实值两两差值/合计视为可复算",
       "情景推演：假设/目标/预计句中的数字单列，不判幻觉"],
      size=12.5, color=GRAY, spacing=1.35)

# ---------------- 11 验证记录截图 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "验证证据长什么样", "同一节点两轮判定，证据可点击回看")
card(s, 0.45, 1.52, 11.9, 4.95)
fit(s, "04-验证记录-8节点.png", 0.95, 1.64, 10.9, 4.6)
text(s, 0.45, 6.58, 12.43, 0.45,
     "四层验证共 13 条判定记录全部通过（rule 7 / recompute 4 / cross 1 / judge 1）。",
     size=13, color=CYAN)

# ---------------- 12 运行实录 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "运行实录：零返修的一跑", "8 节点 / 8 次调用 / 58,210 tokens / ¥0.1967 / 90.8 秒")
card(s, 0.45, 1.55, 4.0, 5.0)
fit(s, "01-终端-8节点.png", 0.62, 1.68, 3.66, 4.74)
card(s, 4.75, 1.55, 8.13, 2.15)
text(s, 5.0, 1.72, 7.6, 1.9,
     "8 次模型调用\n58,210 tokens\n¥0.1967\n90.8 秒\n13 项验证全部通过，零返修",
     size=15, color=DARK, spacing=1.5)
card(s, 4.75, 3.9, 8.13, 2.65)
text(s, 5.0, 4.05, 7.6, 0.35, "调优轨迹（同一套代码）", size=13, bold=True, color=DARK)
text(s, 5.0, 4.45, 7.6, 1.95,
     "14 次调用 / ¥0.192  →  10 次 / ¥0.229  →  8 次 / ¥0.197（零返修）\n\n"
     "关键修复：事实表与工具证据同时注入、审校判否回溯重写、max_tokens 放开",
     size=12.5, color=GRAY, spacing=1.4)

# ---------------- 13 工程化 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "工程化：让别人十分钟跑起来", "这是“可复现性 25 分”的全部底气")
cards = [("零第三方依赖", "git clone 后直接运行，无 pip install", "复现成本 ≈ 0"),
         ("mock 离线后端", "没有 API Key 也能完整演示全流程", "评委不会卡在环境"),
         ("11 项单元测试", "结构 / 数据 / 验证器 / 端到端", "改坏了立刻知道"),
         ("全链路 trace", "runs / nodes / verdicts / metrics", "任何一次都可回放")]
for i, (h1, b1, f1) in enumerate(cards):
    x = 0.45 + (i % 2) * 6.29
    y = 1.68 + (i // 2) * 2.28
    card(s, x, y, 6.14, 2.05)
    text(s, x + 0.28, y + 0.20, 5.6, 0.42, h1, size=17, bold=True, color=DARK)
    text(s, x + 0.28, y + 0.72, 5.6, 0.75, b1, size=12.5, color=GRAY, spacing=1.35)
    card(s, x + 0.28, y + 1.55, 2.6, 0.38, fill=RGBColor(0xE6, 0xF6, 0xEE))
    text(s, x + 0.28, y + 1.61, 2.6, 0.3, f1, size=10.5, color=GREEN,
         bold=True, align=PP_ALIGN.CENTER)

# ---------------- 14 局限与价值 ----------------
s = prs.slides.add_slide(L_SECTION)
title(s, "诚实的边界与真实的价值", "知道自己的极限，比假装什么都能做更值钱")
card(s, 0.45, 1.62, 6.14, 4.85)
text(s, 0.75, 1.80, 5.6, 0.38, "已知局限（主动披露）", size=15, bold=True, color=DARK)
lines(s, 0.75, 2.30, 5.55, 4.0,
      ["复算只覆盖数值型结论，纯文本判断仍依赖终审",
       "python_eval 是受限执行，非容器级沙箱",
       "mock 是确定性模拟，不能替代真实评测",
       "当前仅内置一个业务场景",
       "单机 SQLite，不支持多用户并发"],
      size=12.5, color=GRAY, spacing=1.55)
card(s, 6.75, 1.62, 6.13, 4.85)
text(s, 7.05, 1.80, 5.6, 0.38, "可迁移的场景", size=15, bold=True, color=DARK)
lines(s, 7.05, 2.30, 5.55, 1.9,
      ["凡是“有硬验证信号”的场景都能复用：",
       "合规审查 · 投标文件检查 · 财务对账",
       "平台本体与场景解耦：只换 flows 与 agents"],
      size=12.5, color=GRAY, spacing=1.55)
text(s, 7.05, 4.45, 5.6, 0.38, "商业可行性", size=15, bold=True, color=DARK)
lines(s, 7.05, 4.90, 5.55, 1.4,
      ["单次运行成本约 ¥0.05", "替代“人工做表 + 口头汇报”的流程", "可作为企业内部数据中台组件"],
      size=12.5, color=GRAY, spacing=1.45)

# ---------------- 15 谢谢 ----------------
s = prs.slides.add_slide(L_TITLE)
text(s, 0.9, 2.55, W - 1.8, 0.9, "谢谢观看", size=40, bold=True, align=PP_ALIGN.CENTER)
text(s, 0.9, 3.45, W - 1.8, 0.5, "Thanks", size=22, color=SOFT, align=PP_ALIGN.CENTER)
text(s, 0.9, 4.25, W - 1.8, 0.5, "数诊编排 DataDx · 赛题一 Agent 编排创新应用",
     size=13, color=SOFT, align=PP_ALIGN.CENTER)

prs.save(str(OUT))
print(f"已生成：{OUT}")
print(f"页数：{len(prs.slides)}")
