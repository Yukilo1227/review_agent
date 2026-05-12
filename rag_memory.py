import os
import pickle
from typing import List
from langchain_community.embeddings import DashScopeEmbeddings
# from langchain_community.vectorstores import Chroma  # 注释掉
from langchain_community.vectorstores import FAISS  # 新增
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.documents import Document
from datetime import datetime

class RAGWithMemory:
    def __init__(self, persist_dir="./report_knowledge"):
        # 1. 初始化嵌入模型
        self.embedding = DashScopeEmbeddings(
            model="text-embedding-v3",
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")
        )
        self.persist_dir = persist_dir
        self.vector_store = None
        # 2. 尝试从磁盘加载已有的 FAISS 索引
        if os.path.exists(self.persist_dir) and os.listdir(self.persist_dir):
            try:
                # 如果索引存在，就加载进来
                self.vector_store = FAISS.load_local(self.persist_dir, self.embedding, allow_dangerous_deserialization=True)
            except Exception:
                self.vector_store = None
        # 3. 如果加载失败或没有索引，就创建一个新的
        if self.vector_store is None:
            self.vector_store = FAISS.from_texts(["Initialization text"], self.embedding)

        self.checkpointer = InMemorySaver()

    def add_report(self, report_text: str, metadata: dict):
        content = report_text[:800] if len(report_text) > 800 else report_text
        doc = Document(
            page_content=content,
            metadata={
                "timestamp": datetime.now().isoformat(),
                "query": metadata.get("query", ""),
                "thread_id": metadata.get("thread_id", ""),
                **metadata
            }
        )
        # 注意：FAISS 的 add_documents 方法需要传入文档列表
        self.vector_store.add_documents([doc])
        # 保存到磁盘
        self.vector_store.save_local(self.persist_dir)

    def search_similar(self, query: str, k: int = 2) -> List[str]:
        if not self.vector_store:
            return []
        docs = self.vector_store.similarity_search(query, k=k)
        return [doc.page_content for doc in docs]