"""Retrieval-augmented generation over the repository.

Hybrid retrieval: BM25 keyword search (always available, zero dependencies) fused with dense
embeddings (Ollama / OpenAI-compatible) when an embedding model is reachable."""
from __future__ import annotations

import ast
import json
import math
import re
import threading
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..llm.providers import LLMConfig, LLMError, chat_stream, embed, without_thinking

TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,40}|\d+")
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
STOP = set("the a an and or of to in for on with is are be this that it as by from at if else return def class import "
           "self const let var function true false none null new public private static void int string".split())

CHUNK_LINES = 60
OVERLAP = 12
MAX_CHUNKS = 5000
MAX_EMBED = 1800


def tokenize(text: str) -> list[str]:
    out = []
    for t in TOKEN.findall(text):
        low = t.lower()
        if low in STOP:
            continue
        out.append(low)
        if "_" in t or CAMEL.search(t):
            out += [p.lower() for p in re.split(r"_|" + CAMEL.pattern, t) if len(p) > 1]
    return out


def _py_chunks(path: str, text: str) -> list[dict]:
    try:
        tree = ast.parse(text)
    except Exception:
        return []
    lines = text.splitlines()
    chunks, covered = [], 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            s, e = node.lineno, getattr(node, "end_lineno", node.lineno)
            if s - 1 > covered and any(l.strip() for l in lines[covered:s - 1]):
                chunks.append((covered + 1, s - 1))
            if e - s > CHUNK_LINES * 2:   # big class -> window it
                for ws in range(s, e + 1, CHUNK_LINES - OVERLAP):
                    chunks.append((ws, min(e, ws + CHUNK_LINES)))
            else:
                chunks.append((s, e))
            covered = e
    if covered < len(lines):
        chunks.append((covered + 1, len(lines)))
    return [{"path": path, "start": s, "end": e, "text": "\n".join(lines[s - 1:e])} for s, e in chunks if e >= s]


def chunk_file(path: str, text: str) -> list[dict]:
    if path.endswith(".py"):
        c = _py_chunks(path, text)
        if c:
            return c
    lines = text.splitlines()
    if not lines:
        return []
    out = []
    step = CHUNK_LINES - OVERLAP
    for s in range(0, len(lines), step):
        e = min(len(lines), s + CHUNK_LINES)
        out.append({"path": path, "start": s + 1, "end": e, "text": "\n".join(lines[s:e])})
        if e == len(lines):
            break
    return out


def build_chunks(contents: dict[str, str], priority: dict[str, float]) -> list[dict]:
    files = sorted(contents, key=lambda p: -priority.get(p, 0))
    chunks: list[dict] = []
    for p in files:
        if p.endswith((".json", ".svg", ".csv", ".lock")) and not p.endswith(("package.json", "tsconfig.json")):
            continue
        if len(contents[p]) > 300_000:
            continue
        chunks.extend(chunk_file(p, contents[p]))
        if len(chunks) >= MAX_CHUNKS:
            break
    for i, c in enumerate(chunks):
        c["id"] = i
        c["text"] = c["text"][:6000]
    return chunks


class RepoIndex:
    def __init__(self, chunks: list[dict], vectors: np.ndarray | None, embed_model: str | None):
        self.chunks = chunks
        self.vectors = vectors
        self.embed_model = embed_model
        docs = [tokenize(f"{c['path']} {c['text']}") for c in chunks]
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1
        df: Counter = Counter()
        for d in self.tf:
            df.update(d.keys())
        n = len(docs) or 1
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    # ---------------- persistence
    @staticmethod
    def dir_for(aid: str) -> Path:
        return get_settings().index_dir / aid

    def save(self, aid: str) -> None:
        d = self.dir_for(aid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "chunks.json").write_text(json.dumps(self.chunks))
        meta = {"embed_model": self.embed_model, "dense": self.vectors is not None}
        (d / "meta.json").write_text(json.dumps(meta))
        if self.vectors is not None:
            np.save(d / "vectors.npy", self.vectors)

    @classmethod
    def load(cls, aid: str) -> "RepoIndex | None":
        d = cls.dir_for(aid)
        if not (d / "chunks.json").exists():
            return None
        chunks = json.loads((d / "chunks.json").read_text())
        meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
        vec = np.load(d / "vectors.npy") if (d / "vectors.npy").exists() else None
        return cls(chunks, vec, meta.get("embed_model"))

    # ---------------- search
    def bm25(self, query: str, k: int) -> list[tuple[int, float]]:
        q = tokenize(query)
        if not q:
            return []
        k1, b = 1.5, 0.75
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf.get(t, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * self.len[i] / self.avg))
            if s:
                # small boost when query term appears in the path
                path = self.chunks[i]["path"].lower()
                if any(t in path for t in q):
                    s *= 1.25
                if re.search(r"(^|/)(tests?|__tests__|spec|testdata|fixtures)/|(_test|\.test|\.spec)\.\w+$|(^|/)test_", path):
                    s *= 0.6   # prefer implementation over tests
                elif path.endswith((".md", ".rst", ".txt")):
                    s *= 0.85
                scores.append((i, s))
        scores.sort(key=lambda x: -x[1])
        return scores[:k]

    def dense(self, query: str, k: int, cfg: LLMConfig) -> list[tuple[int, float]]:
        if self.vectors is None or not len(self.vectors):
            return []
        try:
            qv = np.array(embed([query], cfg)[0], dtype=np.float32)
        except LLMError:
            return []
        if qv.shape[0] != self.vectors.shape[1]:
            return []
        qv /= (np.linalg.norm(qv) or 1)
        sims = self.vectors @ qv
        idx = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in idx]

    def search(self, query: str, k: int = 8, cfg: LLMConfig | None = None) -> list[dict]:
        lists = [self.bm25(query, 40)]
        if cfg is not None and self.vectors is not None:
            lists.append(self.dense(query, 40, cfg))
        fused: dict[int, float] = {}
        for lst in lists:
            for rank, (i, _) in enumerate(lst):
                fused[i] = fused.get(i, 0) + 1 / (60 + rank)
        ranked = sorted(fused.items(), key=lambda x: -x[1])
        out, per_file = [], Counter()
        for i, s in ranked:
            c = self.chunks[i]
            if per_file[c["path"]] >= 2:
                continue
            per_file[c["path"]] += 1
            out.append({**c, "score": round(s * 1000, 2)})
            if len(out) >= k:
                break
        return out


def build_index(aid: str, contents: dict[str, str], priority: dict[str, float], cfg: LLMConfig | None,
                progress=None) -> dict:
    chunks = build_chunks(contents, priority)
    vectors = None
    note = "keyword (BM25) index"
    if cfg and (cfg.provider == "ollama" or cfg.compat) and cfg.embed_model and chunks:
        try:
            to_embed = chunks[:MAX_EMBED]
            embs: list[list[float]] = []
            batch = 32
            for s in range(0, len(to_embed), batch):
                part = to_embed[s:s + batch]
                embs += embed([f"File: {c['path']}\n{c['text'][:2000]}" for c in part], cfg)
                if progress:
                    progress(min(1.0, (s + batch) / len(to_embed)))
            arr = np.array(embs, dtype=np.float32)
            arr /= np.maximum(np.linalg.norm(arr, axis=1, keepdims=True), 1e-9)
            if len(arr) < len(chunks):  # chunks beyond MAX_EMBED: zero vectors (BM25 still finds them)
                arr = np.vstack([arr, np.zeros((len(chunks) - len(arr), arr.shape[1]), dtype=np.float32)])
            vectors = arr
            note = f"hybrid index (BM25 + {cfg.embed_model} embeddings)"
        except (LLMError, Exception) as e:  # noqa: BLE001
            note = f"keyword (BM25) index — embeddings unavailable: {str(e)[:120]}"
    idx = RepoIndex(chunks, vectors, cfg.embed_model if vectors is not None else None)
    idx.save(aid)
    _cache_put(aid, idx)
    return {"chunks": len(chunks), "dense": vectors is not None, "note": note}


_cache: "OrderedDict[str, RepoIndex]" = OrderedDict()
_cache_lock = threading.Lock()


def _cache_put(aid: str, idx: RepoIndex) -> None:
    with _cache_lock:
        _cache[aid] = idx
        _cache.move_to_end(aid)
        while len(_cache) > 6:
            _cache.popitem(last=False)


def get_index(aid: str) -> RepoIndex | None:
    with _cache_lock:
        if aid in _cache:
            _cache.move_to_end(aid)
            return _cache[aid]
    idx = RepoIndex.load(aid)
    if idx:
        _cache_put(aid, idx)
    return idx


def drop_index(aid: str) -> None:
    with _cache_lock:
        _cache.pop(aid, None)


RAG_SYSTEM = """You are RepoXray, an expert assistant answering questions about the GitHub repository "{repo}".
Use the retrieved code context and repository overview below. Cite files as `path:line` when you use them.
If the context is insufficient, say what is missing and suggest where to look. Use Markdown; keep code snippets short.

## Repository overview
{overview}

## Retrieved context
{context}"""


def answer_stream(question: str, history: list[dict], repo: str, overview: str, hits: list[dict], cfg: LLMConfig):
    ctx = "\n\n".join(f"### {h['path']}:{h['start']}-{h['end']}\n```\n{h['text'][:3000]}\n```" for h in hits)
    msgs = [{"role": "system", "content": RAG_SYSTEM.format(repo=repo, overview=overview[:4000], context=ctx[:cfg.context_budget(22000) - 3000])}]
    for m in history[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": str(m["content"])[:4000]})
    msgs.append({"role": "user", "content": question})
    yield from without_thinking(chat_stream(msgs, cfg, max_tokens=2000))


def fallback_answer(question: str, hits: list[dict], reason: str | None = None) -> str:
    if not hits:
        return ("No code matched that question. Try the names of functions, files or concepts.\n\n"
                "_Connect a model in **Settings** to get written answers._")
    lead = f"**The AI model could not be reached** ({reason})." if reason else "**No AI model is connected.**"
    out = [f"{lead} These are the most relevant code sections found by search:\n"]
    for h in hits[:5]:
        snippet = "\n".join(h["text"].splitlines()[:18])
        out.append(f"**`{h['path']}`** (lines {h['start']}–{h['end']})\n```\n{snippet}\n```")
    out.append("_Connect a model in **Settings** to get written answers._")
    return "\n".join(out)
