from pydantic import BaseModel, Field
from typing import List, Any, Annotated, Optional
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps


def keep_last(a, b):
    """Reducers: 后写入的值覆盖先前的（None 不覆盖）。"""
    return b if b is not None else a


class BugItem(BaseModel):
    """一条被检测出来的问题。"""
    line: int = Field(description="问题所在行号，从 1 开始")
    type: str = Field(description="问题类型，如 除零/索引越界/空值解引用/资源泄漏/可变默认参数")
    severity: str = Field(description="严重程度: high | medium | low")
    description: str = Field(description="问题的具体说明")


class BugReport(BaseModel):
    """检测节点的结构化输出。路由据此决定是否进入修复分支。"""
    has_bug: bool = Field(description="代码是否存在需要修复的问题")
    bugs: List[BugItem] = Field(default_factory=list, description="检测出的问题列表")
    confidence: float = Field(default=1.0, description="对本次判断的置信度 0~1")


class FixResult(BaseModel):
    """修复节点的结构化输出。fixed_code 必须是可直接执行的完整 Python 代码。"""
    fixed_code: str = Field(description="修复后的完整 Python 代码，不含 markdown 代码块标记")
    explanation: str = Field(default="", description="修复思路说明")
    changed: bool = Field(default=True, description="是否真的做了改动")


class VerifyResult(BaseModel):
    """执行式验证的结果。由真实运行修复后代码得出，不经过 LLM。"""
    passed: bool = False
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration: float = 0.0

    def feedback(self) -> str:
        """回灌给修复节点的失败反馈。"""
        if self.timed_out:
            return "上一次修复执行超时（超过时间上限）。代码可能存在死循环或阻塞调用。"
        if self.stderr:
            return f"上一次修复执行失败，退出码 {self.exit_code}：\n{self.stderr}"
        return "上一次修复未能通过验证。"


class BugState(BaseModel):
    """贯穿整条流水线的共享状态。

    路由所需的信息全部落在这些**结构化字段**上，而不是去解析 messages 里的自由文本 ——
    这是确定性路由的前提。
    """
    # —— 输入 ——
    code: Annotated[str, keep_last] = ""
    error: Annotated[str, keep_last] = ""

    # —— 分析证据（确定性工具产出，非 LLM）——
    evidence: Annotated[str, keep_last] = ""

    # —— 检测 ——
    bug_report: Annotated[Optional[BugReport], keep_last] = None

    # —— 修复 ——
    fixed_code: Annotated[str, keep_last] = ""
    fix_explanation: Annotated[str, keep_last] = ""

    # —— 验证与重试 ——
    verification: Annotated[Optional[VerifyResult], keep_last] = None
    verify_feedback: Annotated[str, keep_last] = ""
    fix_attempts: Annotated[int, keep_last] = 0

    # —— 报告 ——
    report: Annotated[str, keep_last] = ""

    # —— 运行观测 ——
    llm_calls: Annotated[int, keep_last] = 0
    total_tokens: Annotated[int, keep_last] = 0

    # —— 对话与轨迹（保留给前端展示）——
    messages: Annotated[List[Any], add_messages] = Field(default_factory=list)

    # langgraph 托管的步数护栏：由 scratchpad 每步递减，防止 ReAct/图失控
    remaining_steps: RemainingSteps = 100
