from langgraph.graph import StateGraph, START, END
from .state import BugState
from .agents import SupervisorAgent, CodeParserAgent, BugCheckerAgent, ReportAgent, FixAgent

def log_progress(name):
    print(f"⚪正在执行: {name}")

def wrap_agent(agent, name):
    def wrapped(state: BugState) -> BugState:
        log_progress(name)
        return agent.invoke(state)
    return wrapped

builder = StateGraph(BugState)

builder.add_node("codeparser", wrap_agent(CodeParserAgent, "代码解析"))
builder.add_node("bugchecker", wrap_agent(BugCheckerAgent, "Bug检测"))
builder.add_node("fix", wrap_agent(FixAgent, "代码修复"))
builder.add_node("report", wrap_agent(ReportAgent, "生成报告"))
builder.add_node("supervisor", wrap_agent(SupervisorAgent, "知识库管理"))

builder.set_entry_point("codeparser")

builder.add_edge("codeparser", "bugchecker")
builder.add_edge("bugchecker", "fix")
builder.add_edge("fix", "report")
builder.add_edge("report", "supervisor")
builder.add_edge("supervisor", END)

workflow = builder.compile()