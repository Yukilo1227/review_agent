<<<<<<< HEAD
"""
agent.py - 产品评测 Agent 核心模块
功能：联网搜索、RAG记忆、短期记忆（checkpointer）、流式输出
"""
import os
import json
import re
from typing import List, Dict, Any, Generator
from datetime import datetime
from dotenv import load_dotenv
from tavily import TavilyClient
import pandas as pd
import matplotlib.pyplot as plt
from langchain_community.chat_models import ChatTongyi
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.documents import Document
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import FAISS
# 加载环境变量
load_dotenv()

# ==================== 配置 ====================
MODEL_NAME = "qwen3-max-2026-01-23"  # 保留你指定的模型名
TEMPERATURE = 0.3
RAG_PERSIST_DIR = "./report_knowledge"
SEARCH_MAX_RESULTS = 3
SEARCH_TIME_RANGE = "year"  # 近一年数据

# ==================== 初始化客户端 ====================
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# ==================== 工具定义 ====================
@tool
def search_web(query: str) -> str:
    """在互联网上搜索指定产品的真实评测信息。"""
    try:
        result = tavily.search(
            query,
            search_depth="advanced",
            max_results=SEARCH_MAX_RESULTS,
            time_range=SEARCH_TIME_RANGE
        )
        if result and 'results' in result:
            formatted = []
            for r in result['results'][:3]:
                formatted.append(
                    f"标题: {r.get('title', '无标题')}\n"
                    f"内容摘要: {r.get('content', '无内容')[:500]}\n"
                )
            return "\n".join(formatted) if formatted else f"未找到关于 '{query}' 的相关信息。"
        return f"未找到关于 '{query}' 的相关信息。"
    except Exception as e:
        return f"搜索失败: {str(e)}"

# ==================== RAG + 短期记忆（FAISS + InMemorySaver）====================
class RAGWithMemory:
    """向量检索 + 短期记忆管理"""
    def __init__(self, persist_dir: str = RAG_PERSIST_DIR):
        self.persist_dir = persist_dir
        self.embedding = DashScopeEmbeddings(
            model="text-embedding-v3",
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")
        )
        self.vector_store = self._load_or_create_vector_store()
        self.checkpointer = InMemorySaver()

    def _load_or_create_vector_store(self):
        if os.path.exists(self.persist_dir) and os.listdir(self.persist_dir):
            try:
                return FAISS.load_local(
                    self.persist_dir,
                    self.embedding,
                    allow_dangerous_deserialization=True
                )
            except Exception:
                pass
        return FAISS.from_texts(["初始化占位文本"], self.embedding)

    def add_report(self, report_text: str, metadata: dict):
        """添加报告到向量库（自动截取前800字符）"""
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
        self.vector_store.add_documents([doc])
        self.vector_store.save_local(self.persist_dir)
        print(f"[RAG] 已存储报告: {metadata.get('query', '')[:50]}")

    def search_similar(self, query: str, k: int = 2) -> List[str]:
        """检索相似历史报告，返回片段列表"""
        if self.vector_store is None:
            return []
        try:
            docs = self.vector_store.similarity_search(query, k=k)
            return [doc.page_content for doc in docs]
        except Exception as e:
            print(f"[RAG] 检索失败: {e}")
            return []

# ==================== 初始化 RAG ====================
rag_mem = RAGWithMemory(persist_dir=RAG_PERSIST_DIR)

# ==================== 模型 ====================
model = ChatTongyi(
    model=MODEL_NAME,
    temperature=TEMPERATURE,
    streaming=True
)

# ==================== Agent 创建（静态 system_prompt，不含 RAG 上下文）====================
agent = create_agent(
    model=model,
    tools=[search_web],
    checkpointer=rag_mem.checkpointer,
    system_prompt="""你是一个专业的产品评测报告生成Agent。你的输出必须是**经过你自己归纳总结后的最终报告**，禁止输出任何搜索工具返回的原始段落、标题或列表。

【铁律】
- 不要输出任何以“标题:”、“内容摘要:”、“适合你如果：”等开头的原始搜索结果。
- 不要输出网页 URL、价格表、评分星星（⭐⭐）等格式。
- 不要输出“发生错误”之类的调试信息。

【必须做的事】
1. 调用 search_web 搜索后，**你自己阅读**搜索结果，提取关键信息。
2. 用你自己的语言，写出以下板块：
   ## 产品概述
   ## 推荐型号（列出2-3款，用Markdown表格展示，表格列名：产品名称、综合评分、价格、核心优点）
   ## 关键参数对比（续航、降噪、连接等，可用列表）
   ## 价格参考
   ## 购买建议

请立即输出最终报告（不要输出任何其他文字）。"""
)

# ==================== 流式生成函数（集成 RAG + 动态 prompt）====================
def get_product_review_streaming(
    user_query: str,
    thread_id: str = "default_session"
) -> Generator[str, None, None]:
    """
    流式生成产品评测报告
    - 自动检索相似历史报告（RAG）
    - 动态构造 system_prompt 注入检索内容
    - 通过 checkpointer 保持同一 thread_id 的短期记忆
    """
    try:
        # 1. RAG 检索相似报告
        similar_reports = rag_mem.search_similar(user_query, k=2)
        context = ""
        if similar_reports:
            context = "【以下是从历史评测报告中检索到的相关参考信息，仅作为内部参考，不要直接复制】\n\n"
            for idx, snippet in enumerate(similar_reports, 1):
                context += f"参考{idx}:\n{snippet}\n\n"
            context += "---\n\n"
            print(f"[RAG] 检索到 {len(similar_reports)} 条相似报告")

        # 2. 动态 system_prompt（注入 context）
        dynamic_system_prompt = f"""你是一个专业的产品评测报告生成Agent。请直接输出最终评测报告，不要输出任何无关的解释、思考过程或工具调用说明。

{context}

【严格禁止】
- 不要输出“好的”、“现在”、“首先”、“接下来”、“基于搜索结果”、“根据我的知识”等引导词。
- 不要输出“用户问的是...”、“我需要...”、“让我分析”等元描述。
- 不要输出“Thought:”、“Action:”、“Observation:”等推理步骤。
- 绝对不要直接复制粘贴网上的评测原文或大段摘要。你必须用自己的语言对信息进行归纳、总结和重组。

【工作流程（内部执行，不要输出）】
1. 使用 search_web 工具搜索用户指定的产品信息（尽量获取近两年数据）。
2. 结合搜索结果，用自己的话提炼关键点，生成 Markdown 格式的评测报告。
3. 报告必须包含：## 产品概述、## 核心参数对比（可用表格）、## 用户口碑（优点/缺点）、## 价格参考、## 购买建议。
4. 如果信息不足，只写“信息不足”，不要解释原因。
5. 在报告末尾，用 Markdown 表格格式给出推荐的几款产品的对比评分，格式如下：
   | 产品名称 | 综合评分（满分100） |
   |----------|------------------|
   | 产品A    | 90               |
   | 产品B    | 85               |
- 不要自己编造评分，根据搜索结果合理估算。

请严格按照以上要求直接输出最终报告。"""

        # 3. 配置短期记忆（thread_id）
        config = {"configurable": {"thread_id": thread_id}}

        full_content = ""
        # 4. 流式调用
        for chunk in agent.stream(
            {"messages": [("system", dynamic_system_prompt), ("user", user_query)]},
            config=config,
            stream_mode="messages"
        ):
            # 解析消息块
            if isinstance(chunk, tuple) and len(chunk) == 2:
                msg, _ = chunk
            else:
                msg = chunk

            if hasattr(msg, 'content') and msg.content:
                content = msg.content
                # 过滤废话前缀（流式块级别过滤）
                skip_prefixes = ("好的", "现在", "首先", "接下来", "基于", "根据",
                                 "用户问", "我需要", "让我", "Thought", "Action", "Observation")
                if content.strip().startswith(skip_prefixes):
                    continue
                # 只输出 AI 最终回复（非工具调用）
                if not hasattr(msg, 'tool_calls') or not msg.tool_calls:
                    # 过滤明显是搜索原文的块
                    if any(x in content for x in ["标题:", "内容摘要:", "适合你如果",
                                                   "实测评分", "价格表", "发生错误"]):
                        continue
                    full_content += content
                    yield content

        # 5. 可选：将生成的完整报告存入 RAG（需手动开启）
        # 注意：由于流式输出已经 yield 给前端，这里完整报告已收集在 full_content 中
        # 你可以根据需要取消下面注释
        # if full_content.strip():
        #     rag_mem.add_report(full_content, metadata={"query": user_query, "thread_id": thread_id})

    except Exception as e:
        yield f"发生错误: {str(e)}"

# ==================== 测试入口 ====================
if __name__ == "__main__":
    test_query = "我想买一款1000元以内的洗碗机，帮我做一下产品评测和推荐"
    print("正在生成报告...")
    for chunk in get_product_review_streaming(test_query, thread_id="test_session_001"):
        print(chunk, end="", flush=True)
=======
"""
agent.py - 产品评测 Agent 核心模块
功能：联网搜索、RAG记忆、短期记忆（checkpointer）、流式输出
"""
import os
import json
import re
from typing import List, Dict, Any, Generator
from datetime import datetime
from dotenv import load_dotenv
from tavily import TavilyClient
import pandas as pd
import matplotlib.pyplot as plt
from langchain_community.chat_models import ChatTongyi
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.documents import Document
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import FAISS
# 加载环境变量
load_dotenv()

# ==================== 配置 ====================
MODEL_NAME = "qwen3-max-2026-01-23"  # 保留你指定的模型名
TEMPERATURE = 0.3
RAG_PERSIST_DIR = "./report_knowledge"
SEARCH_MAX_RESULTS = 3
SEARCH_TIME_RANGE = "year"  # 近一年数据

# ==================== 初始化客户端 ====================
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# ==================== 工具定义 ====================
@tool
def search_web(query: str) -> str:
    """在互联网上搜索指定产品的真实评测信息。"""
    try:
        result = tavily.search(
            query,
            search_depth="advanced",
            max_results=SEARCH_MAX_RESULTS,
            time_range=SEARCH_TIME_RANGE
        )
        if result and 'results' in result:
            formatted = []
            for r in result['results'][:3]:
                formatted.append(
                    f"标题: {r.get('title', '无标题')}\n"
                    f"内容摘要: {r.get('content', '无内容')[:500]}\n"
                )
            return "\n".join(formatted) if formatted else f"未找到关于 '{query}' 的相关信息。"
        return f"未找到关于 '{query}' 的相关信息。"
    except Exception as e:
        return f"搜索失败: {str(e)}"

# ==================== RAG + 短期记忆（FAISS + InMemorySaver）====================
class RAGWithMemory:
    """向量检索 + 短期记忆管理"""
    def __init__(self, persist_dir: str = RAG_PERSIST_DIR):
        self.persist_dir = persist_dir
        self.embedding = DashScopeEmbeddings(
            model="text-embedding-v3",
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")
        )
        self.vector_store = self._load_or_create_vector_store()
        self.checkpointer = InMemorySaver()

    def _load_or_create_vector_store(self):
        if os.path.exists(self.persist_dir) and os.listdir(self.persist_dir):
            try:
                return FAISS.load_local(
                    self.persist_dir,
                    self.embedding,
                    allow_dangerous_deserialization=True
                )
            except Exception:
                pass
        return FAISS.from_texts(["初始化占位文本"], self.embedding)

    def add_report(self, report_text: str, metadata: dict):
        """添加报告到向量库（自动截取前800字符）"""
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
        self.vector_store.add_documents([doc])
        self.vector_store.save_local(self.persist_dir)
        print(f"[RAG] 已存储报告: {metadata.get('query', '')[:50]}")

    def search_similar(self, query: str, k: int = 2) -> List[str]:
        """检索相似历史报告，返回片段列表"""
        if self.vector_store is None:
            return []
        try:
            docs = self.vector_store.similarity_search(query, k=k)
            return [doc.page_content for doc in docs]
        except Exception as e:
            print(f"[RAG] 检索失败: {e}")
            return []

# ==================== 初始化 RAG ====================
rag_mem = RAGWithMemory(persist_dir=RAG_PERSIST_DIR)

# ==================== 模型 ====================
model = ChatTongyi(
    model=MODEL_NAME,
    temperature=TEMPERATURE,
    streaming=True
)

# ==================== Agent 创建（静态 system_prompt，不含 RAG 上下文）====================
agent = create_agent(
    model=model,
    tools=[search_web],
    checkpointer=rag_mem.checkpointer,
    system_prompt="""你是一个专业的产品评测报告生成Agent。你的输出必须是**经过你自己归纳总结后的最终报告**，禁止输出任何搜索工具返回的原始段落、标题或列表。

【铁律】
- 不要输出任何以“标题:”、“内容摘要:”、“适合你如果：”等开头的原始搜索结果。
- 不要输出网页 URL、价格表、评分星星（⭐⭐）等格式。
- 不要输出“发生错误”之类的调试信息。

【必须做的事】
1. 调用 search_web 搜索后，**你自己阅读**搜索结果，提取关键信息。
2. 用你自己的语言，写出以下板块：
   ## 产品概述
   ## 推荐型号（列出2-3款，用Markdown表格展示，表格列名：产品名称、综合评分、价格、核心优点）
   ## 关键参数对比（续航、降噪、连接等，可用列表）
   ## 价格参考
   ## 购买建议

请立即输出最终报告（不要输出任何其他文字）。"""
)

# ==================== 流式生成函数（集成 RAG + 动态 prompt）====================
def get_product_review_streaming(
    user_query: str,
    thread_id: str = "default_session"
) -> Generator[str, None, None]:
    """
    流式生成产品评测报告
    - 自动检索相似历史报告（RAG）
    - 动态构造 system_prompt 注入检索内容
    - 通过 checkpointer 保持同一 thread_id 的短期记忆
    """
    try:
        # 1. RAG 检索相似报告
        similar_reports = rag_mem.search_similar(user_query, k=2)
        context = ""
        if similar_reports:
            context = "【以下是从历史评测报告中检索到的相关参考信息，仅作为内部参考，不要直接复制】\n\n"
            for idx, snippet in enumerate(similar_reports, 1):
                context += f"参考{idx}:\n{snippet}\n\n"
            context += "---\n\n"
            print(f"[RAG] 检索到 {len(similar_reports)} 条相似报告")

        # 2. 动态 system_prompt（注入 context）
        dynamic_system_prompt = f"""你是一个专业的产品评测报告生成Agent。请直接输出最终评测报告，不要输出任何无关的解释、思考过程或工具调用说明。

{context}

【严格禁止】
- 不要输出“好的”、“现在”、“首先”、“接下来”、“基于搜索结果”、“根据我的知识”等引导词。
- 不要输出“用户问的是...”、“我需要...”、“让我分析”等元描述。
- 不要输出“Thought:”、“Action:”、“Observation:”等推理步骤。
- 绝对不要直接复制粘贴网上的评测原文或大段摘要。你必须用自己的语言对信息进行归纳、总结和重组。

【工作流程（内部执行，不要输出）】
1. 使用 search_web 工具搜索用户指定的产品信息（尽量获取近两年数据）。
2. 结合搜索结果，用自己的话提炼关键点，生成 Markdown 格式的评测报告。
3. 报告必须包含：## 产品概述、## 核心参数对比（可用表格）、## 用户口碑（优点/缺点）、## 价格参考、## 购买建议。
4. 如果信息不足，只写“信息不足”，不要解释原因。
5. 在报告末尾，用 Markdown 表格格式给出推荐的几款产品的对比评分，格式如下：
   | 产品名称 | 综合评分（满分100） |
   |----------|------------------|
   | 产品A    | 90               |
   | 产品B    | 85               |
- 不要自己编造评分，根据搜索结果合理估算。

请严格按照以上要求直接输出最终报告。"""

        # 3. 配置短期记忆（thread_id）
        config = {"configurable": {"thread_id": thread_id}}

        full_content = ""
        # 4. 流式调用
        for chunk in agent.stream(
            {"messages": [("system", dynamic_system_prompt), ("user", user_query)]},
            config=config,
            stream_mode="messages"
        ):
            # 解析消息块
            if isinstance(chunk, tuple) and len(chunk) == 2:
                msg, _ = chunk
            else:
                msg = chunk

            if hasattr(msg, 'content') and msg.content:
                content = msg.content
                # 过滤废话前缀（流式块级别过滤）
                skip_prefixes = ("好的", "现在", "首先", "接下来", "基于", "根据",
                                 "用户问", "我需要", "让我", "Thought", "Action", "Observation")
                if content.strip().startswith(skip_prefixes):
                    continue
                # 只输出 AI 最终回复（非工具调用）
                if not hasattr(msg, 'tool_calls') or not msg.tool_calls:
                    # 过滤明显是搜索原文的块
                    if any(x in content for x in ["标题:", "内容摘要:", "适合你如果",
                                                   "实测评分", "价格表", "发生错误"]):
                        continue
                    full_content += content
                    yield content

        # 5. 可选：将生成的完整报告存入 RAG（需手动开启）
        # 注意：由于流式输出已经 yield 给前端，这里完整报告已收集在 full_content 中
        # 你可以根据需要取消下面注释
        # if full_content.strip():
        #     rag_mem.add_report(full_content, metadata={"query": user_query, "thread_id": thread_id})

    except Exception as e:
        yield f"发生错误: {str(e)}"

# ==================== 测试入口 ====================
if __name__ == "__main__":
    test_query = "我想买一款1000元以内的洗碗机，帮我做一下产品评测和推荐"
    print("正在生成报告...")
    for chunk in get_product_review_streaming(test_query, thread_id="test_session_001"):
        print(chunk, end="", flush=True)
>>>>>>> d004942 (first commit)
    print("\n" + "="*50)