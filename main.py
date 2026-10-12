import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent

from graph import build_workflow
from mcptools.tools import load_mcp, mcp_tools
from rag.bugrag import make_rag_search

load_dotenv()

logging.basicConfig(level=logging.ERROR, format="%(message)s")
logger = logging.getLogger(__name__)

model = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "deepseek-v4.1-flash"),
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    temperature=0,
)

# 默认关闭。消融实验（见 README）未能在 n=27 上证明 RAG 带来收益，
# 而它确定性地增加延迟与 token 消耗。开启：RAG_ENABLED=1
RAG_ENABLED = os.getenv("RAG_ENABLED", "0") == "1"


def _pick_search_tool():
    """从 MCP 工具里挑出联网检索工具。"""
    for t in mcp_tools:
        if "search" in t.name:
            return t
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MCP 工具必须在**构建工作流之前**加载完成。
    # 原实现在模块导入时就用 *mcp_tools 解包（那时还是空列表），导致联网能力形同虚设。
    search_tool = None
    try:
        await load_mcp()
        search_tool = _pick_search_tool()
    except Exception as e:
        logger.error("MCP 加载失败，联网调研将关闭: %s", e)

    rag_search = make_rag_search() if RAG_ENABLED else None

    app.state.workflow = build_workflow(model, rag_search=rag_search, search_tool=search_tool)

    print(f"模型: {model.model_name}")
    print(f"RAG: {'已启用' if rag_search else '未启用'}")
    print(f"联网调研(MCP): {search_tool.name if search_tool else '未启用'}")
    yield


app = FastAPI(title="Code Doctor", description="自纠错的多智能体代码修复系统", lifespan=lifespan)

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


@app.post("/checkCode")
async def check_code(req: CodeRequest, request: Request):
    started = time.time()
    try:
        result = await request.app.state.workflow.ainvoke(
            {
                "code": req.code,
                "error": req.error,
                "messages": [{"role": "user", "content": req.code}],
            },
            config={"recursion_limit": 25},
        )
    except Exception as e:
        logger.exception("执行失败")
        return {"error": f"检查代码失败: {e}"}

    report = result.get("bug_report")
    verification = result.get("verification")

    return {
        "report": result.get("report", ""),
        "has_bug": bool(report.has_bug) if report else False,
        "bugs": [b.model_dump() for b in report.bugs] if report else [],
        "confidence": report.confidence if report else None,
        "fixed_code": result.get("fixed_code", ""),
        "fix_explanation": result.get("fix_explanation", ""),
        "fix_attempts": result.get("fix_attempts", 0),
        "evidence": result.get("evidence", ""),
        "verification": verification.model_dump() if verification else None,
        "stats": {
            "llm_calls": result.get("llm_calls", 0),
            "total_tokens": result.get("total_tokens", 0),
            "duration": round(time.time() - started, 2),
        },
        "messages": [
            {"content": m.content} if hasattr(m, "content") else {"content": str(m)}
            for m in result.get("messages", [])
        ],
    }


@app.get("/")
async def root():
    """直接返回前端页面 —— 前后端同一个地址，启动后浏览器开一个 URL 即可。"""
    return FileResponse(BASE_DIR / "frontend.html")


@app.get("/favicon.ico")
async def favicon():
    """前端里的 <img src="favicon.ico"> 走的是相对路径，
    页面由后端提供时必须一并提供静态资源，否则 Logo 会变成破图。"""
    return FileResponse(BASE_DIR / "favicon.ico")


@app.get("/health")
async def health():
    return {"message": "Code Doctor is running"}
