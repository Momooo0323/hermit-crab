"""
工具：写入 / 创建文件
"""

from pathlib import Path
from app.tools import register


@register(name="file_write", icon="📝",
          keywords=["写入", "创建", "写文件", "覆盖"],
          description="创建新文件或覆盖已有文件。参数 filepath 为文件路径，content 为写入内容。")
def file_write(app, filepath: str, content: str) -> str:
    """写入或创建文件。"""
    fp = Path(filepath)
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"✓ 已写入: {fp.name}  ({len(content)} 字符, {fp.stat().st_size / 1024:.1f}KB)"
    except Exception as e:
        return f"[写入失败] {e}"
