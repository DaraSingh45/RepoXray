"""Deterministic Mermaid diagram generation (works with no LLM at all)."""
from __future__ import annotations

import posixpath
import re
from collections import defaultdict

LAYER_HEX = {"UI / Presentation": "#7FB2F0", "API / Routing": "#4FC3C7", "Business Logic": "#C69BF2", "Core": "#9FD99A",
             "Data & Models": "#F0A04B", "Utilities & Config": "#8FA1BA", "Tests": "#6CCB8B", "Docs & Examples": "#EF8F8C"}
LAYER_ORDER = ["UI / Presentation", "API / Routing", "Core", "Business Logic", "Data & Models",
               "Utilities & Config", "Docs & Examples", "Tests"]


def _id(s: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", s)[:60] + f"_{abs(hash(s)) % 9973}"


def _files(n: int) -> str:
    return f"{n} file" if n == 1 else f"{n} files"


def _label(s: str) -> str:
    s = s.replace('"', "'").replace("<", "‹").replace(">", "›").replace("#", "").replace("`", "'")
    return s[:48] + "…" if len(s) > 48 else s


def architecture(modules: dict, stack: list[dict]) -> str:
    """Big-picture view: modules grouped in their layer, ONE labelled arrow per layer-to-layer dependency.
    (Module-to-module detail lives in the interactive architecture map, so this stays uncluttered.)"""
    nodes = modules.get("nodes", [])
    if not nodes:
        return ""
    layer_of = {n["id"]: n["layer"] for n in nodes}
    by_layer: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        if n["layer"] not in ("Tests", "Docs & Examples"):
            by_layer[n["layer"]].append(n)
    if not by_layer:
        for n in nodes:
            by_layer[n["layer"]].append(n)
    sid = lambda layer: "L_" + re.sub(r"\W", "", layer)  # noqa: E731
    lines = ["flowchart TB"]
    front = any(t["category"] in ("Frontend", "Mobile", "Desktop") for t in stack)
    lines.append(f'  user(["👤 {"User / Browser" if front else "User / Caller"}"])')
    present = [l for l in LAYER_ORDER if by_layer.get(l)]
    for layer in present:
        mods = sorted(by_layer[layer], key=lambda n: -n["lines"])
        shown, rest = mods[:5], mods[5:]
        rows = "".join(f'<br/><small>{_label(n.get("label") or n["id"])} · {_files(n["files"])}</small>' for n in shown)
        if rest:
            rows += f"<br/><small><i>+{len(rest)} more modules</i></small>"
        total = sum(n["lines"] for n in mods)
        lines.append(f'  {sid(layer)}["{layer}<br/><small>{total:,} lines of code</small>{rows}"]')
        lines.append(f"  class {sid(layer)} {sid(layer)}c")
    # aggregate imports between layers
    agg: dict[tuple[str, str], int] = defaultdict(int)
    for e in modules.get("edges", []):
        a_, b_ = layer_of.get(e["source"]), layer_of.get(e["target"])
        if a_ and b_ and a_ != b_ and a_ in present and b_ in present:
            agg[(a_, b_)] += e["weight"]
    lines.append(f"  user --> {sid(present[0])}")
    for (a_, b_), w in sorted(agg.items(), key=lambda kv: -kv[1])[:12]:
        arrow = "==>" if w >= 10 else "-->"
        lines.append(f'  {sid(a_)} {arrow}|"{w} import{"s" if w != 1 else ""}"| {sid(b_)}')
    ext = [t for t in stack if t["category"] in ("Database", "Queue", "Cloud", "AI/ML", "Payments", "Auth")][:6]
    data_layer = next((l for l in ("Data & Models", "Business Logic", "Core", "API / Routing") if by_layer.get(l)), present[-1])
    for t in ext:
        tid = _id("ext_" + t["name"])
        shape = f'[("{_label(t["name"])}")]' if t["category"] == "Database" else f'{{{{"{_label(t["name"])}"}}}}'
        lines.append(f"  {tid}{shape}")
        lines.append(f"  {sid(data_layer)} -.-> {tid}")
    for layer in present:
        lines.append(f"  classDef {sid(layer)}c fill:#15243A,stroke:{LAYER_HEX.get(layer, '#8FA1BA')},stroke-width:2px,color:#E7EEF6")
    lines.append("  classDef ext fill:#1f2937,stroke:#f59e0b,color:#fde68a")
    for t in ext:
        lines.append(f"  class {_id('ext_' + t['name'])} ext")
    return "\n".join(lines)


def execution_flow(entry: str | None, flow_edges: list[tuple[str, str]], symbols: dict[str, list[dict]]) -> str:
    if not entry:
        return ""
    lines = ["flowchart LR"]
    lines.append(f'  start(("▶ start")) --> {_id(entry)}')
    nodes = {entry} | {a for a, _ in flow_edges} | {b for _, b in flow_edges}
    for n in nodes:
        syms = [s["name"] for s in symbols.get(n, []) if s["kind"] in ("class", "function")][:3]
        sub = f"<br/><small>{', '.join(_label(s) for s in syms)}</small>" if syms else ""
        shape = ("[[", "]]") if n == entry else ("[", "]")
        lines.append(f'  {_id(n)}{shape[0]}"{_label(posixpath.basename(n))}<br/><small>{_label(posixpath.dirname(n) or "/")}</small>{sub}"{shape[1]}')
    for a, b in flow_edges:
        lines.append(f"  {_id(a)} --> {_id(b)}")
    lines.append(f"  classDef entry fill:#4c1d95,stroke:#a78bfa,color:#fff")
    lines.append(f"  class {_id(entry)} entry")
    return "\n".join(lines)


def request_lifecycle(stack: list[dict], routes: list[dict], modules: dict) -> str:
    names = {t["name"] for t in stack}
    cats = {t["category"] for t in stack}
    if "Backend" not in cats and not routes:
        return ""
    backend = next((t["name"] for t in stack if t["category"] == "Backend" and t["name"] not in ("Pydantic", "Uvicorn", "Gunicorn")), "Server")
    layers = {n["layer"] for n in modules.get("nodes", [])}
    db = next((t["name"] for t in stack if t["category"] == "Database"), None)
    orm = next((t["name"] for t in stack if t["category"] == "ORM"), None)
    front = next((t["name"] for t in stack if t["category"] in ("Frontend", "Mobile")), None)
    p = ["sequenceDiagram", "  autonumber"]
    p.append(f"  actor U as {'User' if front else 'Client'}")
    if front:
        p.append(f"  participant F as {front} UI")
    p.append(f"  participant R as {backend} router")
    if "Business Logic" in layers or "Core" in layers:
        p.append("  participant S as Services / logic")
    if db or orm or "Data & Models" in layers:
        p.append(f"  participant D as {(orm + ' → ') if orm else ''}{db or 'Data layer'}")
    ex = routes[0] if routes else {"method": "GET", "path": "/"}
    if front:
        p += ["  U->>F: interact", f"  F->>R: {ex['method'].split(',')[0]} {ex['path'][:40]}"]
    else:
        p.append(f"  U->>R: {ex['method'].split(',')[0]} {ex['path'][:40]}")
    if any(t["name"] in ("JWT", "Passport", "NextAuth", "Clerk") for t in stack):
        p.append("  R->>R: authenticate / validate")
    target = "S" if ("Business Logic" in layers or "Core" in layers) else None
    if target:
        p.append("  R->>S: call handler logic")
    if db or orm or "Data & Models" in layers:
        p.append(f"  {target or 'R'}->>D: query / persist")
        p.append(f"  D-->>{target or 'R'}: records")
    if target:
        p.append("  S-->>R: result")
    p.append(f"  R-->>{'F' if front else 'U'}: response ({'JSON' if 'API' in cats or routes else 'HTML'})")
    if front:
        p.append("  F-->>U: render update")
    return "\n".join(p)


def dev_lifecycle(projects: list[dict], stack: list[dict], files: list, commands: dict) -> str:
    names = {t["name"] for t in stack}
    lines = ["flowchart LR"]
    steps = [("clone", "📥 Clone repo")]
    if commands.get("install"):
        steps.append(("install", "📦 " + _label(commands["install"][0])))
    if any(f.path.endswith((".env.example", ".env.sample")) for f in files):
        steps.append(("env", "🔑 Configure .env"))
    if commands.get("build"):
        steps.append(("build", "🛠 " + _label(commands["build"][0])))
    if commands.get("test"):
        steps.append(("test", "🧪 " + _label(commands["test"][0])))
    if commands.get("run"):
        steps.append(("run", "🚀 " + _label(commands["run"][0])))
    for i, (sid, lab) in enumerate(steps):
        lines.append(f'  {sid}["{lab}"]')
        if i:
            lines.append(f"  {steps[i-1][0]} --> {sid}")
    last = steps[-1][0]
    if "Docker" in names or "Docker Compose" in names:
        lines.append(f'  docker["🐳 {_label(commands.get("docker", ["docker build"])[0])}"]')
        lines.append(f"  clone -.-> docker")
    ci = [n for n in names if n in ("GitHub Actions", "GitLab CI", "CircleCI", "Jenkins", "Travis CI")]
    if ci:
        lines.append(f'  ci{{{{"⚙ {ci[0]}"}}}}')
        lines.append(f"  {last} -.push.-> ci")
        hosts = [t["name"] for t in stack if t["category"] == "Hosting"]
        if hosts:
            lines.append(f'  deploy(["☁ {hosts[0]}"])')
            lines.append("  ci --> deploy")
    return "\n".join(lines)


def folder_mindmap(tree: dict, max_children: int = 8, max_depth: int = 3) -> str:
    lines = ["mindmap", f"  root(({_label(tree.get('repo', 'repo'))}))"]

    def walk(node: dict, depth: int):
        if depth > max_depth:
            return
        dirs = [c for c in node.get("children", []) if c["type"] == "dir"]
        dirs.sort(key=lambda c: -c.get("files", 0))
        for c in dirs[:max_children]:
            lines.append("  " * (depth + 1) + re.sub(r"[()\[\]{}]", "", c["name"]) or "dir")
            walk(c, depth + 1)

    walk(tree, 1)
    return "\n".join(lines) if len(lines) > 2 else ""
