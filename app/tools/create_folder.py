"""
工具：创建文件夹
"""

from pathlib import Path
from app.tools import register


@register(name="create_folder", icon="📁",
          keywords=["创建文件夹", "创建目录", "新建文件夹", "mkdir"],
          description="在指定路径创建一个新文件夹。参数 folderpath 为文件夹路径。如果父目录不存在会自动创建。")
def create_folder(app, folderpath: str) -> str:
    """创建文件夹（目录）。"""
    fp = Path(folderpath)
    try:
        fp.mkdir(parents=True, exist_ok=True)
        return f"✓ 文件夹已创建: {fp}"
    except Exception as e:
        return f"[创建失败] {e}"
