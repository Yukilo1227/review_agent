import streamlit as st
import uuid
from agent import get_product_review_streaming

st.set_page_config(page_title="智能产品评测Agent", layout="wide")
st.title("🤖 产品评测报告生成 Agent")
st.markdown("输入产品需求，Agent 会联网搜索并生成专业评测报告（含评分表格）。")

# 初始化会话状态
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# 侧边栏配置
with st.sidebar:
    st.header("会话控制")
    st.write(f"会话 ID: `{st.session_state.thread_id[-8:]}`")
    if st.button("🔄 新会话"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    st.markdown("---")
    st.markdown("**模型**: 阿里云 qwen3-max-2026-01-23")
    st.markdown("**工具**: Tavily 联网搜索")
    st.markdown("**增强**: RAG 历史报告检索 + 短期记忆")

# 显示历史对话
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 输入框
if user_query := st.chat_input("输入产品需求，例如：500元以内的蓝牙耳机推荐"):
    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    # 调用 Agent 流式生成
    with st.chat_message("assistant"):
        response = st.write_stream(
            get_product_review_streaming(user_query, st.session_state.thread_id)
        )
    st.session_state.messages.append({"role": "assistant", "content": response})