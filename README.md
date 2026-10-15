# Code Doctor

[![tests](https://github.com/OvoHao888/code-doctor/actions/workflows/tests.yml/badge.svg)](https://github.com/OvoHao888/code-doctor/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> **开发周期：2026.04 起步（v1）→ 2026.10 重构为 v2** ｜ 2026.10 整理开源
>
> 本项目 2026 年 4 月起步，先完成 RAG 语料与 MCP 工具雏形。2026 年 10 月做了一次完整重构：
> 把 v1 的 5 个 ReAct Agent 直线流程改成 3 次结构化 LLM 调用 + 6 节点条件路由图，
> 单请求耗时由约 68 秒降至约 25 秒。`legacy` 分支保留的是重构前的 v1 实现。
> 仓库中的提交时间集中在 10 月，它们是**重构与加固记录**，不是开发记录。

一个**自纠错**的多智能体 Python 代码诊断与修复系统。提交代码后，系统会完成
静态分析 → 问题检测 → 代码修复 → **实际执行验证** → 生成报告的完整闭环，
并在验证失败时带着执行错误回炉重试。

核心特点：**修复是否成功由"把代码真跑一遍"来判定，而不是让 LLM 自评。**

---

## 架构

```
START → analyze → check → research ─┬─(无问题)─────────────────→ report → END
                                    └─(有问题) → fix → verify ─┬─(执行通过) → report
                                                               └─(失败且未超限) → fix
                                                                  （带 stderr 回炉重试）
```

| 节点 | 类型 | 说明 |
|---|---|---|
| `analyze` | **纯代码** | pyflakes + 自研 AST 检查（低误报），产出事实证据 |
| `check` | LLM ×1 | 结构化输出 `BugReport{has_bug, bugs[], confidence}` |
| `research` | **MCP**（条件触发） | 仅当检测置信度低于阈值时联网检索，并入证据 |
| `fix` | LLM ×1 | 结构化输出 `FixResult{fixed_code}` |
| `verify` | **纯代码** | `subprocess` 实际执行修复后代码，用退出码/stderr 判定 |
| `report` | LLM ×1 | 生成诊断报告 |

**一次请求固定 3 次 LLM 调用**（对比改造前：5 个 ReAct agent、~68 秒）。
实测单请求 **~15-30 秒**，token 约 3.8k-5.9k。

---

## 版本说明

本仓库有两个分支，对应这个系统的两次实现：

| 分支 | 版本 | 形态 | 单请求耗时 |
|---|---|---|---|
| `main` | **v2（当前）** | 6 节点有向图 + 2 条条件边，3 次结构化 LLM 调用 | ~25 秒 |
| `legacy` | v1（原始实现） | 5 个 `create_react_agent` 串成一条直线，无分支路由 | ~68 秒 |

### v1 存在的问题

- **所有节点都是 ReAct Agent。** 解析 / 检测 / 修复 / 报告 / 管理 5 个节点各自跑完整的
  ReAct 多轮循环，但检测与修复本质是「给定事实 → 产出结构化结论」，一次调用就够。
- **图是直线，没有任何条件边。** `graph/workflow.py` 里只有 5 条 `add_edge`；
  名为 `Supervisor` 的节点实际上从未参与路由决策。
- **验证只做 `ast.parse`。** 语法合法不等于能跑起来；而让模型自评修复结果又存在确认偏误。
- **MCP 工具从未生效。** 模块导入时用 `*mcp_tools` 解包，但工具加载发生在服务启动阶段，
  解包到的是空列表 —— 联网能力静默失效，且不报错。
- **没有重试、没有评测。** 修复失败无法收敛，效果也无法量化。

### v2 的改动

1. 5 个 ReAct Agent → 3 次结构化 LLM 调用（检测 / 修复 / 报告）+ 6 节点有向图
2. 路由改为纯函数，只读 state 上的结构化字段，零 token 且可穷举单测
3. 用 `subprocess` 真实执行修复后代码，以退出码和 stderr 作为可证伪判据
4. 重试带上界（`MAX_FIX_ATTEMPTS`），并把执行错误回灌给下一轮修复
5. MCP 工具改为服务启动后注入节点，并改成「低置信度才联网」的条件触发
6. 新增 33 个单元测试与 27 条样本的评测集

两个版本的完整差异：`git diff legacy main`

---

## 关键设计决策

以下每一条都是为了解决一个具体问题：

**1. 路由是确定性的，不花 LLM token**
分支判断完全基于 state 上的结构化字段（`bug_report.has_bug`、`verification.passed`），
不去解析 messages 里的自由文本。"能用代码判断的绝不交给 LLM" —— 路由因此可复现、可单测。

**2. 用执行结果当裁判，而不是让 LLM 自评**
`validate_fix_is_correct` 这类"LLM 检查自己修得对不对"的设计存在确认偏误 ——
它倾向于宣称成功。改用 `subprocess` 实际运行，退出码和 stderr 是**可证伪**的证据。

**3. 不是所有节点都该是 agent**
原实现把 5 个节点全做成 `create_react_agent`，每个都跑完整 ReAct 多轮循环。
但检测/修复本质是"给定事实 → 产出结构化结论"，一次调用足够。只有真正需要
多轮工具调用的场景才值得上 ReAct。

**4. 重试必须回灌执行反馈**
裸回环会让 FixAgent 读到和上一轮完全相同的状态，产出同样的代码，空转到超限。
`verify` 失败时把 stderr 写回 state，下一轮修复才能对症下药。

**5. 回环必须有上界**
`MAX_FIX_ATTEMPTS` 封顶，超限后如实出报告并标记失败，而不是无限烧 token。

**6. 非崩溃类缺陷需要静态判据**
资源泄漏、裸 `except` 这类问题不修也不会让程序报错，执行结果无法区分修没修。
评测对这类样本补了静态断言（`uses_with_open` / `no_bare_except`）作为 oracle。

---

## 快速开始

> 需要 **Python 3.11 或更高**（CI 在 3.11 / 3.12 上跑全量测试）。

```bash
# 1. 准备环境变量
cp .env.example .env    # 填入你的 API Key

# 2. 安装依赖
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 3. 启动服务（Windows 直接双击 start.bat）
set PYTHONIOENCODING=utf-8
.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

然后浏览器打开 **http://localhost:8000** 即可 —— 前端页面由后端直接提供，
不需要单独起前端服务，也不用去双击 html 文件。

环境变量：

| 变量 | 说明 |
|---|---|
| `OPENAI_API_KEY` / `OPENAI_API_BASE` | LLM 接入（OpenAI 兼容协议） |
| `LLM_MODEL` | 模型名 |
| `SILICON_API_KEY` / `SILICON_API_BASE` | Embedding 服务（RAG 用） |
| `TAVILY_API_KEY` | 联网调研（MCP）。**不配置则自动跳过，不影响主流程** |
| `RAG_ENABLED` | 默认 `0`（关闭）。改为 `1` 开启 —— 理由见评测章节 |
| `MAX_FIX_ATTEMPTS` | 修复重试上限，默认 3 |
| `VERIFY_TIMEOUT` | 执行验证超时秒数，默认 5 |

---

## API

服务启动后：

- `GET /` 返回前端页面（前后端同源，只占一个端口）
- `GET /docs` 是 Swagger UI，可直接在浏览器里调试

### `POST /checkCode`

```bash
curl -X POST http://127.0.0.1:8000/checkCode \
  -H "Content-Type: application/json" \
  -d '{"code": "data = [1, 2, 3]\nprint(data[10])", "error": "IndexError: list index out of range"}'
```

响应（字段省略了正文）：

```json
{
  "report": "## 问题概述\n...",
  "has_bug": true,
  "bugs": [
    {"line": 2, "type": "索引越界", "severity": "high", "description": "访问下标 10，超出列表长度 3"}
  ],
  "confidence": 0.95,
  "fixed_code": "data = [1, 2, 3]\nif len(data) > 10:\n    print(data[10])",
  "fix_attempts": 1,
  "verification": {
    "passed": true, "exit_code": 0,
    "stdout": "", "stderr": "", "timed_out": false, "duration": 0.031
  },
  "stats": {"llm_calls": 3, "total_tokens": 3903, "duration": 25.3}
}
```

### `GET /health`

```bash
curl http://127.0.0.1:8000/health
# {"message": "Code Doctor is running"}
```

## 评测

```bash
# 数据集自检（断言必须在原始有 bug 代码上失败，否则没有区分度）
python eval/run_eval.py --validate-dataset

# 完整评测
python eval/run_eval.py --rag on  --concurrency 3
python eval/run_eval.py --rag off --concurrency 3   # 消融：关闭 RAG
```

评测集包含 **19 个带标注 bug 样本 + 8 个干净样本**。负样本是必需的 —— 只有正样本时，
"永远报 bug"的检测器召回率就是 100%，指标毫无意义。

**指标定义**

| 指标 | 含义 |
|---|---|
| recall | 标注问题中被检出的比例（行号容差 ±3） |
| precision | 报出的问题中真实存在的比例 |
| F1 | 主指标 |
| FPR | **干净样本**上被误报的比例（防"永远报 bug"） |
| 修复成功率 | 修复后代码通过隐藏断言的比例 |

### 实测结果

在 27 个样本（19 正 / 8 负）上，`temperature=0`：

| 配置 | 语料 | 检索 query | recall | precision | **F1** | 误报率 | 修复成功率 | 耗时 | token |
|---|---|---|---|---|---|---|---|---|---|
| **RAG off** | — | — | 94.7% | 94.7% | **94.7%** | 0% | 100% | 25.3s | 3903 |
| RAG on | 通用文档 | 原始代码 | 100% | 95.0% | 97.4% | 0% | 100% | 26.6s | 5175 |
| RAG on | bug 语料 | 原始代码 | 68.4% | 76.5% | 72.2% | 0% | 94.7% | 27.8s | 4779 |
| RAG on | bug 语料 | 增强 query | 94.7% | 81.8% | 87.8% | 0% | 100% | 24.3s | 5006 |

### 怎么读这张表（重要）

**可以确信的结论：**

- 检测能力整体可用：非退化配置下 F1 在 87%~97%，**干净样本误报率始终为 0** —— 8 个无 bug 样本没有一个被误报。
- 修复环节稳定：**修复成功率 94.7%~100%**，且这个指标是用隐藏断言 + 实际执行判定的，不是"退出码 0"。

**不能确信的结论 —— 我没有证明 RAG 有收益：**

> RAG 三种配置之间的 F1 跨度是 **72.2% ~ 97.4%**，这个方差**远大于**"开 RAG"与"关 RAG"之间的差距（94.7% vs 最好 97.4%）。
> 也就是说，**检索配置的选择比"要不要 RAG"影响更大**，而当前样本量下无法把差异归因给任何单一因素。

这不是含糊其辞，而是这个实验本身**存在我应当指出的缺陷**：

1. **变量没有完全隔离。** A 臂（通用语料）与 B 臂（bug 语料）之间，我除了换语料还同时改了检索距离阈值（1.2 → 0.9）。B 臂 72.2% 的骤降无法确定是语料导致的还是阈值导致的。这是我实验设计上的失误。
2. **样本量太小。** n=27 的置信区间很宽，各臂只跑了一次。
3. **`temperature=0` 不保证可复现。** 服务端的推理实现不保证确定性，单次运行的差异可能只是采样噪声。

**因此默认关闭 RAG**（`RAG_ENABLED=0`）：既然测量不支持它，而它确定性地增加延迟与 token 消耗，那就不该默认开着。RAG 的完整实现与消融框架都保留在仓库里，随时可以开启。

**要给出可信结论，需要：** 固定检索配置只变一个变量、每配置重复 k=3 次取均值±标准差、样本量扩到 100+，并预注册主指标。这是明确的后续工作。

### 单条样本的观察

- RAG=off 时**完全漏检** `index_oob`（`data = [1,2,3]; print(data[10])`），RAG=on 时检出。
- 精确率的扣分主要来自**同一个 bug 被报在多行**（如 `div_zero_ratio` 同时报第 2 行与第 6 行）。当前口径按"每条预测独立计分"，这属于口径偏严，而非真的误报。

---

## 已知边界（诚实说明）

- **执行验证不是安全沙箱。** 当前用 `subprocess -I` + 独立临时目录 + 硬超时，
  能防误伤，防不住蓄意逃逸。生产环境应放进一次性容器：
  `docker run --rm --network none --read-only --memory 256m --pids-limit 64`
- **超时只杀直接子进程。** Windows 上孙进程可能存活，需要 `taskkill /T` 或 Job Object。
- **评测样本量小（27 条）且各配置只跑一次**，结论是方向性的，不具备统计显著性。
- **消融实验存在未隔离的变量**（详见评测章节），因此**不能宣称 RAG 带来收益**。
- **`temperature=0` 不保证可复现**，服务端推理实现可能有采样差异。
- **报告节点未做结构化输出约束**，返回的是自由文本 Markdown。

---

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

覆盖路由分支（含回环有界性穷举）、执行验证（通过/失败/超时/编码/隔离）、
静态分析（真阳性 + 不误报）。
