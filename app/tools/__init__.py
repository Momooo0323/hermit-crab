"""
Hermit Crab — 工具系统

轻量插件架构：工具通过 @tool 装饰器注册，自动生成 OpenAI 函数调用格式。
支持两种触发方式：
  1. 函数调用模式（Function Calling）— 模型自动调用
  2. 文本关键词触发 — 非 FC 模型也能使用
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import re

# ── 工具注册表 ──

_registry: dict[str, "Tool"] = {}
_tool_aliases: dict[str, str] = {}  # 关键词 → 工具名


@dataclass
class Tool:
    """一个可被模型调用或用户触发的工具。"""
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: callable
    icon: str = "🔧"
    keywords: list = field(default_factory=list)  # 文本触发关键词


def register(func=None, *, name=None, description=None, parameters=None,
             icon="🔧", keywords=None):
    """注册一个工具。

    可作为装饰器使用:
        @register
        def my_tool(app, query: str): ...

        @register(name="search", icon="🌐", keywords=["搜索", "查"])
        def web_search(app, query: str): ...
    """
    def wrapper(f):
        tool_name = name or f.__name__
        tool_desc = description or (f.__doc__ or "").strip()
        # 自动从函数签名生成参数 schema
        import inspect
        sig = inspect.signature(f)
        props = {}
        required = []
        for p_name, p_param in sig.parameters.items():
            if p_name == "app":
                continue
            # 尝试从 type hint 推断类型
            type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
            param_type = "string"
            if p_param.annotation != inspect.Parameter.empty:
                param_type = type_map.get(p_param.annotation, "string")
            props[p_name] = {"type": param_type, "description": p_name}
            if p_param.default is inspect.Parameter.empty:
                required.append(p_name)
        tool_params = parameters or {
            "type": "object",
            "properties": props,
            "required": required,
        }
        tool = Tool(
            name=tool_name,
            description=tool_desc,
            parameters=tool_params,
            handler=f,
            icon=icon,
            keywords=keywords or [],
        )
        _registry[tool_name] = tool
        for kw in tool.keywords:
            _tool_aliases[kw] = tool_name
        return f
    if func is not None:
        return wrapper(func)
    return wrapper


# ── 注册表查询 ──

def get_tools() -> list[Tool]:
    """获取所有已注册工具。"""
    return list(_registry.values())


def get_tool(name: str) -> Optional[Tool]:
    """按名称查找工具。"""
    return _registry.get(name)


def get_openai_tools() -> list[dict]:
    """返回 OpenAI 函数调用格式的工具列表。"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in _registry.values()
    ]


# 工具 → 权限映射（没有映射的工具默认放行）
_TOOL_PERMISSIONS = {
    "read_file":     "file_read",
    "file_write":    "file_create",
    "file_delete":   "file_delete",
    "create_folder": "file_create",
    "shell_exec":    "shell_exec",
    "memory_add":    "memory_add",
    "memory_delete": "memory_delete",
    "web_search":    "web_search",
    "kb_search":     "kb_search",
    "kb_index":      "kb_index",
}


def execute_tool(name: str, args: dict, app=None) -> str:
    """执行工具，返回结果文本（含权限检查）。"""
    tool = _registry.get(name)
    if not tool:
        return f"[工具错误] 未知工具: {name}"

    # 权限检查
    perm_key = _TOOL_PERMISSIONS.get(name)
    if perm_key and app and hasattr(app, "permissions"):
        import permissions as _perm
        if not _perm.check(app.permissions, perm_key):
            label = dict(_perm.PERMISSION_DEFS).get(perm_key, [perm_key])[0] if isinstance(perm_key, str) else perm_key
            # 找对应的显示名称
            for k, lbl, _, _ in _perm.PERMISSION_DEFS:
                if k == perm_key:
                    label = lbl
                    break
            return f"[权限被拒] {label} 未开启，请在权限设置中启用。"

    try:
        result = tool.handler(**args, app=app)
        return str(result)
    except Exception as e:
        return f"[工具错误] {name}: {e}"


def match_tool_from_text(text: str) -> list[tuple[str, str, str]]:
    """从用户文本中匹配关键词触发的工具。

    返回: [(tool_name, keyword, matched_query), ...]
    """
    matches = []
    for kw, tool_name in sorted(_tool_aliases.items(), key=lambda x: -len(x[0])):
        idx = text.find(kw)
        if idx != -1:
            query = text[idx + len(kw):].strip().rstrip("，。？！,?!")
            if query:
                matches.append((tool_name, kw, query))
    return matches


def init_tools(app):
    """初始化工具系统：导入所有工具模块。"""
    import app.tools.web_search
    import app.tools.read_file
    import app.tools.file_write
    import app.tools.file_delete
    import app.tools.create_folder
    import app.tools.shell_exec
    import app.tools.knowledge_tools
    import app.tools.memory_tools
