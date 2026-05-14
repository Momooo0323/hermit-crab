"""
工具：知识库操作
"""

import json
from pathlib import Path
from app.tools import register


@register(name="kb_search", icon="📚",
          description="在本地知识库中搜索相关文档片段。参数 query 为搜索关键词。")
def kb_search(app, query: str) -> str:
    """搜索知识库。"""
    if not app.kb:
        return "[知识库未加载]"
    results = app.kb.search(query)
    if not results:
        return "知识库无匹配结果。"
    lines = [f"知识库匹配 ({len(results)}):"]
    for score, r in results:
        src = Path(r["source"]).name
        lines.append(f"  [{src}] {r['text'][:200]}")
    return "\n".join(lines)


@register(name="kb_status", icon="📊",
          description="查看知识库当前状态（文件数、段落数）。")
def kb_status(app) -> str:
    """查看知识库状态。"""
    if not app.kb:
        return "[知识库未加载]"
    return app.kb.status()


@register(name="mem_list", icon="🧠",
          description="列出 AI 记住的关于用户的所有记忆。")
def mem_list(app) -> str:
    """列出所有记忆。"""
    if not app.memories:
        return "还没有记忆。"
    lines = [f"记忆 ({len(app.memories)}):"]
    for name, mem in app.memories.items():
        lines.append(f"  [{name}] {mem['description']}")
    return "\n".join(lines)
