from fastapi import FastAPI
from pydantic import BaseModel
from graph import workflow
from dotenv import load_dotenv
import os
from fastapi.middleware.cors import CORSMiddleware
from mcptools.tools import load_mcp, mcp_tools
import logging

# 配置日志 - 只显示错误级别以上
logging.basicConfig(level=logging.ERROR, format='%(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Bug检测")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CodeRequest(BaseModel):
    code: str
    error: str = ""

# 启动时加载 MCP 工具
@app.on_event("startup")
async def startup_event():
    try:
        await load_mcp()
        print(f"MCP 工具加载完成: {[tool.name for tool in mcp_tools] if mcp_tools else '无工具'}")
    except Exception as e:
        print(f"MCP 加载失败: {str(e)}")

@app.post("/checkCode")
async def check_code(req: CodeRequest):
    try:
        print("请求收到")

        res = await workflow.ainvoke(
            {
                "code": req.code,
                "messages": [{"role": "user", "content": f"请分析以下代码：\n{req.code}"}],
            }
        )
        messages = res.get('messages', [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, 'content'):
                content = str(last_msg.content)[:500] + "..." if len(str(last_msg.content)) > 500 else str(last_msg.content)
                print(f"│ 最终结果:\n│ {content}")
        return res
    except Exception as e:
        print(f"[error] 执行失败: {str(e)}")
        return {"error": f"检查代码失败: {str(e)}"}

@app.get("/")
async def root():
    return {"message": "Hello World"}