"""LangGraph 拓扑 —— 带条件路由的自纠错闭环。

    START → analyze → check ─┬─(has_bug=False)──────────────────→ report → END
                             └─(has_bug=True) → fix → verify ─┬─(通过) → report
                                                             └─(失败且未超限) → fix
                                                                （带执行反馈回到修复）

对比原版：原版是 codeparser → bugchecker → fix → report → supervisor 的五节点**直线**，
没有任何条件边，"Supervisor"这个名字暗示的动态路由从未实现。这里把它做成了真的。
"""

from langgraph.graph import StateGraph, START, END

from .state import BugState
from .analysis import make_analyze_node
from .llm_nodes import make_check_node, make_fix_node, make_report_node
from .verify import make_verify_node
from .research import make_research_node
from .routing import route_after_check, route_after_verify


def build_workflow(model, rag_search=None, search_tool=None):
    """构造工作流。

    model:       一个 ChatOpenAI 实例
    rag_search:  可选的 (code) -> str 检索函数。传 None 即关闭 RAG（消融实验用）。
    search_tool: 可选的 MCP 检索工具。传 None 即关闭联网调研。

    注意：search_tool 必须由调用方在 load_mcp() **之后**取得再传入 ——
    这正是原项目出错的地方（在模块导入时解包，那时工具还没加载）。
    """
    builder = StateGraph(BugState)

    builder.add_node("analyze", make_analyze_node(rag_search))
    builder.add_node("check", make_check_node(model))
    builder.add_node("research", make_research_node(search_tool))
    builder.add_node("fix", make_fix_node(model))
    builder.add_node("verify", make_verify_node())
    builder.add_node("report", make_report_node(model))

    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "check")
    builder.add_edge("check", "research")

    builder.add_conditional_edges(
        "research",
        route_after_check,
        {"fix": "fix", "report": "report"},
    )

    builder.add_edge("fix", "verify")
    builder.add_conditional_edges(
        "verify",
        route_after_verify,
        {"fix": "fix", "report": "report"},
    )

    builder.add_edge("report", END)

    return builder.compile()
