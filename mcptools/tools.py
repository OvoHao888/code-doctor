"""MCP 客户端 —— 接入远程工具服务（Tavily 联网搜索）。

注意：密钥从环境变量读取，不要硬编码在源码里。
原实现在此处直接写了明文 API Key，随仓库一起提交，属于密钥泄漏。
"""

import logging
import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

mcp_tools = []

mcp_client = None
if TAVILY_API_KEY:
    try:
        mcp_client = MultiServerMCPClient(
            {
                "tavily": {
                    "url": os.getenv("TAVILY_MCP_URL", "https://mcp.tavily.com/mcp"),
                    "transport": "http",
                    "headers": {"Authorization": f"Bearer {TAVILY_API_KEY}"},
                }
            }
        )
    except Exception as e:
        logger.error("MCP 客户端初始化失败: %s", e)


async def load_mcp():
    """加载 MCP 工具到模块级 mcp_tools。

    必须在**构建工作流之前**调用 —— 原项目在模块导入时就用 *mcp_tools 解包，
    那时工具还没加载，导致联网能力完全失效。
    """
    if mcp_client is None:
        return "未配置 TAVILY_API_KEY，联网调研已跳过"
    try:
        tools = await mcp_client.get_tools()
        mcp_tools[:] = tools
        return None
    except Exception as e:
        logger.error("MCP 工具加载失败: %s", e)
        return f"MCP 加载失败: {e}"
