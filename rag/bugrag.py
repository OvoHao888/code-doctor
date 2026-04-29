import numpy as np
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS
from langchain_core.tools import tool
import os
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import logging

# 降低日志级别到 ERROR
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

load_dotenv()

try:
    embedding = OpenAIEmbeddings(
        api_key=os.getenv("SILICON_API_KEY"),
        base_url=os.getenv("SILICON_API_BASE"),
        model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    )
except Exception as e:
    logger.error(f"Embedding 初始化失败: {str(e)}")
    embedding = None

def load_db():
    try:
        db_path = os.getenv("KNOWLEDGE_DB_PATH", "rag/faiss")
        db = FAISS.load_local(db_path, embedding, allow_dangerous_deserialization=True)
        return db
    except Exception as e:
        logger.error(f"加载知识库时发生异常: {str(e)}")
        return None

db = load_db()

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=80
)

@tool
def add_knowledge_to_faiss(knowledge: str):
    """
    将知识添加到FAISS向量数据库
    参数：
    knowledge:知识字符串
    """
    global db
    if not db:
        return "向量库未加载"
    if not knowledge or not knowledge.strip():
        return "请输入有效知识字符串"

    try:
        doc = Document(
            page_content=knowledge,
            metadata={"source": "new_knowledge"}
        )
        docs_to_index = text_splitter.split_documents([doc])
        db.add_documents(docs_to_index)
        db.save_local(os.getenv("KNOWLEDGE_DB_PATH", "rag/faiss"))
        return "已入库"
    except Exception as e:
        logger.error(f"add_knowledge_to_faiss 异常: {str(e)}")
        return f"添加知识失败: {str(e)}"

@tool
def rag_search_code_knowledge(code: str)-> str:
    """
    从向量库中查询代码知识
    参数：
    code:代码字符串
    返回：
    knowledge:查询结果字符串
    """
    if not db:
        return "向量库未加载"
    if not code or not code.strip():
        return "请输入有效代码或错误信息"
    try:
        query = embedding.embed_query(code)
        results = db.similarity_search_by_vector(query, k=3)
        knowledge = "\n".join([doc.page_content for doc in results])
        if not knowledge:
            return "未找到相关知识"
        else:
            return knowledge
    except Exception as e:
        logger.error(f"rag_search_code_knowledge 异常: {str(e)}")
        return f"查询失败: {str(e)}"