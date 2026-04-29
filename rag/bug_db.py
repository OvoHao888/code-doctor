import os
import numpy as np
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

# 加载配置
load_dotenv()

# 读取知识库
with open("bug_db.txt", "r", encoding="utf-8") as f:
    text = f.read()

# 切分文本
text_splitter = CharacterTextSplitter(
    chunk_size=int(os.getenv("CHUNK_SIZE")),
    chunk_overlap=int(os.getenv("CHUNK_OVERLAP"))
)
# 文段列表
texts = text_splitter.split_text(text)
# 初始化本地嵌入
embedding = OpenAIEmbeddings(
    api_key=os.getenv("SILICON_API_KEY"),
    base_url=os.getenv("SILICON_API_BASE"),
    model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
)

# 构建向量库
db = FAISS.from_texts(texts, embedding)
db.save_local("faiss")
