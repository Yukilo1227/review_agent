# 🛒 智能产品评测 Agent
基于 LangGraph 和通义千问的智能产品评测助手。用户输入产品需求（如"500元以内的蓝牙耳机"），Agent 自动联网搜索最新评测，生成结构化评测报告，支持多轮对话、历史记忆和流式输出。

## ✨ 功能特点

- 🌐 **联网搜索**：通过 Tavily API 获取真实评测、口碑、价格
- 🧠 **RAG 记忆**：历史报告向量化存储（FAISS），相似问题无需重复搜索
- 💬 **短期记忆**：同一会话内可连续追问（如"那第一款降噪怎么样？"）
- 📊 **表格输出**：以 Markdown 表格形式推荐多款产品对比
- ⚡ **流式输出**：实时逐字显示，降低等待焦虑
- 🎨 **Web 界面**：基于 Streamlit，支持会话管理、历史记录

## 🛠️ 技术栈
- **LangGraph** + **LangChain**：Agent 编排与工具调用
- **阿里云通义千问**（qwen3-max）：大语言模型
- **Tavily Search API**：实时联网搜索
- **FAISS** + **DashScopeEmbeddings**：RAG 向量检索
- **Streamlit**：前端交互界面

## 🚀 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/Yukilo1227/review_agent.git
cd review_agent
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置API KEY
复制 .env.example 为 .env 并填入你的密钥：

```
DASHSCOPE_API_KEY=你的阿里云通义千问API Key
TAVILY_API_KEY=你的Tavily API Key
```

### 4. 运行
```bash
streamlit run app.py
```

## 项目结构
```
├── app.py                 # Streamlit 前端
├── agent.py               # Agent 核心逻辑（工具、RAG、流式）
├── requirements.txt       # 依赖列表
├── .env.example           # 环境变量模板
└── README.md              # 项目说明
```

## 🙋 常见问题
1. 搜索失败/超时：检查网络是否能够访问 Tavily API，或尝试更换代理。
2. RAG 检索无效果：需要至少产生两份相似产品的报告后才会触发。

### 演示视频
https://www.bilibili.com/video/BV18y5M6LEmL/?vd_source=d08add98d6cdd3245f42a4c450095842




