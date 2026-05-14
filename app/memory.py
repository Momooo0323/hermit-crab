"""
Hermit Crab Memory System
File-based persistent memory with MEMORY.md index,
shared by desktop.py and agent.py.
"""

import re
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"


def _sanitize_name(name):
    """Filter illegal filename characters to prevent path traversal."""
    sanitized = re.sub(r'[<>:"/\\|?*]', "", name.strip())
    if not sanitized:
        raise ValueError("记忆名称不合法")
    return sanitized


def ensure_dirs():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_INDEX.exists():
        MEMORY_INDEX.write_text("# Memories\n\n", encoding="utf-8")


def load_memories():
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
            parts = content.split("---", 2)
            body = parts[2].strip() if len(parts) > 2 else content.strip()
            memories[name] = {"description": desc, "content": body}
    return memories


def save_memory(name, description, content):
    ensure_dirs()
    name = _sanitize_name(name)
    fp = MEMORY_DIR / f"{name}.md"
    fp.write_text(
        f"---\nname: {name}\ndescription: {description}\n"
        f"metadata:\n  type: user\n"
        f"  saved_at: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n---\n\n{content}\n",
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
    """Format memories for context injection (desktop.py format)."""
    if not memories:
        return ""
    parts = ["[记忆注入]"]
    for name, mem in memories.items():
        parts.append(f"  - {mem['description']}")
        if mem["content"]:
            c = mem["content"][:150]
            if len(mem["content"]) > 150:
                c += "..."
            parts.append(f"    {c}")
    return "\n".join(parts)
