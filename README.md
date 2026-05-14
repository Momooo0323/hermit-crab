# Hermit Crab

**Hermit Crab（寄居蟹）** — 一个轻量、可扩展的本地 AI 桌面助手，支持本地 llama.cpp、OpenAI 兼容 API 和 Anthropic Claude 三种后端。

纯 Python + tkinter 构建，零外部 UI 依赖，双击即用。

---

## 功能

- **多 Provider 切换** — 本地模型 (`llama-server`) / OpenAI 兼容 API / Anthropic Claude
- **插件工具系统** — `@register` 装饰器注册工具，支持函数调用（FC）和关键词触发，自动执行回调循环（最多 5 轮）
- **权限控制** — 9 项独立开关（文件读写删、记忆管理、搜索、知识库、计划），图形化设置面板
- **语义知识库（RAG）** — 纯 Python TF-IDF 实现，零外部依赖，中英文分词，增量索引
- **Web 搜索集成** — DuckDuckGo + Bing 容灾，国内网络可用
- **多步规划执行** — 模型输出 `[计划]` 后开启逐步执行，搜索/读文件步骤自动路由
- **持久记忆系统** — 基于文件的记忆，每次对话自动注入
- **对话管理** — 历史记录、重命名、导出 Markdown、重试/编辑/新对话
- **自动上下文压缩** — 超长上下文自动压缩早期对话为摘要
- **流式输出** — 实时显示 token 速度、上下文占用，支持思考过程显示，⏹ 随时打断停止
- **暗色 UI** — 5 套暗色主题：经典、深海蓝、暮光紫、森林绿、暖阳橙
- **代码块语法高亮** — 自动识别 ``` 标记
- **拖拽文件** — 从资源管理器拖入文件自动读取并发送给 AI
- **模型管理** — 图形化切换模型，自动管理后端进程
- **首次运行向导** — 3 步引导配置 Provider 和密钥
- **系统密钥环** — 可选 keyring 将 API 密钥存入 OS 凭据管理器

## 项目结构

```
hermit-crab/
├── app/
│   ├── tools/                  # 工具插件包
│   │   ├── __init__.py         # 注册表 + 权限映射
│   │   ├── web_search.py       # 网络搜索
│   │   ├── read_file.py        # 读取文件
│   │   ├── file_write.py       # 写入/创建文件
│   │   ├── file_delete.py      # 删除文件
│   │   ├── knowledge_tools.py  # 知识库搜索/状态/记忆列表
│   │   └── memory_tools.py     # 记忆添加/删除
│   ├── __init__.py
│   ├── memory.py               # 记忆系统
│   ├── themes.py               # 主题定义
│   ├── win32_drop.py           # Windows 拖拽支持
│   ├── providers.py            # LLM Provider 封装
│   ├── knowledge.py            # TF-IDF 语义知识库
│   └── setup_wizard.py         # 首次运行向导
├── permissions.py              # 权限控制模块
├── desktop.py                  # 桌面 GUI 版（主程序）
├── agent.py                    # CLI 命令行版
├── config.json                 # 配置文件
├── requirements.txt            # Python 依赖
├── run.bat                     # 桌面版启动脚本
├── run-cli.bat                 # 命令行版启动脚本
└── 更新日志.md                  # 版本历史
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
5. 切换模型可在软件内直接完成，无需手动改配置

**OpenAI 模式：**
- 在设置向导中选择 OpenAI，或运行后用 `/key openai sk-xxx` 设置密钥

**Anthropic 模式：**
- 在设置向导中选择 Anthropic，或运行后用 `/key anthropic sk-ant-xxx` 设置密钥

## 命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/provider [local\|openai\|anthropic]` | 查看/切换后端 |
| `/key <openai\|anthropic> <密钥>` | 设置 API 密钥 |
| `/models` | 列出可用模型 |
| `/model <关键词>` | 切换模型 |
| `/read <路径>` | 读取文件并让 AI 分析 |
| `/write <路径>` | 创建或覆盖文件（弹出编辑器） |
| `/delete <路径>` | 删除文件（需确认） |
| `/search <关键词>` | 搜索网络 |
| `/plan <任务>` | 多步规划执行 |
| `/kb index <路径>` | 索引文档到知识库 |
| `/kb search <词>` | 搜索知识库 |
| `/kb status` | 查看知识库统计 |
| `/mem add <名字> <描述>` | 添加记忆 |
| `/mem del <名字>` | 删除记忆 |
| `/mem list` | 列出所有记忆 |
| `/new` | 新对话 |
| `/history` | 历史对话浏览 |
| `/rename <标题>` | 重命名当前对话 |
| `/export` | 导出对话为 Markdown |
| `/theme [名称]` | 查看/切换主题 |
| `/prompt` | 编辑系统提示词 |
| `/clear` | 清屏 |
| `/status` | 检查后端状态 |

## License

MIT
