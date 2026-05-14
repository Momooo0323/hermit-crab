"""
工具：记忆管理
"""

from app.tools import register
from app.memory import save_memory, delete_memory, load_memories


@register(name="memory_add", icon="🧠",
          parameters={
              "type": "object",
              "properties": {
                  "name": {"type": "string", "description": "记忆名称"},
                  "description": {"type": "string", "description": "记忆描述"},
                  "content": {"type": "string", "description": "记忆详细内容"},
              },
              "required": ["name", "description", "content"],
          },
          description="保存一条关于用户的记忆。当用户透露个人信息、偏好、事实时使用。")
def memory_add(app, name: str, description: str, content: str) -> str:
    """添加一条记忆。"""
    save_memory(name, description, content)
    if hasattr(app, '_load_memories'):
        app._load_memories()
    return f"已保存记忆: {name}"


@register(name="memory_delete", icon="🧹",
          description="删除指定名称的记忆。参数 name 为记忆名称。")
def memory_delete(app, name: str) -> str:
    """删除一条记忆。"""
    delete_memory(name)
    if hasattr(app, '_load_memories'):
        app._load_memories()
    return f"已删除记忆: {name}"
