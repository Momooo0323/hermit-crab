"""
工具：网络搜索
支持 DuckDuckGo（主）和 Bing（备用）。
"""

from app.tools import register


@register(name="web_search", icon="🌐",
          keywords=["搜索", "搜一下", "搜搜", "查一下", "查查", "帮我查"],
          description="搜索网络获取实时信息。当用户问新闻、最新消息、实时数据时使用。")
def web_search(app, query: str) -> str:
    """搜索网络并返回格式化结果。"""
    return app._search_web(query)
