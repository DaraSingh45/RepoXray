"""Human-readable insights: always computed heuristically, optionally enriched by an LLM."""
from __future__ import annotations

import posixpath
import re
from collections import Counter

from .providers import LLMConfig, LLMError, chat, parse_json

LAYER_ROLE = {
    "UI / Presentation": "renders the user interface",
    "API / Routing": "receives requests and routes them to handlers",
    "Business Logic": "implements the core logic",
    "Core": "contains core application code",
    "Data & Models": "defines data models and persistence",
    "Utilities & Config": "provides shared helpers and configuration",
    "Tests": "verifies behaviour with automated tests",
    "Docs & Examples": "documents usage with examples",
}


def heuristic(r: dict) -> dict:
    meta, stack, langs = r["meta"], r["stack"], r["languages"]
    readme = r.get("readme") or {}
    ptype = r["project_type"]
    main_lang = next((l["name"] for l in langs if l.get("is_code")), None)
    frameworks = [t["name"] for t in stack if t["category"] in ("Frontend", "Backend", "Mobile", "Desktop", "AI/ML")][:4]
    desc = meta.get("description") or (readme.get("intro") or [None])[0]
    summary = (desc.rstrip(".") + ". ") if desc else ""
    summary += f"It is a {ptype.lower()}"
    if main_lang:
        summary += f" written mainly in {main_lang}"
    if frameworks:
        summary += f", built with {', '.join(frameworks)}"
    summary += "."
    if r["metrics"]["source_files"]:
        summary += f" The codebase has {r['metrics']['source_files']} source files (~{r['metrics']['source_loc']:,} lines of code)."

    steps = []
    ep = r["entry_points"][0]["path"] if r["entry_points"] else None
    if ep:
        steps.append({"step": "Entry point", "detail": f"Execution starts in `{ep}` ({', '.join(r['entry_points'][0]['reasons'][:2])})."})
    layers = Counter(n["layer"] for n in r["modules"]["nodes"])
    for layer in ("UI / Presentation", "API / Routing", "Business Logic", "Core", "Data & Models", "Utilities & Config"):
        mods = [n["id"] for n in sorted(r["modules"]["nodes"], key=lambda n: -n["lines"]) if n["layer"] == layer][:3]
        if mods:
            steps.append({"step": layer, "detail": f"`{'`, `'.join(mods)}` {LAYER_ROLE[layer]}."})
    if r["routes"]:
        steps.append({"step": "HTTP API", "detail": f"Exposes {len(r['routes'])} HTTP endpoints, e.g. "
                      + ", ".join(f"`{x['method']} {x['path']}`" for x in r["routes"][:3]) + "."})
    ext = [t["name"] for t in stack if t["category"] in ("Database", "ORM", "Queue", "Cloud")]
    if ext:
        steps.append({"step": "Data & services", "detail": f"Persists / integrates with {', '.join(ext[:5])}."})
    if not steps:
        steps.append({"step": "Structure", "detail": "No clear executable entry point was found; this repository is likely a library, collection of scripts, or documentation."})

    central = sorted(r["file_degrees"].items(), key=lambda kv: -kv[1]["in"])[:8]
    key_components = []
    for path, deg in central:
        if deg["in"] == 0:
            continue
        syms = [s["name"] for s in r["symbols"].get(path, [])[:4]]
        key_components.append({"name": posixpath.basename(path), "path": path,
                               "role": f"Used by {deg['in']} file(s)" + (f"; defines {', '.join(syms)}" if syms else "")})
    if not key_components:
        for n in sorted(r["modules"]["nodes"], key=lambda n: -n["lines"])[:6]:
            key_components.append({"name": n["id"], "path": n["id"], "role": f"{n['layer']} · {n['files']} files"})

    path_to_learn = []
    if r.get("readme_path"):
        path_to_learn.append({"path": r["readme_path"], "why": "Project overview and setup"})
    for m in r["dependencies"]["manifests"][:2]:
        path_to_learn.append({"path": m["path"], "why": f"{m['ecosystem']} dependencies & scripts"})
    if ep:
        path_to_learn.append({"path": ep, "why": "Where execution begins"})
    for kc in key_components[:4]:
        if kc["path"] != ep and kc["path"] not in {p["path"] for p in path_to_learn}:
            path_to_learn.append({"path": kc["path"], "why": "Most-depended-on code"})
    tests = [f for f in r["files"] if f.get("test") and f.get("code")]
    if tests:
        path_to_learn.append({"path": tests[0]["path"], "why": "Tests show intended behaviour"})

    use_cases = readme.get("features")[:6] if readme.get("features") else []
    return {
        "source": "heuristic",
        "summary": summary,
        "purpose": desc or f"A {ptype.lower()}.",
        "audience": "Developers" if "Library" in ptype else "End users and developers",
        "use_cases": use_cases,
        "how_it_works": steps,
        "key_components": key_components[:8],
        "architecture": _arch_sentence(r),
        "learning_path": path_to_learn[:8],
        "improvements": [],
    }


def _arch_sentence(r: dict) -> str:
    layers = [l for l, _ in Counter(n["layer"] for n in r["modules"]["nodes"]).most_common() if l not in ("Tests", "Docs & Examples")]
    if not layers:
        return "Flat structure with no distinct architectural layers."
    style = "layered" if len(layers) >= 3 else "simple"
    if any(t["name"] in ("Docker Compose", "Kubernetes") for t in r["stack"]) and len(r["dependencies"]["projects"]) > 1:
        style = "multi-service"
    if len(r["dependencies"]["projects"]) > 2:
        style = "monorepo / multi-package"
    return f"A {style} architecture organised into: {', '.join(layers[:6])}."


SYSTEM = (
    "You are RepoXray, a senior software architect who explains codebases to students and engineers. "
    "Be concrete, cite real file paths from the context, never invent files or technologies. Reply with valid JSON only."
)

SCHEMA = """{
  "summary": "3-4 sentence plain-English overview of what the project is and does",
  "purpose": "the problem it solves, 1-2 sentences",
  "audience": "who would use it",
  "use_cases": ["concrete use case", "..."],
  "how_it_works": [{"step": "short title", "detail": "1-2 sentences referencing real files"}],
  "key_components": [{"name": "component", "path": "real/path", "role": "what it does"}],
  "architecture": "one paragraph describing the architecture and data flow",
  "learning_path": [{"path": "real/path", "why": "why read it at this point"}],
  "improvements": [{"title": "...", "detail": "specific, actionable suggestion referencing files", "priority": "high|medium|low", "category": "Architecture|Performance|Security|Testing|DX|Documentation|Code Quality"}],
  "mermaid": "a valid Mermaid 'flowchart TD' showing how data/control flows through the main components (max 14 nodes, ids alphanumeric, labels in double quotes)"
}"""


def build_context(r: dict, contents: dict[str, str], budget: int) -> str:
    parts: list[str] = []
    m = r["meta"]
    parts.append(f"# Repository: {m.get('full_name') or r['repo']}\nDescription: {m.get('description') or '-'}\n"
                 f"Type guess: {r['project_type']}\nStars: {m.get('stars')} | License: {m.get('license')}")
    parts.append("## Languages\n" + ", ".join(f"{l['name']} {l['percent']}%" for l in r["languages"][:8]))
    parts.append("## Detected stack\n" + ", ".join(f"{t['name']} ({t['category']})" for t in r["stack"][:40]))
    parts.append("## Entry points\n" + "\n".join(f"- {e['path']}: {', '.join(e['reasons'])}" for e in r["entry_points"][:5]))
    if r["routes"]:
        parts.append("## HTTP routes\n" + "\n".join(f"- {x['method']} {x['path']} ({x['file']})" for x in r["routes"][:25]))
    parts.append("## Modules (layer, files, loc)\n" + "\n".join(
        f"- {n['id']}: {n['layer']}, {n['files']} files, {n['lines']} loc" for n in sorted(r["modules"]["nodes"], key=lambda n: -n["lines"])[:25]))
    parts.append("## Module dependencies\n" + "\n".join(f"- {e['source']} -> {e['target']} ({e['weight']})" for e in r["modules"]["edges"][:30]))
    dirs = sorted({posixpath.dirname(f["path"]) for f in r["files"] if f.get("code")} - {""})[:80]
    parts.append("## Directories\n" + "\n".join(dirs))
    parts.append("## Rule-based findings\n" + "\n".join(f"- {i['title']}: {i['detail']}" for i in r["quality"]["improvements"][:10]))
    ctx = "\n\n".join(parts)
    readme = contents.get(r.get("readme_path") or "", "")
    if readme:
        ctx += "\n\n## README (truncated)\n" + readme[: min(7000, budget // 3)]
    # key file excerpts
    important = [e["path"] for e in r["entry_points"][:2]] + [p for p, _ in sorted(r["file_degrees"].items(), key=lambda kv: -kv[1]["in"])[:6]]
    for p in dict.fromkeys(important):
        if len(ctx) > budget:
            break
        t = contents.get(p)
        if t:
            ctx += f"\n\n## File: {p}\n```\n{t[:2500]}\n```"
    syms = []
    for p, ss in list(r["symbols"].items())[:60]:
        names = ", ".join(s["name"] for s in ss[:8])
        if names:
            syms.append(f"- {p}: {names}")
    ctx += "\n\n## Symbols\n" + "\n".join(syms)
    return ctx[:budget]


def llm_insights(r: dict, contents: dict[str, str], cfg: LLMConfig, budget: int) -> dict:
    ctx = build_context(r, contents, budget)
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Analyse this repository and respond ONLY with JSON matching this schema:\n{SCHEMA}\n\nCONTEXT:\n{ctx}"},
    ]
    raw = chat(msgs, cfg, json_mode=True, max_tokens=4000)
    data = parse_json(raw)
    if not data:
        raise LLMError("Model did not return valid JSON")
    return _sanitize(data, {f["path"] for f in r["files"]})


def _sanitize(d: dict, paths: set[str]) -> dict:
    def strl(v, n=10):
        return [str(x) for x in v][:n] if isinstance(v, list) else []

    def objs(v, keys, n=12):
        out = []
        if isinstance(v, list):
            for x in v[:n]:
                if isinstance(x, dict):
                    out.append({k: str(x.get(k, "")) for k in keys})
                elif isinstance(x, str):
                    out.append({keys[0]: x, **{k: "" for k in keys[1:]}})
        return out

    mer = d.get("mermaid") if isinstance(d.get("mermaid"), str) else ""
    mer = re.sub(r"^```(?:mermaid)?|```$", "", mer.strip(), flags=re.M).strip()
    if mer and not re.match(r"^(flowchart|graph)\s", mer):
        mer = ""
    lp = [x for x in objs(d.get("learning_path"), ["path", "why"]) if x["path"]]
    return {
        "source": "llm",
        "summary": str(d.get("summary") or ""),
        "purpose": str(d.get("purpose") or ""),
        "audience": str(d.get("audience") or ""),
        "use_cases": strl(d.get("use_cases")),
        "how_it_works": objs(d.get("how_it_works"), ["step", "detail"]),
        "key_components": objs(d.get("key_components"), ["name", "path", "role"]),
        "architecture": str(d.get("architecture") or ""),
        "learning_path": [dict(x, exists=x["path"] in paths) for x in lp],
        "improvements": objs(d.get("improvements"), ["title", "detail", "priority", "category"]),
        "mermaid": mer,
    }


LIST_MIN = {"how_it_works": 3, "key_components": 3, "learning_path": 3, "use_cases": 2}


def merge(base: dict, extra: dict | None) -> dict:
    """LLM output wins for prose; for lists it only wins when it is at least as useful as the heuristic."""
    if not extra:
        return base
    out = dict(base)
    if "learning_path" in extra:
        extra["learning_path"] = [x for x in extra["learning_path"] if x.get("exists", True)]
    if "key_components" in extra and base.get("key_components"):
        known = {c["path"] for c in base["key_components"]}
        extra["key_components"] = [c for c in extra["key_components"] if c.get("path")] or extra["key_components"]
    for k, v in extra.items():
        if not v:
            continue
        if isinstance(v, list) and k in LIST_MIN:
            if len(v) >= min(LIST_MIN[k], max(1, len(base.get(k) or []))):
                out[k] = v
        elif isinstance(v, str) and k in ("summary", "architecture") and len(v) < 40 and base.get(k):
            continue
        else:
            out[k] = v
    out["source"] = "llm"
    return out


def explain_file(path: str, text: str, symbols: list[dict], cfg: LLMConfig | None) -> tuple[str, str]:
    """Returns (markdown, source)."""
    if cfg and cfg.enabled:
        try:
            msgs = [
                {"role": "system", "content": "You explain source files to developers. Use concise Markdown with headings: Purpose, How it works, Key parts, Notes / possible improvements."},
                {"role": "user", "content": f"Explain `{path}`:\n```\n{text[:14000]}\n```"},
            ]
            return chat(msgs, cfg, max_tokens=1500), "llm"
        except LLMError:
            pass
    lines = text.count("\n") + 1
    md = [f"### `{path}`", f"{lines} lines."]
    if symbols:
        md.append("\n**Defines:**")
        for s in symbols[:25]:
            extra = f" — {s['doc']}" if s.get("doc") else ""
            md.append(f"- `{s['name']}` ({s['kind']}, line {s['line']}){extra}")
    head = [l.strip("#/*\"' ") for l in text.splitlines()[:15] if l.strip().startswith(("#", "//", "/*", "*", '"""'))]
    if head:
        md.append("\n**Header comments:** " + " ".join(h for h in head if h)[:400])
    md.append("\n_Connect an LLM in Settings for a full natural-language explanation._")
    return "\n".join(md), "heuristic"
