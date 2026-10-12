"""LLM 节点 —— 每个节点只做一次结构化调用。

设计说明：
    原项目把 5 个节点全做成 create_react_agent，每个都要跑完整的 ReAct 多轮循环，
    单次请求耗时 ~68s，且路由只能靠解析自由文本来猜。
    这里的关键判断是：**不是所有节点都该是 agent**。
      - 检测/修复/报告：只需要"给定事实 → 产出结构化结论"，一次调用足够；
      - 真正需要多轮工具调用的场景（本项目里没有），才值得上 ReAct。
    代价是 LLM 调用从「5 个 agent × 每个若干轮」降到固定的 3 次。
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .state import BugReport, FixResult

# DashScope 兼容模式不支持 json_schema 形态的 response_format，
# 必须显式走 function calling 路径。（已实测：默认路径返回
# "This response_format type is unavailable now"）
STRUCTURED_METHOD = "function_calling"


def _structured_call(model, schema, messages):
    """一次结构化调用，同时返回解析结果与 token 用量。

    include_raw=True 是为了拿到 usage_metadata —— 单独用结构化输出会把原始
    AIMessage 丢掉，就没法统计 token 了。
    """
    llm = model.with_structured_output(schema, method=STRUCTURED_METHOD, include_raw=True)
    out = llm.invoke(messages)

    raw = out.get("raw")
    parsed = out.get("parsed")
    parse_error = out.get("parsing_error")

    tokens = 0
    if raw is not None and getattr(raw, "usage_metadata", None):
        tokens = raw.usage_metadata.get("total_tokens", 0)

    return parsed, tokens, parse_error


def _accumulate(state, tokens):
    return {
        "llm_calls": state.llm_calls + 1,
        "total_tokens": state.total_tokens + tokens,
    }


CHECK_SYSTEM = """你是资深 Python 代码审查专家。你的任务是判定代码是否存在需要修复的问题。

你会收到三部分信息：
1. 用户的原始代码
2. 用户提供的运行时错误信息（可能为空）
3. 由确定性静态分析工具产出的检查证据

要求：
- 静态分析证据是**事实**，请优先采信；但不要因为工具没报就断定无问题。
- 如果用户提供了运行时错误信息，以它为准来定位问题。
- 只报告你有明确把握的问题，不要罗列"可能存在"的猜测 —— 精确率同样重要。
- has_bug 为 false 时，bugs 必须为空列表。
- line 必须是对应到原始代码的真实行号。"""

FIX_SYSTEM = """你是资深 Python 代码修复专家。你的任务是根据检测到的问题，输出修复后的完整代码。

要求：
- fixed_code 必须是**完整、可直接执行**的 Python 代码，从第一行到最后一行。
- 严禁包含 markdown 代码块标记（```），严禁添加原代码中不存在的注释风格（如 C 的 // 或 /* */）。
- 保持原有函数签名和程序行为不变，只修复被指出的问题。
- 如果收到"上一次修复执行失败"的反馈，必须针对该执行错误调整方案，不要重复上一轮的做法。
- 修复后代码应当能被实际运行通过。"""

REPORT_SYSTEM = """你是技术报告撰写专家。请根据完整的处理过程，生成一份结构化的中文诊断报告。

报告应包含：问题概述、根因分析、修复方案说明、修复后代码、验证结果。
使用 Markdown 格式。如果验证未通过，必须如实说明失败原因，不要粉饰。"""


def make_check_node(model):
    def check(state) -> dict:
        user_error = state.error.strip() if state.error else "（用户未提供）"
        prompt = f"""## 原始代码
```python
{state.code}
```

## 用户提供的运行时错误
{user_error}

## 静态分析证据
{state.evidence or "（无）"}

请判定代码是否存在问题。"""

        parsed, tokens, err = _structured_call(
            model, BugReport, [SystemMessage(content=CHECK_SYSTEM), HumanMessage(content=prompt)]
        )

        updates = _accumulate(state, tokens)

        if parsed is None:
            # 解析失败时保守处理：倾向于进入修复分支，而不是漏报
            parsed = BugReport(has_bug=True, bugs=[], confidence=0.0)
            note = f"【检测】结构化解析失败（{err}），保守进入修复流程"
        elif parsed.has_bug:
            note = f"【检测】发现 {len(parsed.bugs)} 个问题（置信度 {parsed.confidence}）"
        else:
            note = "【检测】未发现需要修复的问题"

        updates["bug_report"] = parsed
        updates["messages"] = [AIMessage(content=note)]
        return updates

    return check


def make_fix_node(model):
    def fix(state) -> dict:
        report = state.bug_report
        bugs_text = "（无具体条目，请根据静态分析证据与错误信息定位）"
        if report and report.bugs:
            bugs_text = "\n".join(
                f"- 行{b.line} [{b.severity}] {b.type}：{b.description}" for b in report.bugs
            )

        feedback = state.verify_feedback.strip()
        feedback_block = f"\n## 上一次修复的执行失败反馈（重要）\n{feedback}\n" if feedback else ""

        prompt = f"""## 原始代码
```python
{state.code}
```

## 用户提供的运行时错误
{state.error.strip() or "（无）"}

## 需要修复的问题
{bugs_text}

## 静态分析证据
{state.evidence or "（无）"}
{feedback_block}
请输出修复后的完整代码。"""

        parsed, tokens, err = _structured_call(
            model, FixResult, [SystemMessage(content=FIX_SYSTEM), HumanMessage(content=prompt)]
        )

        updates = _accumulate(state, tokens)
        updates["fix_attempts"] = state.fix_attempts + 1

        if parsed is None:
            # 修复失败时退回原始代码，让验证节点如实报错，而不是假装成功
            updates["fixed_code"] = state.code
            updates["fix_explanation"] = f"修复节点输出解析失败：{err}"
            updates["messages"] = [AIMessage(content=f"【修复】第 {state.fix_attempts + 1} 次尝试解析失败")]
        else:
            updates["fixed_code"] = _strip_code_fence(parsed.fixed_code)
            updates["fix_explanation"] = parsed.explanation
            updates["messages"] = [
                AIMessage(content=f"【修复】第 {state.fix_attempts + 1} 次尝试：{parsed.explanation}")
            ]

        return updates

    return fix


def _strip_code_fence(text: str) -> str:
    """LLM 常无视指令带上 ``` 围栏，这里兜底剥掉。"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        lines = lines[1:]  # 去掉开头的 ```python
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t.strip()


def make_report_node(model):
    def report(state) -> dict:
        verification = state.verification
        if verification is None:
            verify_text = "未执行"
        elif verification.passed:
            verify_text = f"通过（退出码 0，耗时 {verification.duration}s）"
        else:
            verify_text = f"未通过 —— {verification.feedback()}"

        report_obj = state.bug_report
        bugs_text = "未发现明确问题"
        if report_obj and report_obj.bugs:
            bugs_text = "\n".join(
                f"- 行{b.line} [{b.severity}] {b.type}：{b.description}" for b in report_obj.bugs
            )

        prompt = f"""## 原始代码
```python
{state.code}
```

## 用户提供的运行时错误
{state.error.strip() or "（无）"}

## 检测到的问题
{bugs_text}

## 静态分析证据
{state.evidence or "（无）"}

## 修复尝试次数
{state.fix_attempts}

## 修复说明
{state.fix_explanation or "（未进入修复流程）"}

## 修复后代码
```python
{state.fixed_code or "（未进入修复流程）"}
```

## 执行验证结果
{verify_text}

请生成诊断报告。"""

        response = model.invoke(
            [SystemMessage(content=REPORT_SYSTEM), HumanMessage(content=prompt)]
        )

        tokens = 0
        if getattr(response, "usage_metadata", None):
            tokens = response.usage_metadata.get("total_tokens", 0)

        text = response.content if isinstance(response.content, str) else str(response.content)

        updates = _accumulate(state, tokens)
        updates["report"] = text
        updates["messages"] = [AIMessage(content=f"【报告已生成】共 {len(text)} 字")]
        return updates

    return report
