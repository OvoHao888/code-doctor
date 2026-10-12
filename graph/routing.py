"""路由函数 —— 纯函数，不调用 LLM。

设计说明：
    路由决策完全基于 state 上的**结构化字段**，不去解析 messages 里的自由文本。
    "能用代码判断的，绝不交给 LLM" —— 这样路由是确定性、可复现、可单测的，
    也不额外消耗 token。
"""

import os

# 修复尝试次数上限。达到上限后即使验证仍未通过，也出报告（并如实标记失败），
# 避免无限回环烧 token。
MAX_FIX_ATTEMPTS = int(os.getenv("MAX_FIX_ATTEMPTS", "3"))


def route_after_check(state) -> str:
    """检测之后：有问题就修，没问题直接出报告。"""
    report = state.bug_report
    if report is None:
        # 检测节点未能产出结论，不进入修复，直接出报告
        return "report"
    return "fix" if report.has_bug else "report"


def route_after_verify(state) -> str:
    """验证之后：通过就出报告；失败且还有重试额度就带着反馈回到修复。"""
    verification = state.verification
    if verification is not None and verification.passed:
        return "report"
    if state.fix_attempts >= MAX_FIX_ATTEMPTS:
        return "report"
    return "fix"
