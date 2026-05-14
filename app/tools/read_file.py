"""
工具：读取文件
"""

from app.tools import register


@register(name="read_file", icon="📄",
          keywords=["读取", "读文件", "打开文件", "查看文件"],
          description="读取本地文本文件内容。参数 filepath 为文件路径。")
def read_file(app, filepath: str) -> str:
    """读取本地文本文件。"""
    return app._read_file(filepath)
