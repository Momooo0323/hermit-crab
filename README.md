# Hermit Crab

**Hermit Crab（寄居蟹）** — 一个轻量、可扩展的本地 AI 桌面助手，支持本地 llama.cpp、OpenAI 兼容 API 和 Anthropic Claude 三种后端。

纯 Python + tkinter 构建，零外部 UI 依赖，双击即用。

---

## 功能

- **多 Provider 切换** — 本地模型 (`llama-server`) / OpenAI 兼容 API / Anthropic Claude
- **终端风格暗色 UI** — 5 套暗色主题：经典、深海蓝、暮光紫、森林绿、暖阳橙
- **持久记忆系统** — 基于文件的记忆，每次对话自动注入
- **RAG 知识库** — 关键词匹配，零外部依赖，一键索引文档
- **Web 搜索集成** — DuckDuckGo + Bing 容灾
- **多步规划执行** — 模型输出 [计划] 后开启逐步执行
- **对话管理** — 历史记录、重命名、导出为 Markdown、重试/编辑
- **上下文压缩** — 超长上下文自动压缩早期对话
- **流式输出** — 实时显示 token 速度和上下文占用
- **思考过程显示** — 支持 reasoning_content / thinking 块
- **代码块语法高亮** — 自动识别 ``` 标记
- **拖拽文件** — 从资源管理器拖入文件自动发送给 AI
- **模型管理** — 双击切换模型，自动管理后端进程

## 项目结构

```
hermit-crab/
├── app/
│   ├── __init__.py          # 包标记
│   ├── memory.py            # 记忆系统（共享模块）
│   ├── themes.py            # 主题定义
│   ├── win32_drop.py        # Windows 拖拽支持
│   ├── providers.py         # LLM Provider 封装
│   └── knowledge.py         # RAG 知识库
├── desktop.py               # 桌面 GUI 版
├── agent.py                 # CLI 命令行版
├── config.json              # 配置文件
├── requirements.txt         # Python 依赖
├── Shrimpy.bat              # 启动桌面版
└── 启动桌面版.bat            # 启动桌面版（含暂停）
```

## 快速开始

### 环境要求
- Python 3.8+
- Windows（目前仅支持 Windows 拖拽功能）

### 安装

```bash
pip install -r requirements.txt
```

### 运行

**桌面版（推荐）— 双击 `run.bat` 或运行：**
```bash
python desktop.py
```

**命令行版 — 双击 `run-cli.bat` 或运行：**
```bash
python agent.py
```

首次运行会自动弹出设置向导，引导您选择后端和配置密钥。

### 配置后端

**本地模式（默认）：**
1. 下载 [llama.cpp](https://github.com/ggml-org/llama.cpp) 并编译 `llama-server`
2. 将 `llama-server` 放到 PATH 或项目目录下
3. 下载 .gguf 模型放到 `models/` 目录
4. 运行 Hermit Crab，会自动拉起后端

**OpenAI 模式：**
- 在设置向导中选择 OpenAI，或运行后用 `/key openai sk-xxx` 设置密钥

**Anthropic 模式：**
- 在设置向导中选择 Anthropic，或运行后用 `/key anthropic sk-ant-xxx` 设置密钥

## 命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/models` | 列出可用模型 |
| `/model <关键词>` | 切换模型 |
| `/provider [local\|openai\|anthropic]` | 查看/切换后端 |
| `/key <类型> <密钥>` | 设置 API 密钥 |
| `/search <关键词>` | 搜索网络 |
| `/read <路径>` | 读取文件 |
| `/plan <任务>` | 多步规划执行 |
| `/kb index <路径>` | 索引文档到知识库 |
| `/mem add <名字> <描述>` | 添加记忆 |
| `/history` | 历史对话 |
| `/export` | 导出对话为 Markdown |
| `/theme [名称]` | 切换主题 |
| `/prompt` | 编辑系统提示词 |

## License

MIT
