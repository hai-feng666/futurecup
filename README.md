# 数诊编排 DataDx

> 面向经营数据诊断的**多智能体编排调度平台**。
> 赛题一（Agent 编排创新应用）参赛作品。

输入一份脏的经营流水表和一句自然语言问题，平台调度 6 个 Agent 协作产出诊断报告，
并对报告中**每一个数字**执行复算校验——数字对不上就打回返修，最多 3 轮。

---

## 一、30 秒跑起来（零第三方依赖）

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
| `python -m harness.cli run` | 跑一次完整流程 |
| `python -m harness.cli run --fault` | **强制注入一次数字漂移**，演示"验证抓错 → 自动返修" |
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
config/agents.json    ─┼─▶ engine.py   DAG 执行器（顺序/并行/条件/循环/子流程）
data/sales.csv        ─┘        │
                                ├─▶ scheduler.py  能力画像 + UCB + 成本/负载打分
                                │       └─ 决策明细写进 trace，界面可解释
                                ├─▶ tools.py      csv_profile / sql_query / python_eval
                                ├─▶ models.py     MockBackend | OpenAICompat
                                ├─▶ verify.py     规则 / 复算 / 交叉 / LLM终审 → 置信度门控
                                └─▶ store.py      SQLite trace：runs/nodes/verdicts/metrics
                                          │
                                    console.py 零依赖 Web 界面
```

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

> ⚠️ **诚实声明**：mock 后端下的对比数字是模拟值，只用于验证工程链路，
> 不能作为评测结论。换真实模型后重跑本命令，即可得到可写入决赛材料的数字。

---

## 六、已知局限（主动披露）

1. `python_eval` 是白名单内置函数的**受限**执行环境，不是真正的容器沙箱。
2. mock 后端的"模型行为"是确定性模拟，不代表真实 LLM 的表现分布。
3. 复算校验只覆盖数值型结论；纯文本类结论的验证依赖 L4，强度较弱。
4. 目前仅内置一个业务场景（经营数据诊断），新增场景需编写新的 `flows/*.json`。

---

## 七、目录结构

```
futurecup/
├── config/agents.json        6 个 Agent 的角色与能力定义
├── flows/data_insight.json   工作流（DAG）
├── data/sales.csv            演示数据集（240 行，含 3 类脏数据）
├── harness/
│   ├── engine.py             DAG 执行引擎 + 自循环
│   ├── scheduler.py          能力画像调度器
│   ├── verify.py             四层验证 + 置信度门控
│   ├── tools.py              工具层
│   ├── models.py             模型抽象（mock / OpenAI 兼容）
│   ├── store.py              SQLite trace
│   ├── console.py            零依赖 Web 控制台
│   └── cli.py                命令行入口
├── eval/                     任务集 + 评测脚本 + 结果
└── tests/                    冒烟测试
```
