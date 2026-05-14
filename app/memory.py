"""
Hermit Crab Memory System
File-based persistent memory with MEMORY.md index,
shared by desktop.py and agent.py.

v2.4 — Enhanced with memory types and importance levels.
"""

import re
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"

TYPE_ICONS = {
    "user_info": "👤", "preference": "⭐", "fact": "📌",
    "lesson": "🎯", "task": "📋",
}
TYPE_LABELS = {
    "user_info": "用户信息", "preference": "偏好", "fact": "事实",
    "lesson": "经验", "task": "任务",
}


def _sanitize_name(name):
    """Filter illegal filename characters to prevent path traversal."""
    sanitized = re.sub(r'[<>:"/\\|?*]', "", name.strip())
    if not sanitized:
        raise ValueError("记忆名称不合法")
    return sanitized


def _parse_frontmatter(text):
    """Parse YAML-like frontmatter from memory files (compatible with old format)."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    header = parts[1].strip()
    body = parts[2].strip()
    meta = {}
    for line in header.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not val or key == "metadata":
            continue
        if key == "importance":
            try:
                val = int(val)
            except ValueError:
                val = 1
        meta[key] = val
    meta.setdefault("type", "user_info")
    meta.setdefault("importance", 1)
    return meta, body


def ensure_dirs():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_INDEX.exists():
        MEMORY_INDEX.write_text("# Memories\n\n", encoding="utf-8")


def load_memories():
    """
    Load all memories from memory/.
    Returns {name: {description, content, type, importance, saved_at}}
    """
    ensure_dirs()
    if not MEMORY_INDEX.exists():
        return {}
    memories = {}
    text = MEMORY_INDEX.read_text(encoding="utf-8")
    pattern = re.compile(r"^-\s*\[(.+?)\]\((.+?)\)\s*[—–-]\s*(.*)", re.MULTILINE)
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        filename = m.group(2).strip()
        desc = m.group(3).strip()
        fp = MEMORY_DIR / filename
        if fp.exists():
            content = fp.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(content)
            memories[name] = {
                "description": meta.get("description", desc),
                "content": body,
                "type": meta.get("type", "user_info"),
                "importance": meta.get("importance", 1),
                "saved_at": meta.get("saved_at", ""),
            }
    return memories


def save_memory(name, description, content, mem_type="user_info", importance=1):
    """Save a new memory with type and importance."""
    ensure_dirs()
    name = _sanitize_name(name)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    fp = MEMORY_DIR / f"{name}.md"
    fp.write_text(
        f"---\nname: {name}\ndescription: {description}\n"
        f"type: {mem_type}\nimportance: {importance}\nsaved_at: {now}\n"
        f"---\n\n{content}\n",
        encoding="utf-8",
    )
    lines = MEMORY_INDEX.read_text(encoding="utf-8").splitlines()
    lines = [l for l in lines if not l.strip().startswith(f"- [{name}]")]
    lines.append(f"- [{name}]({name}.md) — {description}")
    MEMORY_INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def delete_memory(name):
    name = _sanitize_name(name)
    fp = MEMORY_DIR / f"{name}.md"
    if fp.exists():
        fp.unlink()
    if MEMORY_INDEX.exists():
        lines = MEMORY_INDEX.read_text(encoding="utf-8").splitlines()
        lines = [l for l in lines if not l.strip().startswith(f"- [{name}]")]
        MEMORY_INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_memory_text(memories):
    """
    Format memories for context injection, sorted by importance (high first).
    Returns multi-line string with type icons and importance indicators.
    """
    if not memories:
        return ""
    sorted_items = sorted(
        memories.items(),
        key=lambda x: x[1].get("importance", 1),
        reverse=True,
    )
    parts = ["[记忆注入]"]
    for name, mem in sorted_items:
        mem_type = mem.get("type", "user_info")
        imp = mem.get("importance", 1)
        icon = TYPE_ICONS.get(mem_type, "📝")
        label = TYPE_LABELS.get(mem_type, mem_type)
        stars = "⭐" * imp + "☆" * (5 - imp)
        parts.append(f"  {icon}[{name}] ({label}, {stars}) — {mem['description']}")
        if mem["content"]:
            budget = 150 + (imp - 1) * 50
            c = mem["content"][:budget]
            if len(mem["content"]) > budget:
                c += "..."
            parts.append(f"    {c}")
    return "\n".join(parts)
