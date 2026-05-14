"""
Hermit Crab Knowledge Base — TF-IDF 语义知识库。

纯 Python 实现（零外部依赖），支持：
  - TF-IDF 相关性排序（优于纯关键词匹配）
  - 中英文分词支持
  - 增量索引
  - 持久化到 JSON
"""

import re
import math
import json
import unicodedata
from pathlib import Path
from collections import Counter


def _tokenize(text: str) -> list[str]:
    """简单中英文分词。

    中文：单字 + 常用双字组合
    英文：小写 + 分词
    """
    text = unicodedata.normalize("NFKC", text.lower())
    tokens = []

    # 提取英文单词和数字
    for word in re.findall(r'[a-zA-Z][a-zA-Z0-9_\-]+', text):
        if len(word) >= 2:
            tokens.append(word)

    # 提取中文字符（单字 + 双字）
    chinese_chars = re.findall(r'[一-鿿]', text)
    for c in chinese_chars:
        tokens.append(c)
    # 双字组合
    for i in range(len(chinese_chars) - 1):
        bigram = chinese_chars[i] + chinese_chars[i + 1]
        tokens.append(bigram)

    return tokens


class KnowledgeBase:
    """TF-IDF 本地知识库。"""

    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "knowledge_data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.docs: list[dict] = []  # [{"id": str, "text": str, "source": str}]
        self.doc_count = 0
        self.df: Counter = Counter()  # 文档频率: term -> 包含该词的文档数
        self._loaded = False
        self._load()

    # ── 持久化 ──

    def _chunks_path(self):
        return self.data_dir / "kb_index.json"

    def _load(self):
        path = self._chunks_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.docs = data.get("docs", [])
                self.doc_count = data.get("doc_count", 0)
                self.df = Counter(data.get("df", {}))
                self._loaded = True
            except Exception:
                pass

    def _save(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._chunks_path().write_text(
            json.dumps({
                "docs": self.docs,
                "doc_count": self.doc_count,
                "df": dict(self.df),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 索引 ──

    def index_file(self, filepath):
        """索引单个文件，返回结果信息。"""
        fp = Path(filepath)
        if not fp.exists():
            return f"文件不存在: {filepath}"
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception as e:
            return f"读取失败: {e}"

        paragraphs = re.split(r'\n\s*\n', text)
        existing = {(d["source"], d["text"]) for d in self.docs}
        count = 0
        new_docs = []

        for p in paragraphs:
            p = p.strip()
            if len(p) < 20:
                continue
            key = (str(fp), p)
            if key in existing:
                continue
            doc_id = f"doc_{self.doc_count + count + 1}"
            entry = {"id": doc_id, "text": p, "source": str(fp)}
            self.docs.append(entry)
            new_docs.append(entry)
            existing.add(key)
            count += 1

        # 更新文档频率
        for doc in new_docs:
            terms = set(_tokenize(doc["text"]))
            for term in terms:
                self.df[term] += 1

        self.doc_count += count
        self._save()
        return f"已索引 {fp.name}: {count} 个段落"

    def index_directory(self, dirpath):
        """索引整个目录的文本文件。"""
        dp = Path(dirpath)
        if not dp.exists():
            return f"目录不存在: {dirpath}"

        exts = (".md", ".txt", ".py", ".json", ".yaml", ".yml", ".cfg", ".ini", ".conf", ".toml")
        files = [f for f in dp.rglob("*") if f.is_file() and f.suffix in exts]
        total = 0
        for f in files:
            try:
                result = self.index_file(f)
                # 提取段落数
                m = re.search(r'(\d+) 个段落', result)
                if m:
                    total += int(m.group(1))
            except Exception:
                pass
        return f"已索引 {len(files)} 个文件, 共 {self.doc_count} 个段落 (新增 {total})"

    # ── 搜索 ──

    def search(self, query: str, k=5):
        """TF-IDF 搜索，返回 [(score, doc), ...]。"""
        if not self.docs:
            return []
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        n_docs = len(self.docs)
        scores = []
        query_tf = Counter(query_terms)

        for doc in self.docs:
            doc_terms = _tokenize(doc["text"])
            doc_tf = Counter(doc_terms)
            doc_norm = math.sqrt(sum(tf ** 2 for tf in doc_tf.values()))
            if doc_norm == 0:
                continue

            score = 0.0
            for term, q_tf in query_tf.items():
                if term in doc_tf and term in self.df:
                    tf = doc_tf[term] / doc_norm
                    idf = math.log((n_docs + 1) / (self.df[term] + 1)) + 1
                    score += q_tf * tf * idf

            if score > 0:
                scores.append((score, doc))

        scores.sort(key=lambda x: -x[0])
        return scores[:k]

    def get_context(self, query, max_chars=1500):
        """搜索并格式化为 context 字符串。"""
        results = self.search(query)
        if not results:
            return ""
        parts = ["[知识库相关片段 (TF-IDF)]"]
        chars = 0
        for score, r in results:
            snippet = r["text"][:300]
            if chars + len(snippet) > max_chars:
                break
            src = Path(r["source"]).name
            parts.append(f"  [{src}] (得分: {score:.3f})")
            parts.append(f"    {snippet}")
            chars += len(snippet)
        return "\n".join(parts)

    def status(self):
        if not self.docs:
            return "知识库为空。用 /kb index <路径> 添加文档。"
        return f"知识库: {len(set(d['source'] for d in self.docs))} 个文件, {len(self.docs)} 个段落"
