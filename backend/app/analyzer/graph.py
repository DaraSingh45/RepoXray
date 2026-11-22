"""Import/dependency graph, symbols, API routes and entry-point detection."""
from __future__ import annotations

import ast
import json
import posixpath
import re
from collections import Counter, defaultdict, deque

JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".vue", ".svelte")
JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[\w*{}\s,$]+\s+from\s+)?|export\s+(?:\*|\{[^}]*\})\s+from\s+|require\(\s*|import\(\s*)['"]([^'"]+)['"]"""
)
GO_IMPORT_BLOCK = re.compile(r"import\s*\((.*?)\)", re.S)
GO_IMPORT_SINGLE = re.compile(r'import\s+(?:\w+\s+)?"([^"]+)"')
JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?;", re.M)
JAVA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)", re.M)
C_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)
RUBY_REQ = re.compile(r"""^\s*require_relative\s+['"]([^'"]+)['"]""", re.M)
RUST_MOD = re.compile(r"^\s*(?:pub\s+)?mod\s+(\w+)\s*;", re.M)
RUST_USE = re.compile(r"^\s*(?:pub\s+)?use\s+crate::(\w+)", re.M)
PHP_REQ = re.compile(r"""(?:require|include)(?:_once)?\s*\(?\s*(?:__DIR__\s*\.\s*)?['"]([^'"]+)['"]""")


def _norm(p: str) -> str:
    return posixpath.normpath(p).lstrip("./") if p else p


class ImportGraph:
    def __init__(self, contents: dict[str, str], code_paths: set[str], extra: dict):
        self.contents = contents
        self.paths = code_paths
        self.extra = extra
        self.edges: Counter[tuple[str, str]] = Counter()
        self.external: dict[str, Counter] = defaultdict(Counter)  # file -> external packages
        self._py_modules = self._index_python()
        self._java_classes = self._index_java()
        simple: dict[str, list[str]] = defaultdict(list)
        for fq, path in self._java_classes.items():
            simple[fq.rsplit(".", 1)[-1]].append(path)
        self._java_simple = {k: v[0] for k, v in simple.items() if len(v) == 1}
        self._go_module = extra.get("go_module")
        self._aliases = self._ts_aliases()
        self._by_basename = defaultdict(list)
        for p in self.paths:
            self._by_basename[posixpath.basename(p)].append(p)

    # ------------------------------------------------------------ indexes
    def _index_python(self) -> dict[str, str]:
        idx: dict[str, str] = {}
        for p in self.paths:
            if not p.endswith(".py"):
                continue
            parts = p[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            # register every suffix so both "pkg.mod" and "src.pkg.mod" resolve
            for i in range(len(parts)):
                key = ".".join(parts[i:])
                if key:
                    idx.setdefault(key, p)
        return idx

    def _index_java(self) -> dict[str, str]:
        idx = {}
        for p in self.paths:
            if p.endswith((".java", ".kt")):
                m = JAVA_PACKAGE.search(self.contents.get(p, "")[:3000])
                cls = posixpath.splitext(posixpath.basename(p))[0]
                if m:
                    idx[f"{m.group(1)}.{cls}"] = p
        return idx

    def _ts_aliases(self) -> list[tuple[str, str]]:
        aliases: list[tuple[str, str]] = []
        for p, text in self.contents.items():
            if posixpath.basename(p) in ("tsconfig.json", "jsconfig.json", "tsconfig.app.json"):
                try:
                    clean = re.sub(r"//.*?$|/\*.*?\*/", "", text, flags=re.M | re.S)
                    clean = re.sub(r",(\s*[}\]])", r"\1", clean)
                    j = json.loads(clean)
                except Exception:
                    continue
                co = j.get("compilerOptions") or {}
                base = posixpath.join(posixpath.dirname(p), co.get("baseUrl") or ".")
                for alias, targets in (co.get("paths") or {}).items():
                    if targets:
                        aliases.append((alias.rstrip("*"), _norm(posixpath.join(base, targets[0].rstrip("*")))))
        # common default: "@/..." -> src/
        if not any(a == "@/" for a, _ in aliases):
            aliases.append(("@/", "src/"))
            aliases.append(("~/", "src/"))
        return aliases

    # ------------------------------------------------------------ resolution
    def _resolve_js(self, src: str, spec: str) -> str | None:
        base = None
        if spec.startswith("."):
            base = _norm(posixpath.join(posixpath.dirname(src), spec))
        else:
            for alias, target in self._aliases:
                if spec.startswith(alias):
                    base = _norm(target.rstrip("/") + "/" + spec[len(alias):])
                    break
        if base is None:
            return None
        cands = [base] + [base + e for e in JS_EXT] + [f"{base}/index{e}" for e in JS_EXT]
        for c in cands:
            if c in self.paths:
                return c
        # monorepo: alias target may be relative to a sub-package
        return None

    def _resolve_py(self, src: str, module: str, level: int) -> str | None:
        if level:
            pkg = posixpath.dirname(src).split("/") if posixpath.dirname(src) else []
            pkg = pkg[: len(pkg) - (level - 1)] if level > 1 else pkg
            parts = pkg + (module.split(".") if module else [])
            key = ".".join(p for p in parts if p)
            return self._py_modules.get(key) or (self._py_modules.get(".".join(parts[:-1])) if len(parts) > 1 else None)
        parts = module.split(".")
        while parts:
            hit = self._py_modules.get(".".join(parts))
            if hit:
                return hit
            parts = parts[:-1]
        return None

    # ------------------------------------------------------------ build
    def build(self) -> None:
        for p in self.paths:
            text = self.contents.get(p)
            if not text:
                continue
            try:
                if p.endswith(".py"):
                    self._py(p, text)
                elif p.endswith(JS_EXT):
                    for spec in JS_IMPORT.findall(text):
                        tgt = self._resolve_js(p, spec)
                        if tgt:
                            self._add(p, tgt)
                        elif not spec.startswith((".", "/")):
                            pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                            self.external[p][pkg] += 1
                elif p.endswith(".go"):
                    self._go(p, text)
                elif p.endswith((".java", ".kt")):
                    body = re.sub(r"//.*|/\*.*?\*/|\"(?:\\.|[^\"])*\"", "", text, flags=re.S)
                    for tok in set(re.findall(r"\b([A-Z][A-Za-z0-9_]+)\b", body)):
                        tgt = self._java_simple.get(tok)
                        if tgt and tgt != p:
                            self._add(p, tgt)
                    for imp in JAVA_IMPORT.findall(text):
                        tgt = self._java_classes.get(imp)
                        if tgt:
                            self._add(p, tgt)
                        else:
                            self.external[p][".".join(imp.split(".")[:2])] += 1
                elif p.endswith((".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh")):
                    for inc in C_INCLUDE.findall(text):
                        tgt = _norm(posixpath.join(posixpath.dirname(p), inc))
                        if tgt in self.paths:
                            self._add(p, tgt)
                        else:
                            cands = self._by_basename.get(posixpath.basename(inc), [])
                            if len(cands) == 1:
                                self._add(p, cands[0])
                elif p.endswith(".rb"):
                    for r in RUBY_REQ.findall(text):
                        tgt = _norm(posixpath.join(posixpath.dirname(p), r if r.endswith(".rb") else r + ".rb"))
                        if tgt in self.paths:
                            self._add(p, tgt)
                elif p.endswith(".rs"):
                    d = posixpath.dirname(p)
                    for mod in RUST_MOD.findall(text):
                        for c in (f"{d}/{mod}.rs", f"{d}/{mod}/mod.rs"):
                            c = _norm(c)
                            if c in self.paths:
                                self._add(p, c)
                    for mod in RUST_USE.findall(text):
                        for c in (f"src/{mod}.rs", f"src/{mod}/mod.rs"):
                            if c in self.paths:
                                self._add(p, c)
                elif p.endswith(".php"):
                    for r in PHP_REQ.findall(text):
                        tgt = _norm(posixpath.join(posixpath.dirname(p), r))
                        if tgt in self.paths:
                            self._add(p, tgt)
            except Exception:
                continue

    def _add(self, a: str, b: str) -> None:
        if a != b:
            self.edges[(a, b)] += 1

    def _py(self, p: str, text: str) -> None:
        try:
            tree = ast.parse(text)
        except Exception:
            for m in re.findall(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", text, re.M):
                mod = m[0] or m[1]
                tgt = self._resolve_py(p, mod, 0)
                if tgt:
                    self._add(p, tgt)
            return
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    tgt = self._resolve_py(p, a.name, 0)
                    if tgt:
                        self._add(p, tgt)
                    else:
                        self.external[p][a.name.split(".")[0]] += 1
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                tgt = None
                # `from pkg import submodule` -> prefer submodule file
                for a in node.names:
                    sub = self._resolve_py(p, f"{mod}.{a.name}" if mod else a.name, node.level)
                    if sub and sub.endswith(f"/{a.name}.py") or (sub and sub.endswith(f"{a.name}/__init__.py")):
                        self._add(p, sub)
                        tgt = tgt or sub
                if not tgt:
                    tgt = self._resolve_py(p, mod, node.level)
                    if tgt:
                        self._add(p, tgt)
                    elif node.level == 0 and mod:
                        self.external[p][mod.split(".")[0]] += 1

    def _go(self, p: str, text: str) -> None:
        imports = []
        for block in GO_IMPORT_BLOCK.findall(text):
            imports += re.findall(r'"([^"]+)"', block)
        imports += GO_IMPORT_SINGLE.findall(text)
        for imp in imports:
            if self._go_module and imp.startswith(self._go_module + "/"):
                d = imp[len(self._go_module) + 1:]
                prefix = (self.extra.get("go_root", "") + "/" + d).lstrip("/")
                for c in self.paths:
                    if c.endswith(".go") and posixpath.dirname(c) == prefix and not c.endswith("_test.go"):
                        self._add(p, c)
                        break
            elif "." in imp.split("/")[0]:
                self.external[p]["/".join(imp.split("/")[:3])] += 1


# ---------------------------------------------------------------- module aggregation

def _adaptive_groups(paths: list[str], max_modules: int) -> dict[str, str]:
    """Group files into modules by drilling into the biggest directories first.
    Collapses single-child chains like src/main/java/org/acme -> one step."""
    assign: dict[str, str] = {}
    for p in paths:
        parts = p.split("/")[:-1]
        assign[p] = parts[0] if parts else "(root)"

    def split(group: str) -> dict[str, str] | None:
        depth = len(group.split("/"))
        members = [p for p, g in assign.items() if g == group]
        newmap = {}
        for p in members:
            parts = p.split("/")[:-1]
            newmap[p] = "/".join(parts[: depth + 1]) if len(parts) > depth else group
        return newmap if len(set(newmap.values())) > 1 or set(newmap.values()) != {group} else None

    for _ in range(200):
        counts = Counter(assign.values())
        if len(counts) >= max_modules:
            break
        total = len(paths) or 1
        cands = [g for g, c in counts.most_common() if g != "(root)" and c > max(4, total * 0.18)]
        progressed = False
        for g in cands:
            nm = split(g)
            if not nm:
                continue
            new_groups = set(nm.values())
            if len(counts) - 1 + len(new_groups) > max_modules and len(new_groups) > 1:
                continue
            assign.update(nm)
            progressed = True
            break
        if not progressed:
            break
    return assign


def module_of(path: str, depth: int) -> str:
    parts = path.split("/")[:-1]
    return "/".join(parts[:depth]) if parts else "(root)"


def aggregate_modules(file_edges: Counter, files: list, max_modules: int = 30) -> dict:
    code_files = [f for f in files if f.is_code and not f.is_test]
    assign = _adaptive_groups([f.path for f in code_files], max_modules)
    nodes: dict[str, dict] = {}
    for f in code_files:
        m = assign[f.path]
        n = nodes.setdefault(m, {"id": m, "files": 0, "lines": 0, "languages": Counter(), "complexity": 0})
        n["files"] += 1
        n["lines"] += f.code_lines
        n["complexity"] += f.complexity
        n["languages"][f.language] += f.code_lines
    edges: Counter = Counter()
    for (a, b), w in file_edges.items():
        ma, mb = assign.get(a), assign.get(b)
        if ma and mb and ma != mb and ma in nodes and mb in nodes:
            edges[(ma, mb)] += w
    # keep graphs readable for very large repos
    if len(nodes) > max_modules:
        keep = {n for n, _ in sorted(((k, v["lines"]) for k, v in nodes.items()), key=lambda x: -x[1])[:max_modules]}
        nodes = {k: v for k, v in nodes.items() if k in keep}
        edges = Counter({k: v for k, v in edges.items() if k[0] in keep and k[1] in keep})
    for n in nodes.values():
        n["language"] = n["languages"].most_common(1)[0][0] if n["languages"] else None
        n["languages"] = dict(n["languages"])
        n["layer"] = classify_layer(n["id"])
        segs = n["id"].split("/")
        n["label"] = "/".join(segs[-2:]) if len(segs) > 2 else n["id"]
    return {
        "grouping": "adaptive",
        "nodes": list(nodes.values()),
        "edges": [{"source": a, "target": b, "weight": w} for (a, b), w in edges.most_common(150)],
    }


LAYER_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Tests", ("test", "tests", "spec", "specs", "__tests__", "e2e", "cypress", "testing")),
    ("Docs & Examples", ("docs", "doc", "examples", "example", "samples", "demo", "tutorial", "notebooks")),
    ("UI / Presentation", ("components", "component", "pages", "views", "templates", "ui", "frontend", "client",
                           "web", "public", "static", "screens", "layouts", "widgets", "styles", "assets", "app/(", "hooks")),
    ("API / Routing", ("api", "routes", "router", "routers", "controllers", "controller", "handlers", "endpoints",
                       "server", "graphql", "resolvers", "middleware", "middlewares", "rest", "cmd", "bin", "cli")),
    ("Business Logic", ("services", "service", "core", "domain", "usecases", "logic", "engine", "lib", "internal",
                        "pkg", "modules", "features", "agents", "pipeline", "analyzer", "workers", "jobs", "tasks")),
    ("Data & Models", ("models", "model", "db", "database", "schemas", "schema", "entities", "entity", "repositories",
                       "repository", "migrations", "store", "stores", "dao", "orm", "prisma", "data", "dataset", "datasets")),
    ("Utilities & Config", ("utils", "util", "helpers", "helper", "common", "shared", "config", "configs", "settings",
                            "constants", "types", "scripts", "tools", "infra", "deploy", "docker", "k8s")),
]


def classify_layer(path: str) -> str:
    """Classify by the most specific folder names (deepest first), so that
    org/acme/samples/owner is judged by 'owner', not by 'samples'."""
    segs = [s.lower() for s in path.split("/") if s]
    for seg in reversed(segs[-2:]):
        for layer, keys in LAYER_RULES:
            if seg in keys:
                return layer
    # top-level hints such as tests/ or docs/ anywhere near the root
    for seg in segs[:2]:
        for layer, keys in LAYER_RULES[:2]:
            if seg in keys:
                return layer
    return "Core"


# ---------------------------------------------------------------- symbols

def extract_symbols(path: str, text: str, limit: int = 60) -> list[dict]:
    out: list[dict] = []
    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    doc = (ast.get_docstring(node) or "").strip().split("\n")[0][:160]
                    methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] if kind == "class" else []
                    args = [a.arg for a in node.args.args] if kind == "function" else []  # type: ignore[union-attr]
                    out.append({"name": node.name, "kind": kind, "line": node.lineno, "end": getattr(node, "end_lineno", node.lineno),
                                "doc": doc, "methods": methods[:20], "args": args[:8]})
        except Exception:
            pass
        return out[:limit]
    patterns = []
    if path.endswith(JS_EXT):
        patterns = [
            (r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)", "function"),
            (r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)", "class"),
            (r"^\s*export\s+(?:const|let)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>", "function"),
            (r"^\s*export\s+(?:const|let)\s+(\w+)", "const"),
            (r"^\s*(?:export\s+)?(?:interface|type)\s+(\w+)", "type"),
            (r"^\s*(?:async\s+)?function\s+(\w+)", "function"),
        ]
    elif path.endswith(".go"):
        patterns = [(r"^func\s+(?:\([^)]*\)\s*)?(\w+)", "function"), (r"^type\s+(\w+)\s+(?:struct|interface)", "type")]
    elif path.endswith((".java", ".kt", ".cs", ".scala")):
        patterns = [(r"^\s*(?:public|internal|private)?\s*(?:abstract\s+|final\s+|data\s+|sealed\s+)*(?:class|interface|enum|object|record)\s+(\w+)", "class"),
                    (r"^\s+(?:public|protected|private|override|suspend|fun)\s+[\w<>\[\],\s]*?\s*(\w+)\s*\(", "function")]
    elif path.endswith(".rs"):
        patterns = [(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)", "function"),
                    (r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)", "type")]
    elif path.endswith(".rb"):
        patterns = [(r"^\s*class\s+(\w+)", "class"), (r"^\s*def\s+(?:self\.)?(\w+)", "function")]
    elif path.endswith(".php"):
        patterns = [(r"^\s*(?:abstract\s+|final\s+)?class\s+(\w+)", "class"), (r"function\s+(\w+)\s*\(", "function")]
    elif path.endswith((".c", ".cpp", ".cc", ".h", ".hpp")):
        patterns = [(r"^[\w\*\s:<>]+?\b(\w+)\s*\([^;]*\)\s*\{?\s*$", "function"), (r"^\s*(?:class|struct)\s+(\w+)", "class")]
    seen = set()
    for i, line in enumerate(text.splitlines()[:5000], 1):
        for rx, kind in patterns:
            m = re.match(rx, line)
            if m and m.group(1) not in seen and m.group(1) not in ("if", "for", "while", "switch", "return", "catch", "else", "new"):
                seen.add(m.group(1))
                out.append({"name": m.group(1), "kind": kind, "line": i, "doc": ""})
                break
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- API routes

ROUTE_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("Flask/FastAPI", re.compile(r"@(?:\w+)\.(get|post|put|patch|delete|route|websocket|api_route)\(\s*['\"]([^'\"]*)['\"](?:.*?methods\s*=\s*\[([^\]]*)\])?"), "py"),
    ("Django", re.compile(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]\s*,\s*([\w.]+)"), "dj"),
    ("Express/Koa", re.compile(r"\b(?:app|router|server|api|routes|r)\.(get|post|put|patch|delete|all|use)\(\s*['\"`](/[^'\"`]*)['\"`]"), "js"),
    ("NestJS", re.compile(r"@(Get|Post|Put|Patch|Delete)\(\s*['\"]?([^'\")]*)['\"]?\s*\)"), "nest"),
    ("Spring", re.compile(r"@(Get|Post|Put|Patch|Delete|Request)Mapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\"?([^\")]*)\"?"), "java"),
    ("Go", re.compile(r"\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete|HandleFunc|Handle)\(\s*\"(/[^\"]*)\""), "go"),
    ("Rails", re.compile(r"^\s*(get|post|put|patch|delete|resources?)\s+['\":]([\w/:]+)", re.M), "rb"),
    ("Laravel", re.compile(r"Route::(get|post|put|patch|delete|any|resource)\(\s*['\"]([^'\"]+)['\"]"), "php"),
    ("ASP.NET", re.compile(r"\[Http(Get|Post|Put|Patch|Delete)(?:\(\"([^\"]*)\"\))?\]"), "cs"),
    ("Next.js API", re.compile(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b"), "next"),
]


def extract_routes(contents: dict[str, str], limit: int = 300) -> list[dict]:
    routes: list[dict] = []
    for path, text in contents.items():
        ext = posixpath.splitext(path)[1]
        if ext not in (".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".java", ".kt", ".go", ".rb", ".php", ".cs"):
            continue
        if "test" in path.lower():
            continue
        for fw, rx, kind in ROUTE_PATTERNS:
            if kind == "py" and ext != ".py": continue
            if kind == "dj" and (ext != ".py" or "urls" not in path): continue
            if kind in ("js", "nest", "next") and ext not in (".js", ".ts", ".jsx", ".tsx", ".mjs"): continue
            if kind == "java" and ext not in (".java", ".kt"): continue
            if kind == "go" and ext != ".go": continue
            if kind == "rb" and not path.endswith("routes.rb"): continue
            if kind == "php" and ext != ".php": continue
            if kind == "cs" and ext != ".cs": continue
            if kind == "next" and not re.search(r"(^|/)app/.*route\.(t|j)s$", path): continue
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                if kind == "py":
                    method = m.group(1).upper()
                    if method in ("ROUTE", "API_ROUTE"):
                        method = ",".join(x.strip(" '\"").upper() for x in (m.group(3) or "GET").split(",")) or "GET"
                    route = m.group(2)
                elif kind == "dj":
                    method, route = "ANY", "/" + m.group(1)
                elif kind == "next":
                    method = m.group(1)
                    route = "/" + re.sub(r"^.*?app/|/?route\.(t|j)s$", "", path)
                elif kind == "cs":
                    method, route = m.group(1).upper(), m.group(2) or ""
                else:
                    method, route = m.group(1).upper(), m.group(2)
                if method == "USE" and kind == "js":
                    method = "MOUNT"
                if method == "HANDLEFUNC" or method == "HANDLE":
                    method = "ANY"
                routes.append({"method": method.replace("REQUEST", "ANY"), "path": route or "/", "file": path, "line": line, "framework": fw})
                if len(routes) >= limit:
                    return routes
    return routes


# ---------------------------------------------------------------- entry points

ENTRY_NAMES = {
    "main.py": 10, "app.py": 9, "manage.py": 9, "wsgi.py": 6, "asgi.py": 6, "server.py": 8, "run.py": 8, "cli.py": 6,
    "__main__.py": 9, "index.js": 7, "index.ts": 7, "server.js": 9, "server.ts": 9, "app.js": 8, "app.ts": 8,
    "main.js": 7, "main.ts": 8, "main.tsx": 9, "main.jsx": 9, "index.tsx": 8, "index.jsx": 8, "App.tsx": 6,
    "App.jsx": 6, "App.vue": 6, "main.go": 10, "main.rs": 10, "lib.rs": 6, "Main.java": 8, "Program.cs": 9,
    "main.c": 9, "main.cpp": 9, "train.py": 7, "bot.py": 7, "streamlit_app.py": 9, "main.dart": 9, "index.php": 7, "config.ru": 6, "Application.java": 9,
}


def find_entry_points(files: list, contents: dict[str, str], projects: list[dict], in_deg: Counter, out_deg: Counter) -> list[dict]:
    scores: dict[str, tuple[float, list[str]]] = {}

    def bump(p: str, s: float, why: str):
        cur, reasons = scores.get(p, (0.0, []))
        if why not in reasons:
            reasons = reasons + [why]
        scores[p] = (cur + s, reasons)

    paths = {f.path for f in files}
    for f in files:
        if not f.is_code or f.is_test:
            continue
        name = posixpath.basename(f.path)
        depth = f.path.count("/")
        if re.search(r"(^|/)(examples?|samples?|demos?|docs?|benchmarks?|scripts|testdata|fixtures)/", f.path):
            depth += 3
        if f.path.endswith(".py") and depth == 0 and in_deg.get(f.path, 0) == 0 and name not in ("setup.py", "conftest.py", "noxfile.py", "tasks.py"):
            bump(f.path, 3.5, "top-level script not imported elsewhere")
        if name in ENTRY_NAMES:
            bump(f.path, ENTRY_NAMES[name] - depth * 1.5, f"conventional entry file ({name})")
        if name.endswith("Application.java") or name.endswith("Application.kt"):
            bump(f.path, 8, "Spring Boot application class")
        text = contents.get(f.path, "")
        if f.path.endswith(".py") and "__name__" in text and re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", text):
            bump(f.path, 5 - depth, "has `if __name__ == '__main__'`")
        if f.path.endswith(".go") and re.search(r"^package main\b", text, re.M) and "func main()" in text:
            bump(f.path, 6, "Go `package main` with main()")
        if re.search(r"\b(app|server)\.listen\(|uvicorn\.run\(|app\.run\(|createRoot\(|ReactDOM\.render\(|new Vue\(|createApp\(|SpringApplication\.run|http\.ListenAndServe|bootstrapApplication|NestFactory\.create", text):
            bump(f.path, 5, "starts the application / server")
        if out_deg.get(f.path, 0) >= 3 and in_deg.get(f.path, 0) == 0:
            bump(f.path, 1.5, "imports many modules but is imported by none")
    for pr in projects:
        base = posixpath.dirname(pr["path"])
        for key in ("main",):
            v = pr.get(key)
            if isinstance(v, str):
                c = _norm(posixpath.join(base, v))
                for cand in (c, c + ".js", c + ".ts"):
                    if cand in paths:
                        bump(cand, 6, f"`{key}` in {pr['path']}")
        b = pr.get("bin")
        if isinstance(b, str):
            b = {"bin": b}
        if isinstance(b, dict):
            for v in b.values():
                c = _norm(posixpath.join(base, str(v)))
                if c in paths:
                    bump(c, 6, f"CLI `bin` in {pr['path']}")
        scripts = pr.get("scripts") or {}
        if isinstance(scripts, dict):
            for sname, cmd in scripts.items():
                if not isinstance(cmd, str):
                    continue
                if sname in ("start", "dev", "serve"):
                    for tok in cmd.split():
                        c = _norm(posixpath.join(base, tok))
                        if c in paths and c.endswith((".js", ".ts", ".mjs", ".py")):
                            bump(c, 5, f"`npm run {sname}` script")
                if ":" in cmd and pr["ecosystem"] == "pypi":
                    mod = cmd.split(":")[0].replace(".", "/")
                    for cand in (f"{mod}.py", f"src/{mod}.py", f"{mod}/__init__.py"):
                        if cand in paths:
                            bump(cand, 5, f"console script `{sname}`")
    ranked = sorted(scores.items(), key=lambda kv: -kv[1][0])
    return [{"path": p, "score": round(s, 1), "reasons": r} for p, (s, r) in ranked if s > 2][:8]


def bfs_flow(start: str, adj: dict[str, list[str]], max_nodes: int = 22, max_depth: int = 3) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    seen = {start}
    q = deque([(start, 0)])
    while q and len(seen) < max_nodes:
        node, d = q.popleft()
        if d >= max_depth:
            continue
        for nxt in adj.get(node, [])[:6]:
            edges.append((node, nxt))
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, d + 1))
                if len(seen) >= max_nodes:
                    break
    return edges
