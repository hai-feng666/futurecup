# -*- coding: utf-8 -*-
"""生成《方案书》Word 初稿（赛题一）。运行后输出 docs/方案书.docx。"""
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

OUT = Path(__file__).resolve().parent.parent / "docs" / "方案书.docx"
CN = "宋体"
CN_H = "黑体"


def set_cn(run, font=CN, size=None, bold=None):
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold


def body(doc, text, size=10.5, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(size * 2)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.5
    r = p.add_run(text)
    set_cn(r, CN, size)
    return p


def bullet(doc, text, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.4
    r = p.add_run(text)
    set_cn(r, CN, size)
    return p


def heading(doc, text, level=1):
    h = doc.add_heading("", level=level)
    r = h.add_run(text)
    set_cn(r, CN_H, 16 if level == 1 else 13, True)
    r.font.color.rgb = RGBColor(0x1F, 0x2A, 0x37)
    h.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    h.paragraph_format.space_after = Pt(6)
    return h


def caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    set_cn(r, CN, 9)
    r.font.color.rgb = RGBColor(0x55, 0x5F, 0x6D)
    return p


IMG_DIR = Path(__file__).resolve().parent.parent / "docs" / "截图"


def pic(doc, filename, width_cm, cap):
    """插入一张截图并配图注；文件缺失时留出醒目的占位块，便于后续替换。"""
    path = IMG_DIR / filename
    if path.exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        p.add_run().add_picture(str(path), width=Cm(width_cm))
        caption(doc, cap)
        return
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"［待补截图］{cap}\n请替换为：docs/截图/{filename}")
    set_cn(r, CN, 10)
    r.font.color.rgb = RGBColor(0xB9, 0x1C, 0x1C)
    caption(doc, cap)


def blank(doc, n=1):
    for _ in range(n):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run("")
        set_cn(r, CN, 11)


def table(doc, headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ""
        r = cell.paragraphs[0].add_run(h)
        set_cn(r, CN_H, 9.5, True)
    # 表头跨页重复
    tr = t.rows[0]._tr
    trPr = tr.get_or_add_trPr()
    tblHeader = trPr.makeelement(qn("w:tblHeader"), {})
    trPr.append(tblHeader)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(v))
            set_cn(r, CN, 9)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = w
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


doc = Document()
style = doc.styles["Normal"]
style.font.name = CN
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn("w:eastAsia"), CN)

# ---------------- 封面 ----------------
blank(doc, 5)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("第五届“未来杯”创新大赛")
set_cn(r, CN_H, 15, True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("赛题一：Agent 编排创新应用")
set_cn(r, CN_H, 13)

blank(doc, 2)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("数诊编排 DataDx")
set_cn(r, CN_H, 26, True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("面向经营数据诊断的多智能体编排调度平台")
set_cn(r, CN_H, 14)

blank(doc, 3)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("技术方案书")
set_cn(r, CN, 12)

blank(doc, 4)

for line in ["参赛队伍：hai-feng666", "参赛人数：1 人（个人参赛）",
             "参赛赛题：赛题一 Agent 编排创新应用", "提交日期：2026 年 11 月"]:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(line)
    set_cn(r, CN, 11)

doc.add_page_break()

# ---------------- 摘要 ----------------
heading(doc, "摘要", 1)
body(doc, "本方案面向中小企业“有数据、没分析师”的现实困境，设计并实现了一套"
          "多智能体（Multi-Agent）编排调度平台：输入一份脏的经营流水表与一句自然语言问题，"
          "平台调度 7 个具备不同角色、工具与记忆能力的 Agent（编排为 8 个节点）协作产出管理层诊断报告，"
          "并对报告中每一个数值执行可复算的溯源校验——对不上的数字会被自动打回重写，最多三轮。")
body(doc, "平台的核心主张是：大模型 Agent 落地生产环境的瓶颈不在“写得好不好”，"
          "而在“错得看不出来”。因此本方案把工程重心放在三处：一是自研 DAG 编排引擎，"
          "支持顺序、并行、条件分支与节点级循环；二是基于能力画像与 UCB 探索的调度器，"
          "使“把任务派给谁”成为可解释的算法决策而非硬编码；三是四层结果验证与置信度门控，"
          "把“AI 生成”转化为“AI 生成且可证伪”。")
body(doc, "平台实现为 12 个 Python 模块、约 2,100 行代码，核心零第三方依赖，"
          "在真实大模型上完成 10 余次端到端运行；基准运行（run-1794876724178-da7e）为 "
          "8 个节点、8 次模型调用、5.8 万 tokens、成本 0.197 元、耗时 90.8 秒，"
          "13 条验证记录全部通过、零返修。")
p = doc.add_paragraph()
r = p.add_run("关键词：多智能体；编排调度；DAG；结果验证；自我循环；可复现")
set_cn(r, CN, 10.5, True)
doc.add_page_break()

# ---------------- 一 ----------------
heading(doc, "一、选题背景与场景需求分析", 1)

heading(doc, "1.1 一个具体的场景", 2)
body(doc, "一家做工业设备的中小贸易公司，老板每月要看一次经营数据。他手上有从 ERP 导出的"
          "订单流水表：240 行，7 个字段，记录订单号、日期、区域、品类、渠道、数量、单价与折扣。"
          "他想知道三件事：哪个区域卖得好、哪个品类在掉、钱是不是被折扣吃掉了。")
body(doc, "他面前有三条路。第一条是自己看 Excel，逐月对比、做透视表，大约要花两天，"
          "而且不保证算得对；第二条是请咨询公司，报价三到五万，等两周；第三条是用 AI，"
          "把表格丢给大模型，十分钟就能出一份看起来很专业的报告——但他不敢信，因为 AI 会编数字。")
body(doc, "第三条路的问题不在于“AI 写不出来”，而在于“写出来之后没人能确认它对不对”。"
          "这正是本方案要解决的问题。")

heading(doc, "1.2 三个真实痛点", 2)
body(doc, "痛点一：数据是脏的。", 10.5)
body(doc, "演示数据集的 240 行记录中，5 行存在数量为空、单价为负等质量问题。若不先清洗，"
          "总营收会被负值拉低、客单价会被空值抬高。而现实中，直接把这些脏数据丢给大模型，"
          "它会照单全收并给出一个“看起来合理”的答案。")
body(doc, "痛点二：AI 会编数字。", 10.5)
body(doc, "若不加约束，大模型写报告时会做三类事情：把 5,455,910.0 写成“约 546 万”、"
          "自行心算增长率、以及凭空引用“行业平均水平”。这些数字在行文里毫无破绽，"
          "读者无法分辨哪些来自数据、哪些是模型编的。")
body(doc, "痛点三：错了没人知道。", 10.5)
body(doc, "报告越专业，越容易被信。一份排版整齐、结论清晰的报告，即便其中某个区域的营收"
          "错了 10%，管理层也不会去核对。错误因此从“分析问题”升级为“决策风险”。")

heading(doc, "1.3 目标定位", 2)
body(doc, "本平台的目标不是“让 AI 写得更像人”，而是“让 AI 写的每个数字都能被证伪”。"
          "具体而言，平台承诺三件事：报告中的每个绝对值都能追溯到本次运行的事实表或工具输出；"
          "无法溯源的数字会被自动拦截并触发重写；每一次运行的全过程（输入、输出、调度决策、"
          "验证证据、耗时与成本）都被完整记录，可离线回放。")

# ---------------- 二 ----------------
heading(doc, "二、平台总体架构与技术选型", 1)

heading(doc, "2.1 架构分层", 2)
body(doc, "平台自下而上分为五层：")
bullet(doc, "数据与配置层：flows/*.json 定义工作流，config/agents.json 定义 Agent 团队，data/ 存放业务数据。")
bullet(doc, "执行层：engine.py 的 DAG 执行器，负责依赖解析、并行调度、条件判断与节点级循环。")
bullet(doc, "决策层：scheduler.py 的能力画像调度器，负责“把这一步派给谁”。")
bullet(doc, "质量层：verify.py 的四层验证器与置信度门控，负责“这一步做对了吗”。")
bullet(doc, "观测层：store.py 的 SQLite trace 与 console.py 的零依赖 Web 控制台，负责“让过程可见可回放”。")

heading(doc, "2.2 与赛题六大能力的对应关系", 2)
table(doc,
      ["赛题要求", "本平台实现", "对应模块"],
      [["Agent 团队定义与管理", "6 个角色，含提示词、工具集、模型档位、成本参数、能力标签",
        "config/agents.json"],
       ["工作流编排", "DAG + 并行分层 + when 条件分支 + 节点级循环 + 子流程", "engine.py"],
       ["智能调度引擎", "能力画像 + UCB1 探索 + 成本/延迟/负载扣分，决策可解释", "scheduler.py"],
       ["工具与外部系统集成", "CSV 画像、真实 SQL 执行、受限 Python 求值", "tools.py"],
       ["执行监控与结果验证", "四层验证 + 置信度门控 + 全链路 trace", "verify.py / store.py"],
       ["反馈与自我优化", "验证证据回灌为返修指令，最多三轮；跨运行沉淀能力画像", "engine.py"]],
      widths=[Pt(90), Pt(190), Pt(90)])
caption(doc, "表 2-1 赛题六大能力与实现对应表")

heading(doc, "2.3 为什么自研引擎而不用现成框架", 2)
body(doc, "赛题技术要求明确指出：“必须体现 Agent 编排与调度的智能化，而非简单的硬编码流程”，"
          "并“禁止直接套用现成框架的默认示例”。而主流框架（LangChain、Dify、CrewAI 等）的"
          "默认用法，恰恰是“按顺序执行一串 Task”——角色不同、流程写死、调度靠顺序。"
          "这在本赛题的评分语境下属于减分项：调度算法无从谈起，自我循环也多为框架内建的黑盒。")
body(doc, "因此本方案选择自研。自研的代价是约 340 行 DAG 引擎代码，收益是：调度策略、"
          "验证规则、循环终止条件全部可读、可改、可解释。答辩时被问到“你的调度策略是什么”，"
          "可以当场展示打分公式与决策日志，而不是回答“框架按顺序执行”。")

heading(doc, "2.4 技术选型：刻意保持零第三方依赖", 2)
body(doc, "平台核心不依赖任何第三方库，仅使用 Python 标准库：")
table(doc,
      ["能力", "常规选型", "本平台选型", "选择理由"],
      [["HTTP 调用", "requests / httpx", "urllib.request", "少一个依赖，评委复现少一步失败"],
       ["数据存储", "PostgreSQL / Redis", "sqlite3", "单机可跑，无需部署"],
       ["数据计算", "pandas", "csv + statistics", "数据集规模小，够用即可"],
       ["Web 服务", "Flask / Streamlit", "http.server", "一条命令启动，零安装"],
       ["配置解析", "PyYAML", "json（标准库）", "JSON 无需额外依赖"],
       ["向量检索", "Chroma / FAISS", "本期未启用", "演示场景用 SQL 取数更硬、更可验证"]],
      widths=[Pt(60), Pt(85), Pt(85), Pt(150)])
caption(doc, "表 2-2 技术选型对照")
body(doc, "这一选择并非排斥成熟工具，而是服务于一个非常具体的评分场景：评审专家需要在"
          "陌生机器上复现演示。零依赖意味着 git clone 之后直接 python -m harness.console 即可运行，"
          "把“跑不起来”这一最常见的失分点提前消除。")
body(doc, "在数据侧，平台支持通过 `python -m harness.cli run --dataset <文件> --question <问题>` "
          "指定任意同结构 CSV 与业务问题，无需修改代码或配置文件。项目内置两份数字完全不同的"
          "数据集（240 行与 120 行），运行结果随数据变化而变化，用以验证平台与具体数据解耦、"
          "并非为某一份数据硬编码。")

# ---------------- 三 ----------------
heading(doc, "三、Agent 团队定义与工作流编排", 1)

heading(doc, "3.1 七个角色、八个节点", 2)
body(doc, "角色划分遵循一个原则：每个角色的职责必须能被一句可验证的输出描述，"
          "否则就不该独立成节点。同一条分析任务被拆成两位分析师独立完成，"
          "再由仲裁员合并——这是本方案在多 Agent 协作上的核心设计。")
table(doc,
      ["节点", "Agent", "职责", "可用工具", "不能合并的理由"],
      [["profile", "profiler-a", "数据画像：行数、字段、缺失、异常定位", "csv_profile",
        "只描述数据不做业务判断，防止“边看边猜”"],
       ["clean", "cleaner-a", "清洗规则清单与影响行数", "规则库",
        "清洗规则必须显式可审计，不能藏在分析里"],
       ["analyze_a", "analyst-a", "规模与排名视角：区域营收、订单、单均排序", "sql_query",
        "与 B 视角互补，且两者独立产出构成交叉验证来源"],
       ["analyze_b", "analyst-b", "异常与交叉视角：背离均值者、结构异常、成因假设", "sql_query",
        "与 A 并行执行，互不参考对方结论"],
       ["arbitrate", "arbiter-a", "比对 A/B 结论，消解分歧并输出唯一合并结论", "—",
        "两份结论必须有裁判，否则下游拿到的是矛盾信息"],
       ["deep_dive", "analyst-a / analyst-b", "区域 × 品类交叉深挖", "sql_query",
        "仅在事实表显示存在离群时触发，演示条件分支"],
       ["report", "writer-a", "组织管理层语言，数字原样搬运", "—",
        "最易出错环节，正好作为返修演示点"],
       ["review", "reviewer-a", "调模型逐条核对出处，给出通过/不通过", "—",
        "终局闸门，对应人工介入前的最后一道"]],
      widths=[Pt(52), Pt(76), Pt(118), Pt(56), Pt(116)])
caption(doc, "表 3-1 八个节点与七个 Agent 的职责边界")

heading(doc, "3.2 工作流结构与控制流", 2)
body(doc, "工作流共 8 个节点、7 个依赖层级，是四种控制结构的组合：")
bullet(doc, "并行：analyze_a 与 analyze_b 位于同一层，由线程池并发执行——"
            "这是本工作流中真正的并行点，两者的结论互不参考。")
bullet(doc, "汇聚：arbitrate 节点同时依赖 A 与 B，必须等两者都完成才启动，"
            "并以其 `cross` 验证器比对两路结论。")
bullet(doc, "条件分支：deep_dive 节点带 when 表达式“outlier_count > 0”，"
            "事实表显示无离群订单时该分支自动跳过。")
bullet(doc, "循环迭代：每个节点内部都有最多三轮的“执行—验证—修正”循环，"
            "返修意见由验证证据自动生成并回灌到下一轮提示词。")
pic(doc, "02-DAG-8节点.png", 15.5,
    "图 3-1 八节点工作流 DAG（第 2 层为双分析师并行，仲裁节点汇聚两路结论）")

heading(doc, "3.3 配置驱动的编排", 2)
body(doc, "工作流不是写死在代码里的，而是由 JSON 描述。以下为 analyze_b 与 arbitrate 节点的定义：")
p = doc.add_paragraph()
r = p.add_run('{"id": "analyze_b", "role": "analyst", "depends_on": ["clean"],\n'
              ' "candidates": ["analyst-b"], "tools": ["sql_query"],\n'
              ' "verify": ["rule", "recompute"], "required_facts": []}\n\n'
              '{"id": "arbitrate", "role": "arbiter",\n'
              ' "depends_on": ["analyze_a", "analyze_b"],\n'
              ' "verify": ["rule", "cross", "recompute"],\n'
              ' "cross_with": ["analyze_a", "analyze_b"], "advisory": ["cross"]}')
set_cn(r, "Consolas", 8.5)
body(doc, "两个细节值得说明：`required_facts` 让“只做异常分析”的节点不必复述全部口径，"
          "避免把职责差异误判为质量缺陷；`advisory` 让 cross 只呈现分歧、不阻塞仲裁——"
          "上游本身有问题时，仲裁员仍应正常产出结论，分歧作为证据保留。")

heading(doc, "3.4 事实表 F1–F11：数字的唯一出处", 2)
body(doc, "平台在运行开始时，由确定性代码（而非大模型）从原始数据计算出一张事实表，"
          "并为其编号 F1–F11：F1 记录数与清洗结果、F2 有效订单数、F3 总营收、F4 客单价、"
          "F5 最大单笔、F6 区域营收、F7 品类营收、F8 离群订单、F9 头部区域与品类、"
          "F10 区域订单数、F11 区域单均营收。")
body(doc, "事实表与工具输出会同时注入每个 Agent 的提示词，并在末尾附带三条引用规则："
          "任何绝对值必须标注编号；派生值必须写出计算式；不允许出现既无编号也无计算式的绝对值。"
          "这一约束使得“可溯源”从一句口号变成可执行的格式要求。")

# ---------------- 四 ----------------
heading(doc, "四、智能调度与自我循环机制", 1)

heading(doc, "4.1 调度打分公式", 2)
body(doc, "当同一角色存在多个候选 Agent 时，调度器按下式打分并取最大值：")
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("score = w₁·能力匹配 + w₂·UCB1(历史成功率) − w₃·归一化成本 "
              "− w₄·归一化延迟 − w₅·当前负载")
set_cn(r, CN, 10.5, True)
table(doc,
      ["权重", "取值", "含义"],
      [["w₁ 能力匹配", "1.0", "角色与 Agent 声明的能力标签是否一致，一致记 1.0，否则 0.45"],
       ["w₂ 历史成功率", "1.2", "权重最高，体现“干得好就多派活”"],
       ["w₃ 成本", "0.35", "抑制高成本模型被滥用"],
       ["w₄ 延迟", "0.35", "抑制高延迟模型被滥用"],
       ["w₅ 负载", "0.8", "同一 Agent 并发过高时自动分流"]],
      widths=[Pt(90), Pt(50), Pt(240)])
caption(doc, "表 4-1 调度权重配置")

heading(doc, "4.2 UCB1 探索项", 2)
body(doc, "若只按历史成功率排序，新注册的 Agent 会因样本为零而被永久冷落。为此引入 UCB1：")
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("UCB1 = 历史成功率 + c·√(ln(N+1) / n)，其中 c = 0.30")
set_cn(r, CN, 10.5, True)
body(doc, "样本数 n 越小，探索奖励越大，从而保证新 Agent 有机会被选中并获得画像数据。"
          "这是“探索—利用”权衡在调度层面的最小实现。")

heading(doc, "4.3 决策可解释性", 2)
body(doc, "每一次调度决策都会把全部候选的分数、能力匹配度、UCB 值、样本数、"
          "成本与延迟估计写入 trace，并在控制台展示。实际运行中的一条决策记录为：")
p = doc.add_paragraph()
r = p.add_run("能力匹配 1.00 + UCB 1.219（历史成功率 100%，样本 8）− 成本项 − 延迟项 − 负载项；"
              "领先 analyst-a 0.028 分")
set_cn(r, CN, 9.5)
caption(doc, "表 4-2 实际调度决策日志（控制台截图对应行）")
body(doc, "“领先 0.028 分”这一信息是关键：它说明该任务存在两个候选，调度器经过计算选择了"
          "其中一个，而不是按固定顺序取第一个。这是“智能调度”与“硬编码流程”的分界点。")

heading(doc, "4.4 双分析师与仲裁：把“多 Agent”做成真协作", 2)
body(doc, "多数“多 Agent”作品实质是一条流水线：A 做完交给 B，B 做完交给 C。"
          "本方案让两位分析师并行且互不参考地分析同一份数据，再交由仲裁员合并：")
bullet(doc, "分析师 A（analyst-a）从“规模与排名”切入：区域营收、订单数、单均营收的排序与量价结构。")
bullet(doc, "分析师 B（analyst-b）从“异常与交叉”切入：与整体均值背离的区域、品类结构异常、成因假设。")
bullet(doc, "仲裁员（arbiter-a）同时收到两份结论：一致处直接采纳，矛盾处指出分歧并判定哪一方有事实依据，"
            "输出唯一的合并结论。")
body(doc, "仲裁节点上的 `cross` 验证器负责确认“两路独立结论是否互相印证”。"
          "实测证据为：`compared=['analyze_a','analyze_b'] agree=True`。"
          "这一层不是再调一次模型凑数，而是拿两份独立产出做一致性比对，"
          "因此不产生额外模型调用成本。")

heading(doc, "4.5 自我循环（Self-Loop）", 2)
body(doc, "每个节点的执行是一个三段循环：执行 → 验证 → 修正。验证未通过时，"
          "系统不是简单重试，而是把失败的结构化证据回灌到下一轮提示词：")
p = doc.add_paragraph()
r = p.add_run("【返修意见 / 上一轮验证失败原因】\n"
              '{"verifier": "recompute", "passed": false,\n'
              ' "evidence": {"missing_required": ["总营收"],\n'
              '              "hallucinated_numbers": [6001638.0]}}\n'
              "请修正后输出完整内容；所有数字必须来自事实表。")
set_cn(r, "Consolas", 8.5)
body(doc, "这一机制的效果是可观测的：在同一次运行中，analyze 节点第 1 轮判否、"
          "第 2 轮判是，控制台上该节点显示为黄色并标注“已返修 1 次”。")
pic(doc, "05-终端返修-8节点.png", 14.0,
    "图 4-1 自我循环实录：某节点第 1 轮判否、第 2 轮通过（同一节点、同一 Agent）")

heading(doc, "4.6 终止条件与预算控制", 2)
body(doc, "无限循环是自循环机制最常见的工程事故。平台设置三重终止条件："
          "单节点最多 3 轮；全流程累计 tokens 超过预算即停止返修；"
          "当置信度低于 0.30 时不再继续重试，直接转人工介入并如实计入指标。"
          "第三点是刻意的诚实设计——低置信度意味着“模型自己也不确定”，"
          "此时继续重试只是在烧钱，不如让人来判断。")

heading(doc, "4.7 故障演练（Chaos Drill）", 2)
body(doc, "为验证容错链路确实有效，平台内置故障演练模式：在第一轮给分析类节点附加一条"
          "演练指令，要求其故意给出一个未标注出处的估算值。验证层会在第二轮捕获该问题并"
          "触发返修，从而在不依赖“模型恰好犯错”的前提下，稳定复现“验证—返修—通过”全过程。"
          "这一设计借鉴软件工程中的混沌工程思路：可复现的故障比随机故障更有验证价值。")

# ---------------- 五 ----------------
heading(doc, "五、结果验证与反馈优化", 1)

heading(doc, "5.1 四层验证体系", 2)
body(doc, "四层验证器全部接入实际工作流，最近一次运行中共产生 13 条判定记录（rule 7 条、"
          "recompute 4 条、cross 1 条、llm_judge 1 条），全部通过。")
table(doc,
      ["层级", "验证器", "判什么", "可否机器判定"],
      [["L1", "rule", "长度、分节数量、必备小节、禁止占位符", "确定性"],
       ["L2", "recompute", "报告中每个绝对值 ≥1000 的数字能否复算（容差 0.5%）", "确定性"],
       ["L3", "cross", "两路独立结论（analyze_a / analyze_b）是否互相印证", "确定性"],
       ["L4", "llm_judge", "调用大模型逐条核对出处，输出通过/不通过", "模型判定"]],
      widths=[Pt(35), Pt(75), Pt(220), Pt(80)])
caption(doc, "表 5-1 四层验证器")

heading(doc, "5.2 复算校验的判定规则", 2)
body(doc, "L2 是本方案的核心。它对报告文本做四类判定：")
bullet(doc, "必需口径：总营收、客单价、订单数三项必须出现且与事实表一致；缺失即判否。")
bullet(doc, "幻觉数字：绝对值 ≥1000 且既不等于任何事实值、也不属于派生值空间的数字。")
bullet(doc, "派生值空间：事实值两两的差值与合计视为可复算，避免把正常的比较分析误伤为幻觉。")
bullet(doc, "情景推演：出现在“假设/目标/预计/若”等语气句中的数字单独归类，不判幻觉但记录在案。")
body(doc, "此外，本次运行中所有工具输出出现过的数值构成“证据池”，报告引用它们同样视为合法。"
          "这一规则对应可审计的本质要求：报告里的数字，必须能追溯到本次运行的某处。")

heading(doc, "5.3 置信度门控与三档处置", 2)
body(doc, "多个验证器的结论按权重聚合成一个置信度（复算层权重 3.0，交叉层 2.0，"
          "规则层与终审层各 1.0），据此分三档处置：")
table(doc,
      ["条件", "处置", "说明"],
      [["全部通过且置信度 ≥ 0.75", "accept", "接受，进入下游节点"],
       ["存在未通过且置信度 ≥ 0.30", "repair", "生成返修指令，重跑本节点"],
       ["置信度 < 0.30", "escalate", "停止重试，标记人工介入"]],
      widths=[Pt(140), Pt(60), Pt(210)])
caption(doc, "表 5-2 置信度门控的三档处置")
body(doc, "此外，标记为 `advisory` 的验证器（当前仅 cross）只记录不参与门控："
          "仲裁环节的职责是“呈现并解释分歧”，若因为上游本身有问题就阻断仲裁员，"
          "等于让下游替上游背锅。这一取舍在实测中把一次运行的调用次数从 14 次降到 10 次。")
pic(doc, "04-验证记录-8节点.png", 15.5,
    "图 5-1 分层验证记录：同一节点两轮判定（未通过 → 通过）及其证据")

heading(doc, "5.4 验证器自身如何被验证", 2)
body(doc, "验证机制如果是错的，整套系统就只是看起来很严谨。因此平台把一次真实失败运行"
          "的报告原文固化为回归样本：同一份报告，在只给基础事实表的旧版本下被判“幻觉数字 5 个”，"
          "在引入工具证据池后判“通过、置信度 1.00”。该样本至今保留在测试集中，"
          "保证后续修改不会让验证能力倒退。")

heading(doc, "5.5 迭代记录", 2)
body(doc, "在 10 余次真实运行中，共定位并修复 9 个缺陷，均记录在 docs 进度日志中，此处择要：")
table(doc,
      ["#", "缺陷", "根因", "修复"],
      [["1", "报告被误判为缺少建议", "关键词匹配过死", "改为同义词组 + 分节数检查"],
       ["2", "审校节点永远判不通过", "判定只认英文 PASS/FAIL", "增加中文结论词与否定词子串处理"],
       ["3", "工具返回的真数字被判幻觉", "校验器只认基础事实表", "改为事实表 + 本次工具证据池"],
       ["4", "年份 2026 被当作业务数字", "正则词边界在中文语境失效", "改用前后向断言"],
       ["5", "审校员“看不见”上游数据", "提示词未注入工具证据", "新增 tool_evidence 上下文"],
       ["6", "深挖切片合计与总营收不闭合", "SQL 带 LIMIT 截断", "去除 LIMIT 并补充单均字段"],
       ["7", "宣称并行但并行度为 1", "6 节点排成一条直线", "拆出 analyze_a/b 并行 + arbitrate 汇聚"],
       ["8", "分析节点反复编造订单数", "有工具时未注入事实表", "事实表与工具证据同时注入（调用次数 14→8）"],
       ["9", "上游分歧阻塞仲裁", "cross 参与门控", "引入 advisory：只记录不阻塞"]],
      widths=[Pt(25), Pt(118), Pt(108), Pt(134)])
caption(doc, "表 5-3 缺陷定位与修复记录")

# ---------------- 六 ----------------
heading(doc, "六、核心代码模块与系统实现", 1)

heading(doc, "6.1 目录结构", 2)
p = doc.add_paragraph()
r = p.add_run("futurecup/\n"
              "├── config/agents.json        6 个 Agent 定义\n"
              "├── flows/data_insight.json   工作流定义（DAG）\n"
              "├── data/                     演示数据集与生成脚本\n"
              "├── harness/                  12 个核心模块（约 2100 行）\n"
              "│   ├── engine.py             DAG 执行引擎 + 自循环\n"
              "│   ├── scheduler.py          能力画像调度器\n"
              "│   ├── verify.py             四层验证 + 置信度门控\n"
              "│   ├── tools.py              工具层\n"
              "│   ├── models.py             模型抽象（mock / OpenAI 兼容）\n"
              "│   ├── store.py              SQLite trace\n"
              "│   └── console.py            零依赖 Web 控制台\n"
              "├── tests/                    单元测试与真实样本回归\n"
              "├── eval/                     三组基线评测\n"
              "└── docs/                     方案书与截图素材")
set_cn(r, "Consolas", 8.5)

heading(doc, "6.2 关键模块职责", 2)
table(doc,
      ["模块", "职责", "关键设计"],
      [["engine.py", "DAG 解析、分层并行、条件求值、节点级循环", "依赖深度分层，同层并发"],
       ["scheduler.py", "候选打分与选择", "决策明细全量落库"],
       ["verify.py", "四层验证与门控", "复算层为核心"],
       ["store.py", "runs/nodes/verdicts/metrics 四表", "过程可回放"],
       ["models.py", "模型抽象层", "换模型只改环境变量"],
       ["console.py", "DAG 可视化、决策表、验证记录", "零依赖 http.server"]],
      widths=[Pt(70), Pt(180), Pt(150)])
caption(doc, "表 6-1 核心模块职责")

heading(doc, "6.3 可观测性设计", 2)
body(doc, "所有运行写入同一 SQLite 库的四张表：runs 记录一次运行的配置快照与总量指标；"
          "nodes 记录每个节点每一轮的输入输出、tokens、耗时、成本与调度决策；"
          "verdicts 记录每次验证的结论、置信度与结构化证据；metrics 记录自定义量化指标。"
          "由此支持两个能力：断点回放与横向对比。")

heading(doc, "6.4 运行实录", 2)
body(doc, "2026-11-17 08:52 的一次真实运行（DeepSeek deepseek-chat，run_id 尾号 da7e）："
          "8 个节点、8 次模型调用、58,210 tokens、成本 0.197 元、总耗时 90.8 秒，"
          "8 个节点全部第一轮通过、零返修，13 条验证记录全部 passed=True。各节点耗时（毫秒）："
          "profile 7543、clean 8687、analyze_a 11226、analyze_b 16246、arbitrate 16573、"
          "deep_dive 17383、report 13307、review 8576。")
pic(doc, "01-终端-8节点.png", 8.6,
    "图 6-1 终端运行实录：8 个节点全部一轮通过，13 条验证均为 passed=True")
pic(doc, "03-DAG返修-8节点.png", 15.5,
    "图 6-2 故障演练下的返修实录：report 节点第 1 轮被判否（输出截断），第 2 轮通过")
body(doc, "另一次故障演练运行（run_id 尾号 fe9d）为：9 次调用、59,496 tokens、0.185 元、83.3 秒，"
          "其中 report 节点第 1 轮因输出被截断而触发 rule 的完整性检查，"
          "系统自动生成返修指令并重写，第 2 轮通过——这正是图 6-2 中黄色节点的来源。")

# ---------------- 七 ----------------
heading(doc, "七、测试、性能与量化评估", 1)

heading(doc, "7.1 单元测试", 2)
body(doc, "测试覆盖四类断言：工作流结构（依赖分层、并行度、条件表达式、终局节点）、"
          "数据一致性（清洗剔除、事实表可重复）、验证器行为（复算通过/拦截、门控拒绝）、"
          "端到端（完整运行成功、强制故障触发返修、四层验证全部启用、trace 留存 prompt）。"
          "当前 12 项测试全部通过，另有 1 项依赖真实模型报告样本的回归用例，在样本缺失时自动跳过。")
p = doc.add_paragraph()
r = p.add_run("$ python -m unittest discover -s tests\nRan 12 tests in 0.78s\nOK (skipped=1)")
set_cn(r, "Consolas", 9)

heading(doc, "7.2 基线对比设计", 2)
body(doc, "评测脚本在同一批任务（eval/tasks.jsonl，12 条业务问题）上运行三种配置，"
          "并使用同一判定标准（对最终交付物执行 L2 复算校验）：")
bullet(doc, "A 单 Agent 直连：具备数据访问能力，但一次性输出，无验证。")
bullet(doc, "B 固定串行：多 Agent 流水线，但无验证、无返修。")
bullet(doc, "C 本平台：能力画像调度 + 四层验证 + 自循环。")

heading(doc, "7.3 实测性能", 2)
table(doc,
      ["场景", "模型调用次数", "tokens", "成本（元）", "耗时（秒）", "验证通过率"],
      [["基准全绿运行", "8", "58,210", "0.1967", "90.8", "13/13"],
       ["调优前（同类运行）", "10–14", "57,691–77,152", "0.177–0.256", "104–107", "含返修"],
       ["mock 离线运行", "9", "约 1.0 万", "—", "0.3", "—"]],
      widths=[Pt(85), Pt(80), Pt(95), Pt(70), Pt(70), Pt(70)])
caption(doc, "表 7-1 实测性能数据（DeepSeek deepseek-chat，2026-11-17）")
body(doc, "需要说明的是：上述成本按平台内置单价参数估算，真实扣费以模型服务商账单为准；"
          "mock 模式下的 tokens 为模拟值，用于验证工程链路而非评测结论。")

heading(doc, "7.4 复现方式", 2)
p = doc.add_paragraph()
r = p.add_run("# 零安装启动控制台\n"
              "python -m harness.console\n\n"
              "# 跑一次（默认 mock，不需要 API Key）\n"
              "python -m harness.cli run\n\n"
              "# 回放任意历史运行\n"
              "python -m harness.cli replay <run_id>")
set_cn(r, "Consolas", 9)

# ---------------- 八 ----------------
heading(doc, "八、人工智能使用说明与局限", 1)

heading(doc, "8.1 大模型在各节点的实际作用", 2)
table(doc,
      ["节点", "模型作用", "是否可省略"],
      [["profile", "把结构化画像转写为可读结论", "可，但可读性下降"],
       ["clean", "把确定性清洗规则的依据讲清楚", "可"],
       ["analyze_a", "从规模与排名视角解读事实表", "不可，核心推理环节"],
       ["analyze_b", "从异常与交叉视角提出假设", "不可，构成交叉验证的另一路"],
       ["arbitrate", "比对两路结论、消解分歧", "不可，否则下游拿到矛盾信息"],
       ["deep_dive", "多维交叉的成因假设", "可"],
       ["report", "组织管理层语言、保持结构完整", "不可，决定交付质量"],
       ["review", "调模型逐条核对出处并给出结论", "可，但失去语义级审校"]],
      widths=[Pt(60), Pt(196), Pt(114)])
caption(doc, "表 8-1 大模型作用的边界")

heading(doc, "8.2 工具与协议的取舍", 2)
body(doc, "本期实际启用的工具是 csv_profile（确定性数据画像）与 sql_query（把 CSV 载入内存 SQLite 后"
          "执行只读 SQL）；python_eval 作为扩展点保留在工具注册表中，当前工作流未使用，"
          "其“沙箱”仅基于白名单内置函数，不具备容器级隔离能力，因此不在生产场景中推荐启用。"
          "MCP 与向量检索本期未启用：本场景所有结论都能用 SQL 复算，引入检索反而会削弱可验证性。"
          "平台在 models.py 与 tools.py 层预留了扩展点，接入 MCP Server 与知识库不需要改动引擎。")

heading(doc, "8.3 AI 的贡献边界", 2)
body(doc, "本项目中，AI 承担三类工作：一是作为被编排的“执行者”，即 6 个 Agent 的推理与写作；"
          "二是作为开发辅助，参与部分代码与文档起草；三是不承担的部分——数据清洗规则、"
          "验证判定逻辑、调度打分公式、循环终止条件，全部为确定性代码，不交由大模型决定。"
          "这一边界是刻意的：凡是“必须稳定可复现”的环节，一律不用模型。")

heading(doc, "8.4 已知局限", 2)
bullet(doc, "复算校验只覆盖数值型结论，纯文本类判断（如“哪个建议更可行”）仍依赖终审层，强度较弱。")
bullet(doc, "python_eval 为白名单内置函数的受限执行环境，并非真正的容器级沙箱。")
bullet(doc, "mock 后端的行为是确定性模拟，不代表真实模型的表现分布，不能替代真实评测。")
bullet(doc, "当前仅内置一个业务场景，跨场景迁移需要编写新的 flows 配置并调整验证规则。")
bullet(doc, "单机 SQLite 存储，不支持多用户并发；生产化需替换为服务型存储与任务队列。")

# ---------------- 附录 ----------------
heading(doc, "附录 A 团队分工", 1)
body(doc, "本项目为个人参赛，全部工作由一人完成：需求定义与场景选择、平台架构与编码、"
          "真实模型接入与缺陷修复、测试与评测、文档与演示材料。"
          "个人参赛的优势在于对每一处实现细节的掌握度——答辩中每一个设计决策都能追溯到"
          "具体的实现与实验记录。")

heading(doc, "附录 B 应用价值与推广路径", 1)
body(doc, "直接价值：为缺乏数据分析能力的中小企业提供“可核验”的经营诊断服务，"
          "把原本需要两天的表格分析压缩到一分钟以内，且结论可追溯。")
body(doc, "推广路径：其一，作为工具型产品按次计费，单次成本约 0.05 元，具备商业可行性；"
          "其二，作为企业内部的数据分析中台组件，替换“人工做表 + 口头汇报”的现有流程；"
          "其三，作为教学与实训平台，用于培养“可信 AI 应用”的工程能力。")
body(doc, "技术复用价值：平台本体与业务场景解耦，编排引擎、调度器、验证层可直接迁移到"
          "合规审查、投标文件检查、财务对账等同样具备“硬验证信号”的场景。")

heading(doc, "附录 C 交付物清单", 1)
table(doc,
      ["交付物", "说明"],
      [["方案书（本文档）", "赛题要求的 8 章技术方案，约 7000 字"],
       ["代码仓库", "含 12 个核心模块、测试、评测脚本与 README"],
       ["演示视频", "3–5 分钟，展示编排、调度、验证与返修全过程"],
       ["方案讲解 PPT", "正文 15 页，含架构图、截图与量化数据"],
       ["运行记录库", "runs.db，含历次真实运行的完整 trace"]],
      widths=[Pt(110), Pt(260)])
caption(doc, "表 C-1 交付物清单")

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(f"已生成：{OUT}")
print(f"段落数：{len(doc.paragraphs)}")
words = sum(len(p.text) for p in doc.paragraphs)
table_words = sum(len(c.text) for t in doc.tables for r in t.rows for c in r.cells)
print(f"正文字符数：{words}；表格字符数：{table_words}；合计约 {words + table_words}")
