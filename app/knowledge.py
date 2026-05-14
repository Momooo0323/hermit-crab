"""
Hermit Crab Knowledge Base — 轻量本地知识库。
基于关键词匹配，零外部依赖。
"""

import re
import json
from pathlib import Path


class KnowledgeBase:
    """基于关键词匹配的轻量知识库。"""

    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "knowledge_data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chunks = []
        self.stats = {"files": 0, "chunks": 0}
        self._load()

    # --- 持久化 ---

    def _chunks_path(self):
        return self.data_dir / "chunks.json"

    def _load(self):
        path = self._chunks_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.chunks = data.get("chunks", [])
                self.stats = data.get("stats", {"files": 0, "chunks": 0})
            except Exception:
                pass

    def _save(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._chunks_path().write_text(
            json.dumps(
                {"chunks": self.chunks, "stats": self.stats},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    # --- 索引 ---

    def index_file(self, filepath):
        """索引单个文件。"""
        fp = Path(filepath)
        if not fp.exists():
            return f"文件不存在: {filepath}"
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception as e:
            return f"读取失败: {e}"

        paragraphs = re.split(r'\n\s*\n', text)
        count = 0
        existing = {(c["source"], c["text"]) for c in self.chunks}
        for p in paragraphs:
            p = p.strip()
            if len(p) >= 20 and (str(fp), p) not in existing:
                self.chunks.append({"text": p, "source": str(fp)})
                existing.add((str(fp), p))
                count += 1

        self.stats["files"] += 1
        self.stats["chunks"] += count
        self._save()
        return f"已索引 {fp.name}: {count} 个段落"

    def index_directory(self, dirpath):
        """索引整个目录的文本文件。"""
        dp = Path(dirpath)
        if not dp.exists():
            return f"目录不存在: {dirpath}"

        exts = (".md", ".txt", ".py", ".json", ".yaml", ".yml", ".cfg", ".ini", ".conf", ".toml")
        files = [f for f in dp.rglob("*") if f.is_file() and f.suffix in exts]

        for f in files:
            try:
                self.index_file(f)
            except Exception:
                pass
        return f"已索引 {len(files)} 个文件, 共 {self.stats['chunks']} 个段落"

    # --- 搜索 ---

    def search(self, query, k=5):
        """按关键词搜索，返回 [(score, chunk)]。"""
        keywords = query.lower().split()
        scored = []
        for c in self.chunks:
            text_lower = c["text"].lower()
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]

    def get_context(self, query, max_chars=1200):
        """搜索并格式化为 context 字符串。"""
        results = self.search(query)
        if not results:
            return ""
        parts = ["[知识库相关片段]"]
        chars = 0
        for score, r in results:
            snippet = r["text"][:250]
            if chars + len(snippet) > max_chars:
                break
            parts.append(f"  来自 {r['source']}:")
            parts.append(f"    {snippet}")
            chars += len(snippet)
        return "\n".join(parts)

    def status(self):
        if not self.chunks:
            return "知识库为空。用 /kb index <路径> 添加文档。"
        return f"知识库: {self.stats['files']} 个文件, {self.stats['chunks']} 个段落"
