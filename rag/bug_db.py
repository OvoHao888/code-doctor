"""离线重建向量库 —— 从知识库文本生成 FAISS 索引。

这是一个**离线脚本**，不在请求热路径上运行：
    python rag/bug_db.py

原版把落盘路径硬编码成 "faiss"，而运行时读取的是 KNOWLEDGE_DB_PATH（默认 "rag/faiss"），
两者对不上，脚本产出的索引根本不会被加载。这里统一走环境变量。
"""

import os
import sys

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

SOURCE_FILE = os.getenv("KNOWLEDGE_SOURCE", "rag/bug_db.txt")
DB_PATH = os.getenv("KNOWLEDGE_DB_PATH", "rag/faiss").strip('"')


def main():
    if not os.path.exists(SOURCE_FILE):
        print(f"知识库源文件不存在: {SOURCE_FILE}")
        return 1

    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    # 按章节切分：知识库每条 Bug 类型是一个独立的 `## ` 小节，
    # 用固定字符数硬切会把一个小节拦腰截断，检索时命中半截内容，区分度很差。
    splitter = RecursiveCharacterTextSplitter(
        separators=["\n## ", "\n---\n", "\n\n"],
        chunk_size=int(os.getenv("CHUNK_SIZE", "900")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "0")),
        keep_separator=True,
    )
    chunks = splitter.split_text(text)
    print(f"已切分 {len(chunks)} 个文本块")

    embedding = OpenAIEmbeddings(
        api_key=os.getenv("SILICON_API_KEY"),
        base_url=os.getenv("SILICON_API_BASE"),
        model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    )

    db = FAISS.from_texts(chunks, embedding)
    db.save_local(DB_PATH)
    print(f"索引已写入: {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
