"""自纠错闭环的集成测试 —— 用桩模型强制"第一次修复失败"。

这是对系统核心卖点的直接验证：验证失败时确实会带着执行反馈回到修复节点，
而不是空转到超限。用桩模型而非真实 LLM，因此完全确定性、可重复。
"""

import asyncio

from langchain_core.messages import AIMessage

from graph.state import BugReport, BugItem, FixResult
from graph.workflow import build_workflow


class _StubStructured:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = 0

    def invoke(self, messages):
        idx = min(self.calls, len(self.outputs) - 1)
        self.calls += 1
        return {"raw": None, "parsed": self.outputs[idx], "parsing_error": None}


class StubModel:
    """按顺序返回预设的修复结果，模拟"第一次修错、第二次修对"。"""

    def __init__(self, fix_outputs):
        self.fix_outputs = fix_outputs
        self.fix_tool = None

    def with_structured_output(self, schema, method=None, include_raw=False):
        if schema is BugReport:
            return _StubStructured(
                [BugReport(has_bug=True, bugs=[BugItem(line=2, type="除零", severity="high", description="除数为 0")])]
            )
        if schema is FixResult:
            if self.fix_tool is None:
                self.fix_tool = _StubStructured(self.fix_outputs)
            return self.fix_tool
        raise AssertionError(f"未预期的 schema: {schema}")

    def invoke(self, messages):
        return AIMessage(content="【桩报告】处理完成")


BROKEN = "raise RuntimeError('第一次修复仍然是坏的')\n"
GOOD = "print('第二次修复成功')\n"


def _run(fix_outputs, model=None):
    """research 节点是异步的，因此整张图必须用 ainvoke。"""
    wf = build_workflow(model or StubModel(fix_outputs), rag_search=None, search_tool=None)
    return asyncio.run(
        wf.ainvoke(
            {"code": "def d(a, b):\n    return a / b\nprint(d(1, 0))", "error": "", "messages": []},
            config={"recursion_limit": 25},
        )
    )


def test_第一次修复失败会触发重试():
    result = _run([FixResult(fixed_code=BROKEN, explanation="第一次"), FixResult(fixed_code=GOOD, explanation="第二次")])

    assert result["fix_attempts"] == 2, "验证失败后应当回到修复节点重试"
    assert result["verification"].passed is True, "第二次修复应当通过验证"


def test_重试时执行反馈被回灌():
    """裸回环会让修复节点读到和上一轮相同的状态，产出同样的代码而空转。"""
    result = _run([FixResult(fixed_code=BROKEN, explanation="第一次"), FixResult(fixed_code=GOOD, explanation="第二次")])

    assert "RuntimeError" in result["verify_feedback"], "应把上一轮的执行错误写回 state"


def test_一直失败时受重试上限约束():
    """必须有上界，否则失败样本会无限回环烧 token。"""
    result = _run([FixResult(fixed_code=BROKEN, explanation="永远失败")])

    assert not result["verification"].passed
    assert result["fix_attempts"] == 3, "应在 MAX_FIX_ATTEMPTS 处停止"
    assert "报告" in result["report"] or result["report"], "超限后仍应产出报告"


def test_无bug时不进入修复流程():
    class CleanModel(StubModel):
        def with_structured_output(self, schema, method=None, include_raw=False):
            if schema is BugReport:
                return _StubStructured([BugReport(has_bug=False, bugs=[])])
            raise AssertionError("无 bug 时不应进入修复节点")

    result = _run([], model=CleanModel([]))

    assert result.get("fix_attempts", 0) == 0
    assert result.get("verification") is None
