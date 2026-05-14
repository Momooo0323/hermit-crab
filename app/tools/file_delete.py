"""
工具：删除文件
"""

from pathlib import Path
from app.tools import register


@register(name="file_delete", icon="🗑",
          keywords=["删除", "删除文件"],
          description="删除指定文件。参数 filepath 为要删除的文件路径。")
def file_delete(app, filepath: str) -> str:
    """删除本地文件。"""
    fp = Path(filepath)
    if not fp.exists():
        return f"[删除失败] 文件不存在: {filepath}"
    if not fp.is_file():
        return f"[删除失败] 不是文件: {filepath}"
    try:
        fp.unlink()
        return f"✓ 已删除: {fp.name}"
    except Exception as e:
        return f"[删除失败] {e}"
