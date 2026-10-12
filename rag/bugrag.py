"""FAISS 向量检索。

设计说明：
    原实现在每个请求的**热路径**上调用 add_knowledge_to_faiss 去写向量库
    （db.add_documents + save_local 会重写 index.faiss/index.pkl）。
    多请求并发时这是数据竞争，而且单次请求的噪声会污染整个知识库。
    这里把写入能力保留为**离线批处理**接口，不再挂在请求路径上。
"""

import logging
import os

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

load_dotenv()

# 低于该相似度分数的检索结果直接丢弃（FAISS 的 L2 距离，越小越相似）。
# 实测：相关章节距离约 0.75~0.85，无关章节约 0.95~1.0，0.9 能有效切分。
MAX_DISTANCE = float(os.getenv("RAG_MAX_DISTANCE", "0.9"))

_embedding = None
_db = None
_db_loaded = False


def _get_embedding():
    global _embedding
    if _embedding is None:
        _embedding = OpenAIEmbeddings(
            api_key=os.getenv("SILICON_API_KEY"),
            base_url=os.getenv("SILICON_API_BASE"),
            model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
        )
    return _embedding


def load_db():
    """懒加载向量库。失败返回 None（RAG 是增强项，不该拖垮主流程）。"""
    global _db, _db_loaded
    if _db_loaded:
        return _db
    _db_loaded = True
    try:
        path = os.getenv("KNOWLEDGE_DB_PATH", "rag/faiss").strip('"')
        _db = FAISS.load_local(path, _get_embedding(), allow_dangerous_deserialization=True)
    except Exception as e:
        logger.error("加载知识库失败: %s", e)
        _db = None
    return _db


def make_rag_search():
    """返回一个 (code) -> str 的检索函数；向量库不可用时返回 None。

    消融实验通过"传 None 给 build_workflow"来关闭 RAG。
    """
    db = load_db()
    if db is None:
        return None

    def rag_search(code: str) -> str:
        if not code or not code.strip():
            return ""
        try:
            results = db.similarity_search_with_score(code, k=3)
        except Exception as e:
            logger.error("检索失败: %s", e)
            return ""

        kept = [doc.page_content for doc, score in results if score <= MAX_DISTANCE]
        if not kept:
            return ""
        return "\n---\n".join(kept)

    return rag_search


def add_documents(texts):
    """离线接口：向知识库追加知识并落盘。不在请求热路径上调用。"""
    db = load_db()
    if db is None:
        raise RuntimeError("向量库未加载")
    db.add_documents([Document(page_content=t, metadata={"source": "offline"}) for t in texts])
    db.save_local(os.getenv("KNOWLEDGE_DB_PATH", "rag/faiss").strip('"'))
