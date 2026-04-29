from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from tools.code_tools import *
from tools.state_tools import reset_workflow, workflow_complete, mark_from_web
from rag.bugrag import rag_search_code_knowledge, add_knowledge_to_faiss
from .state import BugState
from langgraph.checkpoint.memory import InMemorySaver
from mcptools.tools import mcp_tools
import os
import logging

# 降低日志级别到 ERROR
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

load_dotenv()
checkpointer = InMemorySaver()

model = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "deepseek-v3"),
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    temperature=0.1,
    streaming=False,
)

# 负责决策
SupervisorAgent = create_react_agent(
    model=model,
    prompt="""
    你是【代码自动化Bug修复系统】的主管智能体。

    核心职责：
    1. 审核 ReportAgent 生成的修复报告
    2. 知识库管理：
       - 检查 messages 中是否有联网搜索结果（{"is_from_web": true}）
       - 如果有，调用 add_knowledge_to_faiss() 将相关知识添加到知识库
       - 搜索词应包含：Bug类型、修复方法、相关技术点

    工作流程：
    - 先查看 messages 中的内容
    - 识别包含 "is_from_web" 或 "mark_from_web" 的记录
    - 提取其中的技术知识
    - 调用 add_knowledge_to_faiss() 添加到知识库

    注意：
    - 工作流已经完成，不需要调用 workflow_complete()
    - 只负责知识库管理，其他事情已经处理好了
    """,
    tools=[add_knowledge_to_faiss],
    state_schema=BugState,
    checkpointer=checkpointer,
)


# 负责解析代码
CodeParserAgent = create_react_agent(
    model=model,
    prompt="""
    你是【代码解析专家】。
    任务：解析用户代码并返回解析结果。

    步骤：
    1. 读取 state.code 字段
    2. 分析代码结构、函数定义、变量、逻辑流程
    3. 生成详细的解析结果并添加到 messages 中

    重要：
    - 专注于代码结构分析
    - 当代码中存在错误时，要在 messages 中详细说明
    """,
    tools=[extract_code_structure,
         extract_code_logic_flow,
         split_long_code
    ],
    state_schema=BugState,
    checkpointer=checkpointer,
)


# 负责检查代码错误
BugCheckerAgent = create_react_agent(
    model=model,
    prompt="""
    你是【高级代码Bug检测专家】。
    任务：检测代码bug并返回检测结果。

    步骤：
    1. 分析 state.code 中的代码
    2. 查找语法错误、逻辑错误等问题
    3. 将检测结果添加到 messages 中

    重要：
    - 当发现错误时，要在 messages 中详细说明
    - 如果调用到 mcp_tools 中的联网搜索工具，要调用 mark_from_web() 标记
    """,
    tools=[rag_search_code_knowledge,
        find_syntax_error,
        find_logic_error,
        find_other_error,
        analyze_bug_root_cause,
        mark_from_web,
        *mcp_tools
    ],
    state_schema=BugState,
    checkpointer=checkpointer,
)


# 负责修改代码
FixAgent = create_react_agent(
    model=model,
    prompt="""
    你是【代码Bug修复专家】。
    任务：修复代码bug并返回修复结果。

    步骤：
    1. 分析 state.code 和 messages 中的bug信息
    2. 生成修复代码，特别注意修复除零错误
    3. 将修复结果添加到 messages 中

    重要：
    - 当修复错误时，要在 messages 中详细说明修复方法
    - 如果调用到 mcp_tools 中的联网搜索工具，要调用 mark_from_web() 标记
    """,
    tools=[generate_fix_code,
        validate_fix_is_correct,
        mark_from_web,
        *mcp_tools
    ],
    state_schema=BugState,
    checkpointer=checkpointer,
)


# 负责报告代码错误
ReportAgent = create_react_agent(
    model=model,
    prompt="""
    你是【自动化报告生成专家】。
    任务：生成bug修复报告并返回报告结果。

    步骤：
    1. 分析 state.code 和 messages 中的信息
    2. 生成结构化报告并添加到 messages 中

    重要：
    - 报告要包含：问题描述、修复方案、修复后的代码
    - 当报告错误时，要在 messages 中详细说明错误信息
    """,
    tools=[generate_bug_report,
        summary_bug_info,
        format_output_to_json
    ],
    state_schema=BugState,
    checkpointer=checkpointer,
)