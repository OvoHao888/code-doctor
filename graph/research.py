"""联网调研节点（MCP）—— 只在本地分析拿不准时升级到联网检索。

设计说明：
    原项目的 MCP 是**完全失效**的：agents.py 里 `tools=[..., *mcp_tools]` 在模块导入时
    解包，而那时 mcp_tools 还是空列表（真正的 load_mcp() 发生在 FastAPI startup）。
    结果所有 tavily 工具从未绑定到任何 agent。

    这里改成正确的做法：MCP 工具在 startup 时加载，然后作为参数注入节点。
    并且它不再是"每个请求都跑"的装饰品，而是**不确定性驱动的升级路径**：
    只有当检测置信度低于阈值时才发起联网检索，把结果并入证据。
    这样既保留了 MCP 能力，又不给常见路径增加延迟。
"""

import os

from langchain_core.messages import AIMessage

# 检测置信度低于该阈值时才触发联网调研
CONFIDENCE_THRESHOLD = float(os.getenv("MCP_CONFIDENCE_THRESHOLD", "0.7"))
# 检索结果并入证据时的截断长度
MAX_RESEARCH_CHARS = 2000


def make_research_node(search_tool=None):
    """search_tool: 一个 MCP 检索工具（如 tavily_search）。为 None 时本节点直接跳过。

    `search_tool` 在构建工作流时注入 —— 这正是原项目踩坑的地方：工具必须在
    load_mcp() 之后才可用，不能在模块导入时解包。
    """

    async def research(state) -> dict:
        if search_tool is None:
            return {}

        report = state.bug_report
        if report is None or not report.bugs:
            return {}

        if report.confidence >= CONFIDENCE_THRESHOLD:
            return {}

        bug_types = "、".join(sorted({b.type for b in report.bugs}))
        error_hint = state.error.strip().splitlines()[-1] if state.error.strip() else ""
        query = f"Python {bug_types} 报错 {error_hint} 修复方法".strip()

        try:
            retrieved = await search_tool.ainvoke({"query": query})
        except Exception as e:
            return {"messages": [AIMessage(content=f"【联网调研】检索失败（不影响主流程）：{e}")]}

        text = str(retrieved)[:MAX_RESEARCH_CHARS]
        return {
            "evidence": (state.evidence or "") + f"\n\n[联网调研 · {bug_types}]\n{text}",
            "messages": [
                AIMessage(content=f"【联网调研】检测置信度 {report.confidence} 低于阈值，已联网检索「{bug_types}」")
            ],
        }

    return research
