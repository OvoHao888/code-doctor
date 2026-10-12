"""路由函数单测 —— 纯函数，无需 LLM，可完全确定性验证。

这是条件路由相比"让 LLM 决定下一步"的核心优势：分支逻辑可以被穷举测试。
"""

from graph.routing import MAX_FIX_ATTEMPTS, route_after_check, route_after_verify
from graph.state import BugReport, BugItem, BugState, VerifyResult


def _state(**kw) -> BugState:
    return BugState(**kw)


class TestRouteAfterCheck:
    def test_有bug_进入修复(self):
        st = _state(bug_report=BugReport(has_bug=True, bugs=[BugItem(line=1, type="除零", severity="high", description="x")]))
        assert route_after_check(st) == "fix"

    def test_无bug_直接出报告(self):
        st = _state(bug_report=BugReport(has_bug=False, bugs=[]))
        assert route_after_check(st) == "report"

    def test_检测节点无结论_不进入修复(self):
        """检测失败时不应误入修复分支（没有明确目标可修）。"""
        assert route_after_check(_state(bug_report=None)) == "report"


class TestRouteAfterVerify:
    def test_验证通过_出报告(self):
        st = _state(verification=VerifyResult(passed=True, exit_code=0))
        assert route_after_verify(st) == "report"

    def test_验证失败且未超限_回到修复(self):
        st = _state(verification=VerifyResult(passed=False, exit_code=1, stderr="boom"), fix_attempts=1)
        assert st.fix_attempts < MAX_FIX_ATTEMPTS
        assert route_after_verify(st) == "fix"

    def test_验证失败且已达上限_出报告(self):
        """必须有上界 —— 否则失败样本会无限回环烧 token。"""
        st = _state(verification=VerifyResult(passed=False, exit_code=1), fix_attempts=MAX_FIX_ATTEMPTS)
        assert route_after_verify(st) == "report"

    def test_超限一再多一步也出报告(self):
        st = _state(verification=VerifyResult(passed=False), fix_attempts=MAX_FIX_ATTEMPTS + 5)
        assert route_after_verify(st) == "report"

    def test_没有验证结果_视为未通过(self):
        st = _state(verification=None, fix_attempts=0)
        assert route_after_verify(st) == "fix"


class TestLoopTermination:
    def test_无论多少轮_最终必然出报告(self):
        """回环的有界性：从任意状态出发，验证失败时最多再修 MAX_FIX_ATTEMPTS 次。"""
        attempts = 0
        st = _state(verification=VerifyResult(passed=False, stderr="always fails"), fix_attempts=0)
        while route_after_verify(st) == "fix":
            attempts += 1
            st = _state(
                verification=VerifyResult(passed=False, stderr="always fails"),
                fix_attempts=st.fix_attempts + 1,
            )
            assert attempts <= MAX_FIX_ATTEMPTS, "回环未收敛"
        assert attempts == MAX_FIX_ATTEMPTS
