# 数诊编排 DataDx

> 面向经营数据诊断的**多智能体编排调度平台**。
> 赛题一（Agent 编排创新应用）参赛作品。

输入一份脏的经营流水表和一句自然语言问题，平台调度 **7 个角色 / 8 个执行节点**
协作产出诊断报告，并对报告中**每一个数字**执行复算校验——数字对不上就打回返修，最多 3 轮。

> **参赛材料导航**
> 方案书 [`docs/方案书.pdf`](docs/方案书.pdf) ｜ 讲解 PPT [`docs/方案讲解PPT.pptx`](docs/方案讲解PPT.pptx) ｜ 系统截图 [`docs/截图/`](docs/截图/)

---

## 一、30 秒跑起来（零第三方依赖）

**环境要求：Python 3.10 或更高版本**，其他什么都不用装。

```powershell
# 1) 进入目录
cd futurecup

# 2) 不需要 pip install，直接跑
python -m harness.cli run

# 3) 打开可视化控制台
python -m harness.console
#    浏览器访问 http://127.0.0.1:8080
```

默认使用 **mock 后端**（离线确定性），**不需要 API Key 就能完整看到全流程**。
这是刻意的设计：评审专家在任何机器上都能复现演示。

### 接真实大模型（可选）

```powershell
copy .env.example .env
# 用记事本打开 .env，填入你的 HARNESS_API_KEY，保存
python check_model.py          # 先做连通性自检，5 秒出结果
python -m harness.cli run      # 通过后再跑完整流程
```

`.env` 会被自动加载（零依赖自实现），**不用每次开终端都重设环境变量**。
兼容任何 OpenAI 协议网关：DeepSeek、通义千问、智谱、vLLM、Ollama。
换模型只改 `.env` 里的两行，不动一行代码。

> ⚠️ `.env` 里是密钥，已被 `.gitignore` 排除，**不要提交到 GitHub**。

---

## 二、常用命令

| 命令 | 作用 |
|---|---|
| `python check_model.py` | **模型连通性自检**（5 秒判断 key/余额/网络是否正常） |
| `python run_demo.py` | 一键演示入口（等价于 `run --fault`），给 PyCharm 的 ▶ 用 |
| `python -m harness.cli run` | 跑一次完整流程（默认数据集） |
| `python -m harness.cli run --dataset "data/xxx.csv"` | **换一份数据跑**（列名需同结构） |
| `python -m harness.cli run --question "哪个月最好？"` | 换业务问题（也覆盖问题文本） |
| `python -m harness.cli run --fault` | **注入一次故障**（报告输出截断），演示"验证抓错 → 自动返修" |
| `python -m harness.cli replay <run_id>` | 离线回放任意一次历史运行 |
| `python -m harness.cli eval` | 三组基线对比评测，输出 `eval/results.md` |
| `python -m harness.console` | 打开 Web 控制台（DAG 图 + 时间线 + 验证记录） |

跑测试：

```powershell
python -m unittest discover -s tests -v
```

---

## 三、架构

```
flows/*.json          ─┐
config/agents.json    ─┼─▶ engine.py   DAG 执行器（分层并行/条件分支/节点循环/回溯重写）
data/*.csv            ─┘        │         （默认 data/sales.csv，可用 --dataset 换任意同结构表）
                                ├─▶ scheduler.py  能力画像 + UCB + 成本/负载打分
                                │       └─ 决策明细写进 trace，界面可解释
                                ├─▶ tools.py      csv_profile / sql_query / python_eval
                                ├─▶ models.py     MockBackend | OpenAICompat
                                ├─▶ verify.py     规则 / 复算 / 交叉 / LLM终审 → 置信度门控
                                └─▶ store.py      SQLite trace：runs/nodes/verdicts/metrics
                                          │
                                    console.py 零依赖 Web 界面
```

### 内置两份演示数据

| 文件 | 规模 | 用途 |
|---|---|---|
| `data/sales.csv` | 240 行（含 5 条脏数据） | 默认数据集，方案书与实践数据均基于它 |
| `data/demo_second.csv` | 120 行，完全不同数字 | 用于证明"不是为某份数据写死" |

```bash
python -m harness.cli run --dataset data/demo_second.csv --question "哪个区域最赚钱？"
```

两份数据跑出来的报告内容完全不同，而代码一行未改。

### 为什么自研引擎，不用 LangChain / Dify / CrewAI

赛题技术要求原文：

> 「必须体现 Agent 编排与调度的智能化，而非简单的硬编码流程」
> 「禁止直接套用现成框架的默认示例」

现成框架的默认用法就是"按顺序跑一串 Task"，这恰好是赛题点名要避免的。
自研约 340 行 DAG 引擎，换来的是**调度策略、验证机制、自循环全部可解释、可修改**。

---

## 四、六项核心能力对照

| 赛题要求 | 本实现 |
|---|---|
| Agent 团队定义与管理 | `config/agents.json`：角色 / 提示词 / 工具集 / 模型档位 / 成本参数 |
| 工作流编排 | `flows/*.json`：DAG + 并行分层 + `when` 条件分支 + 节点级循环返修 |
| 智能调度引擎 | 能力画像（历史成功率）+ UCB 探索 + 成本 / 延迟 / 负载扣分，决策可解释 |
| 工具与外部系统集成 | `csv_profile` / `sql_query`（真 SQLite 执行）/ `python_eval`（受限） |
| 执行监控与结果验证 | 全链路 trace + 四层验证 + 置信度门控 + 人工介入标记 |
| 反馈与自我优化 | 验证证据回灌为返修指令，节点内最多 3 轮迭代；跨运行沉淀能力画像 |

### 四层验证（核心）

| 层 | 判什么 | 可否机器判定 |
|---|---|---|
| L1 `rule` | 长度 / 必备小节 / 禁止占位符 | ✅ 确定性 |
| L2 `recompute` | **报告中每个绝对值 ≥1000 的数字，必须能在事实表复算出来（容差 0.5%）** | ✅ 确定性 |
| L3 `cross` | 两个独立 Agent 的数字集合互相印证 | ✅ 确定性 |
| L4 `llm_judge` | 报告是否逐条给出出处 | ⚠️ 模型判断（mock 下为启发式） |

L2 是本项目的关键：它把"AI 说得好听"变成"AI 说得可证伪"。

---

## 五、评测（量化证据）

```powershell
python -m harness.cli eval
```

三组配置跑同一批任务（`eval/tasks.jsonl`），同一套判定标准：

- **A 单 Agent 直连** —— 有数据访问，但一次性输出、无验证
- **B 固定串行** —— 多 Agent，但无验证、无返修
- **C 本平台** —— 能力画像调度 + 分层验证 + 自循环

结果写入 `eval/results.md` / `results.json`。

### 已产出的对比（mock 后端，12 条任务）

| 配置 | 成功率 | 平均置信度 | 平均尝试次数 | 人工介入率 |
|---|---|---|---|---|
| A 单 Agent 直连 | 75.0% | 0.90 | 1.0 | 0% |
| B 固定串行 | 75.0% | 0.92 | 6.0 | 0% |
| **C 本平台** | **100.0%** | **1.00** | 7.6 | 0% |

> ⚠️ **诚实声明**：上表为 mock 后端（确定性故障注入）下的链路验证结果，
> 说明"验证层能把漂移数字捞回来"这条闭环真实有效，但**不能作为真实模型的效果结论**。
> 配置真实模型后重跑 `python -m harness.cli eval` 即得真实数据。
>
> 真实模型（DeepSeek deepseek-chat）的单次运行实测见下节。

### 真实模型单次实测（2026-11-11）

| 场景 | 调用次数 | tokens | 成本 | 耗时 | 验证通过 |
|---|---|---|---|---|---|
| 全绿运行 | 6 | 18,713 | ¥0.0541 | 37.9 s | 8/8 |
| 含返修运行 | 7 | 25,947 | ¥0.0756 | 41.6 s | 10/10 |

### 测试

```powershell
python -m unittest discover -s tests -v
```

11 项用例覆盖四类断言：工作流结构、数据一致性、验证器行为、端到端流程。
其中 1 项为"真实模型报告回归"用例，依赖 `tests/fixtures/report_real_model.md`
（一次真实运行的输出快照），该样本缺失时自动跳过——重建方法见 `tests/test_smoke.py` 注释。

---

## 六、交付物

| 文件 | 说明 |
|---|---|
| `docs/方案书.pdf` / `.docx` | 技术方案书，16 页、约 1 万字、11 张表、5 张截图 |
| `docs/方案讲解PPT.pptx` | 基于大赛官方模版的 15 页讲解稿 |
| `docs/截图/` | 5 张系统实录截图（含对应 run_id） |
| `docs/参赛作战手册.md` | 参赛排期与自查清单 |

---

## 七、已知局限（主动披露）

1. `python_eval` 是白名单内置函数的**受限**执行环境，不是真正的容器沙箱；当前工作流未启用它。
2. mock 后端的"模型行为"是确定性模拟，不代表真实 LLM 的表现分布。
3. 复算校验只覆盖数值型结论；纯文本类结论的验证依赖 L4，强度较弱。
4. 目前仅内置一个业务场景（经营数据诊断），新增场景需编写新的 `flows/*.json`；
   数据侧已支持任意同结构 CSV（`--dataset`）。
5. 单机 SQLite 存储，不支持多用户并发。

---

## 八、目录结构

```
futurecup/
├── config/agents.json        7 个 Agent 的角色与能力定义
├── flows/data_insight.json   工作流（DAG，8 节点 / 7 层）
├── data/sales.csv            主演示数据集（240 行，含 3 类脏数据）
├── data/demo_second.csv      第二份数据集（120 行，用于验证与数据无关）
├── harness/                  12 个核心模块（约 2300 行）
│   ├── engine.py             DAG 执行引擎 + 自循环
│   ├── scheduler.py          能力画像调度器
│   ├── verify.py             四层验证 + 置信度门控
│   ├── tools.py              工具层（csv_profile / sql_query / python_eval）
│   ├── models.py             模型抽象（mock / OpenAI 兼容）
│   ├── loadenv.py            零依赖 .env 加载
│   ├── mockllm.py            离线确定性后端
│   ├── store.py              SQLite trace
│   ├── console.py            零依赖 Web 控制台
│   └── cli.py                命令行入口
├── eval/                     任务集 + 评测脚本 + 结果
├── tests/                    单元测试（含真实报告回归）
├── tools/                    辅助脚本（生成方案书/PPT、查看运行、自审）
└── docs/                     方案书、PPT、截图
```
