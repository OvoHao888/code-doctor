from langchain_mcp_adapters.client import MultiServerMCPClient
import asyncio
from langchain_mcp_adapters.tools import load_mcp_tools
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# 降低日志级别到 ERROR
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

try:
    mcp_client = MultiServerMCPClient({
        "tavily": {
            "url": "https://mcp.tavily.com/mcp",
            "transport": "http",
            "headers": {
                "Authorization": "Bearer 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"
            }
        }
    })
except Exception as e:
    logger.error(f"MCP 客户端初始化失败: {str(e)}")
    mcp_client = None

mcp_tools = []

async def load_mcp():
    global mcp_tools
    try:
        tools = await mcp_client.get_tools()
        mcp_tools[:] = tools
        return None
    except Exception as e:
        logger.error(f"MCP 工具加载失败: {str(e)}")
        return f"MCP 加载失败: {str(e)}"