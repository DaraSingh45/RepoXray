"""Orchestrates a full repository analysis, reporting progress step-by-step."""
from __future__ import annotations

import posixpath
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

from .. import db
from ..config import get_settings
from ..github import RepoError, RepoRef, fetch_metadata, fetch_repo
from ..llm import insights as ins
from ..llm.providers import LLMError, get_config
from ..rag.index import build_index
from . import deps as deps_mod
from . import docs, flows, gitinfo, graph, quality, scanner, stack as stack_mod

STEPS = [
    ("fetch", "Fetching repository"),
    ("scan", "Scanning files & languages"),
    ("deps", "Parsing dependencies"),
    ("stack", "Detecting tech stack"),
    ("graph", "Mapping code structure"),
    ("git", "Reading commit history"),
    ("quality", "Scoring quality & security"),
    ("diagrams", "Generating diagrams"),
    ("rag", "Building knowledge index (RAG)"),
    ("ai", "Generating AI insights"),
]
WEIGHTS = {"fetch": 15, "scan": 10, "deps": 8, "stack": 3, "graph": 12, "quality": 5, "git": 5, "diagrams": 2, "rag": 20, "ai": 20}


class Progress:
    def __init__(self, aid: str):
        self.aid = aid
        self.steps = [{"key": k, "label": l, "status": "pending", "detail": "", "ms": 0} for k, l in STEPS]
        self._t = 0.0
        self.cur: str | None = None

    def _pct(self, partial: float = 0.0) -> float:
        done = sum(WEIGHTS[s["key"]] for s in self.steps if s["status"] in ("done", "skipped"))
        cur = WEIGHTS.get(self.cur or "", 0) * partial
        return round(min(99.0, (done + cur) / sum(WEIGHTS.values()) * 100), 1)

    def start(self, key: str, detail: str = ""):
        self.cur = key
        self._t = time.time()
        for s in self.steps:
            if s["key"] == key:
                s["status"] = "running"; s["detail"] = detail
        db.update_analysis(self.aid, status="running", step=key, steps=self.steps, progress=self._pct())

    def sub(self, frac: float, detail: str = ""):
        for s in self.steps:
            if s["key"] == self.cur and detail:
                s["detail"] = detail
        db.update_analysis(self.aid, progress=self._pct(frac), steps=self.steps)

    def done(self, detail: str = "", status: str = "done"):
        for s in self.steps:
            if s["key"] == self.cur:
                s["status"] = status; s["ms"] = int((time.time() - self._t) * 1000)
                if detail:
                    s["detail"] = detail
        db.update_analysis(self.aid, steps=self.steps, progress=self._pct())


def run(aid: str, ref: RepoRef, use_llm: bool = True) -> None:
    s = get_settings()
    p = Progress(aid)
    try:
        # 1. fetch ------------------------------------------------------------
        p.start("fetch", f"github.com/{ref.full_name}")
        meta = fetch_metadata(ref)
        dest = s.repos_dir / aid
        fetch_info = fetch_repo(ref, dest, meta)
        root = dest / ref.subpath if ref.subpath and (dest / ref.subpath).is_dir() else dest
        p.done(f"via {fetch_info['method']} · branch {fetch_info.get('branch') or 'default'}")

        # 2. scan -------------------------------------------------------------
        p.start("scan")
        sc = scanner.scan(root, s.max_files, s.max_file_bytes)
        files = sc.files
        contents = sc.contents
        langs = scanner.language_breakdown(files)
        tree = scanner.build_tree(files)
        tree["repo"] = ref.repo
        p.done(f"{len(files)} files" + (" (truncated)" if sc.truncated else ""))

        # 3. deps -------------------------------------------------------------
        p.start("deps")
        dep_info = deps_mod.collect(contents)
        if s.check_outdated and dep_info["dependencies"]:
            p.sub(0.3, f"Checking {min(60, len(dep_info['dependencies']))} packages against registries")
            deps_mod.check_outdated(dep_info["dependencies"])
        p.done(f"{len(dep_info['dependencies'])} dependencies in {len(dep_info['manifests'])} manifests")

        # 4. stack ------------------------------------------------------------
        p.start("stack")
        stack = stack_mod.detect(files, dep_info["dependencies"], langs, contents)
        ptype = stack_mod.project_type(stack, files, dep_info["projects"])
        p.done(f"{len(stack)} technologies · {ptype}")

        # 5. graph ------------------------------------------------------------
        p.start("graph")
        code_paths = {f.path for f in files if f.is_code and f.path in contents}
        extra = {}
        for pr in dep_info["projects"]:
            if pr["ecosystem"] == "go" and pr.get("name"):
                extra = {"go_module": pr["name"], "go_root": posixpath.dirname(pr["path"])}
                break
        g = graph.ImportGraph(contents, code_paths, extra)
        g.build()
        in_deg, out_deg = Counter(), Counter()
        adj: dict[str, list[str]] = defaultdict(list)
        for (a, b), w in g.edges.most_common():
            in_deg[b] += 1; out_deg[a] += 1
            adj[a].append(b)
        p.sub(0.5, "Extracting symbols & routes")
        symbols = {}
        for path in sorted(code_paths, key=lambda x: -in_deg.get(x, 0))[:1500]:
            syms = graph.extract_symbols(path, contents[path])
            if syms:
                symbols[path] = syms
        routes = graph.extract_routes(contents)
        entries = graph.find_entry_points(files, contents, dep_info["projects"], in_deg, out_deg)
        modules = graph.aggregate_modules(g.edges, files)
        file_graph = _file_graph(g.edges, files, in_deg, out_deg)
        ext_usage: Counter = Counter()
        for f_, c in g.external.items():
            for pkg in c:
                ext_usage[pkg] += 1
        p.done(f"{len(g.edges)} import links · {len(routes)} routes · {len(entries)} entry points")

        # 6. git (before quality: churn feeds hotspots) ------------------------
        p.start("git")
        try:
            git = gitinfo.collect(dest)
        except Exception:
            traceback.print_exc()
            git = {"available": False, "contributors": None}
        p.done(f"{git.get('commit_count', 0)} commits" if git.get("available") else "history unavailable",
               "done" if git.get("available") else "skipped")

        # 7. quality ----------------------------------------------------------
        p.start("quality")
        todos = [{"path": f.path, "line": l, "kind": k, "text": t} for f in files for (l, k, t) in f.todos][:200]
        sec = quality.security_scan(files, contents)
        q = quality.evaluate(files, contents, dep_info["dependencies"], stack, meta, git, sec, langs, todos)
        p.done(f"score {q['score']}/100 · {len(sec)} security findings")

        # 8. diagrams ---------------------------------------------------------
        p.start("diagrams")
        readme_path, readme_text = docs.find_readme(contents)
        readme = docs.readme_summary(readme_text) if readme_text else {}
        commands = docs.infer_commands(dep_info["projects"], files, stack, readme.get("commands", []))
        entry = entries[0]["path"] if entries else None
        if entry and not commands["run"]:
            if entry.endswith(".py"):
                commands["run"].append(f"python {entry}")
            elif entry.endswith((".js", ".mjs")):
                commands["run"].append(f"node {entry}")
            elif entry.endswith(".go"):
                commands["run"].append(f"go run ./{posixpath.dirname(entry)}".rstrip("/").replace("./.", "."))
        diagrams = {
            "architecture": flows.architecture(modules, stack),
            "execution": flows.execution_flow(entry, graph.bfs_flow(entry, adj) if entry else [], symbols),
            "request": flows.request_lifecycle(stack, routes, modules),
            "lifecycle": flows.dev_lifecycle(dep_info["projects"], stack, files, commands),
            "mindmap": flows.folder_mindmap(tree),
        }
        p.done(f"{sum(1 for v in diagrams.values() if v)} diagrams")

        metrics = {
            "files": len(files), "total_files": sc.total_files, "truncated": sc.truncated,
            "source_files": q["stats"]["source_files"], "test_files": q["stats"]["test_files"],
            "source_loc": q["stats"]["source_loc"], "test_loc": q["stats"]["test_loc"],
            "total_lines": sum(f.lines for f in files), "size_bytes": sum(f.size for f in files),
            "functions": sum(f.functions for f in files if f.is_code),
            "avg_complexity": round(sum(f.complexity for f in files if f.is_code) / max(1, sum(1 for f in files if f.is_code)), 1),
            "dirs": len({posixpath.dirname(f.path) for f in files}),
            "comment_ratio": q["stats"]["comment_ratio"], "test_ratio": q["stats"]["test_ratio"],
        }
        result = {
            "repo": ref.full_name, "url": ref.canonical_url, "subpath": ref.subpath, "fetch": fetch_info,
            "meta": meta, "project_type": ptype, "metrics": metrics, "languages": langs, "tree": tree,
            "files": [{"path": f.path, "size": f.size, "language": f.language, "lines": f.code_lines, "complexity": f.complexity,
                       "test": f.is_test, "code": f.is_code, "binary": f.is_binary, "in": in_deg.get(f.path, 0),
                       "out": out_deg.get(f.path, 0)} for f in files],
            "dependencies": dep_info, "external_imports": [{"name": k, "files": v} for k, v in ext_usage.most_common(40)],
            "stack": stack, "modules": modules, "file_graph": file_graph, "entry_points": entries, "routes": routes,
            "symbols": symbols, "file_degrees": {k: {"in": in_deg.get(k, 0), "out": out_deg.get(k, 0)} for k in code_paths},
            "git": {k: v for k, v in git.items() if k != "churn"}, "quality": q, "security": sec, "todos": todos,
            "readme": readme, "readme_path": readme_path, "commands": commands, "env_vars": docs.env_vars(contents),
            "diagrams": diagrams, "skipped_dirs": sc.skipped_dirs,
        }
        result["insights"] = ins.heuristic(result)
        db.update_analysis(aid, result=result)  # partial result is viewable while AI steps run

        # 9. RAG --------------------------------------------------------------
        cfg = get_config()
        llm_on = use_llm and cfg.enabled
        p.start("rag")
        test_paths = {f.path for f in files if f.is_test}
        code_set = {f.path for f in files if f.is_code}
        priority = {pth: (in_deg.get(pth, 0) * 3 + (8 if pth == entry else 0) + (6 if pth == readme_path else 0)
                          + (2 if pth in code_set else 0) - (3 if pth in test_paths else 0)) for pth in contents}
        rag = build_index(aid, contents, priority, cfg if (llm_on and cfg.embed_model) else None,
                          progress=lambda fr: p.sub(fr, f"Embedding chunks… {int(fr * 100)}%"))
        result["rag"] = rag
        p.done(f"{rag['chunks']} chunks · {rag['note']}")

        # 10. AI insights -----------------------------------------------------
        p.start("ai", f"{cfg.provider} · {cfg.model}" if llm_on else "")
        if llm_on:
            try:
                extra_ins = ins.llm_insights(result, contents, cfg, cfg.context_budget(s.llm_context_chars))
                result["insights"] = ins.merge(result["insights"], extra_ins)
                result["insights"]["model"] = f"{cfg.provider}/{cfg.model}"
                if extra_ins.get("mermaid"):
                    result["diagrams"]["ai_flow"] = extra_ins["mermaid"]
                p.done(f"by {cfg.model}")
            except LLMError as e:
                result["insights"]["llm_error"] = str(e)
                p.done(f"LLM unavailable — using heuristic insights ({str(e)[:80]})", "skipped")
        else:
            p.done("LLM disabled — heuristic insights", "skipped")

        result["finished_at"] = time.time()
        db.update_analysis(aid, result=result, status="done", progress=100, step="done", steps=p.steps)
    except RepoError as e:
        _fail(aid, p, str(e))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _fail(aid, p, f"Unexpected error: {type(e).__name__}: {e}")


def _fail(aid: str, p: Progress, msg: str) -> None:
    for s in p.steps:
        if s["status"] == "running":
            s["status"] = "failed"
    db.update_analysis(aid, status="failed", error=msg, steps=p.steps)


def _file_graph(edges: Counter, files: list, in_deg: Counter, out_deg: Counter, limit: int = 220) -> dict:
    """Top files by connectivity for the interactive file-level graph."""
    by = {f.path: f for f in files}
    score = Counter()
    for (a, b), w in edges.items():
        score[a] += w; score[b] += w
    keep = {p for p, _ in score.most_common(limit)}
    nodes = [{"id": p, "language": by[p].language if p in by else None, "lines": by[p].code_lines if p in by else 0,
              "in": in_deg.get(p, 0), "out": out_deg.get(p, 0), "layer": graph.classify_layer(posixpath.dirname(p)),
              "test": by[p].is_test if p in by else False} for p in keep]
    es = [{"source": a, "target": b, "weight": w} for (a, b), w in edges.items() if a in keep and b in keep]
    return {"nodes": nodes, "edges": es[:900], "total_edges": len(edges)}
