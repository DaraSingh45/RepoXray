"""README understanding and run-command inference (no LLM required)."""
from __future__ import annotations

import html
import posixpath
import re


def find_readme(contents: dict[str, str]) -> tuple[str | None, str]:
    cands = [p for p in contents if re.match(r"(?i)^readme(\.(md|rst|txt|markdown))?$", p)]
    if not cands:
        cands = sorted((p for p in contents if re.search(r"(?i)(^|/)readme(\.(md|rst|txt))?$", p)), key=lambda p: p.count("/"))
    if not cands:
        return None, ""
    return cands[0], contents[cands[0]]


def clean_markdown(md: str) -> str:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)                 # images / badges
    md = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", md)
    md = re.sub(r"<img[^>]*>", "", md, flags=re.I)
    md = re.sub(r"</?(p|div|a|br|h\d|picture|source|sup|sub|details|summary)[^>]*>", "", md, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", md).strip()


SKIP_INTRO = re.compile(r"(?i)^(click|run|install|see|note|warning|read|check out|visit|this (?:repo|repository) (?:is|was) (?:archived|deprecated|moved)|table of contents|\$|npm |pip )|\bbutton\b|presentation here")


def readme_summary(md: str) -> dict:
    clean = clean_markdown(md)
    prose = re.sub(r"```.*?```", "", clean, flags=re.S)
    prose = html.unescape(re.sub(r"<[^>]+>", "", prose)).replace("\xa0", " ")
    headings = re.findall(r"^#{1,3}\s+(.+)$", clean, re.M)
    title = headings[0].strip() if headings else None
    paras = []
    headings_seen = 0
    for block in re.split(r"\n\s*\n", prose):
        b = block.strip()
        if b.startswith("#"):
            headings_seen += 1
            if headings_seen > 2 and paras:
                break
            if headings_seen > 3:
                break
        if not b or b.startswith(("#", "```", "|", "-", "*", ">", "=", "[", "{", "<", "    ")) or len(b) < 60 or SKIP_INTRO.search(b[:80]) \
                or re.search(r"\s{3,}", b) or sum(c.isalpha() for c in b) < len(b) * 0.6:
            continue
        paras.append(re.sub(r"\s+", " ", re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", b)))
        if len(paras) >= 2:
            break
    features = []
    m = re.search(r"^#{1,3}\s*(?:✨\s*)?(?:key\s+)?features?\b.*?$(.*?)(?=^#{1,3}\s|\Z)", clean, re.M | re.S | re.I)
    if m:
        features = [re.sub(r"\*\*|`|\[([^\]]+)\]\([^)]+\)", r"\1", f).strip() for f in re.findall(r"^\s*[-*]\s+(.+)$", m.group(1), re.M)][:10]
    code_blocks = re.findall(r"```(?:bash|sh|shell|console|zsh|powershell|cmd)?\n(.*?)```", md, re.S)
    commands = []
    for blk in code_blocks[:12]:
        for line in blk.splitlines():
            l = line.strip().lstrip("$> ").strip()
            if re.match(r"^(npm|yarn|pnpm|bun|pip|pip3|python|python3|poetry|uv|go|cargo|docker|docker-compose|make|git clone|mvn|gradle|\./gradlew|bundle|rails|php|composer|dotnet|flutter|deno|npx|conda)\b", l):
                commands.append(l[:160])
    return {"title": title, "intro": paras, "headings": headings[:30], "features": features,
            "commands": list(dict.fromkeys(commands))[:15], "length": len(md)}


def infer_commands(projects: list[dict], files: list, stack: list[dict], readme_cmds: list[str]) -> dict:
    names = {t["name"] for t in stack}
    paths = {f.path for f in files}
    cmds: dict[str, list[str]] = {"install": [], "build": [], "test": [], "run": [], "docker": []}

    def add(k: str, v: str):
        if v not in cmds[k]:
            cmds[k].append(v)

    # Prefer the shallowest project of each ecosystem
    for pr in sorted(projects, key=lambda p: p["path"].count("/")):
        base = posixpath.dirname(pr["path"])
        cd = f"cd {base} && " if base else ""
        if pr["ecosystem"] == "npm":
            pm = "pnpm" if any(p.endswith("pnpm-lock.yaml") for p in paths) else "yarn" if any(p.endswith("yarn.lock") for p in paths) else "bun" if any(p.startswith("bun.lock") for p in paths) else "npm"
            add("install", f"{cd}{pm} install")
            scripts = pr.get("scripts") or {}
            run = lambda s: f"{cd}{pm} run {s}" if pm in ("npm", "pnpm", "bun") else f"{cd}yarn {s}"  # noqa: E731
            for s in ("dev", "start", "serve"):
                if s in scripts:
                    add("run", run(s)); break
            if "build" in scripts:
                add("build", run("build"))
            if "test" in scripts and "no test specified" not in str(scripts["test"]):
                add("test", run("test"))
        elif pr["ecosystem"] == "pypi":
            if pr["path"].endswith("pyproject.toml"):
                add("install", f"{cd}pip install -e .")
            for s in (pr.get("scripts") or {}):
                add("run", f"{s} --help"); break
    for f in sorted(paths, key=lambda p: p.count("/")):
        n = posixpath.basename(f)
        d = posixpath.dirname(f)
        cd = f"cd {d} && " if d else ""
        if n.startswith("requirements") and n.endswith(".txt") and "dev" not in n:
            add("install", f"{cd}pip install -r {n}")
        elif n == "go.mod":
            add("install", f"{cd}go mod download"); add("build", f"{cd}go build ./..."); add("test", f"{cd}go test ./...")
        elif n == "Cargo.toml" and not d:
            add("build", "cargo build --release"); add("test", "cargo test"); add("run", "cargo run")
        elif n == "pom.xml" and not d:
            add("build", "mvn package"); add("test", "mvn test")
        elif n in ("build.gradle", "build.gradle.kts") and not d:
            add("build", "./gradlew build"); add("test", "./gradlew test")
        elif n == "Gemfile" and not d:
            add("install", "bundle install")
        elif n == "composer.json" and not d:
            add("install", "composer install")
        elif n == "pubspec.yaml" and not d:
            add("install", "flutter pub get"); add("run", "flutter run")
        elif n == "manage.py":
            add("run", f"{cd}python manage.py migrate && python manage.py runserver")
        elif n == "Makefile" and not d:
            add("build", "make")
        elif re.match(r"(docker-)?compose\.ya?ml$", n) and not d:
            add("docker", "docker compose up --build")
        elif n == "Dockerfile" and not d:
            add("docker", "docker build -t app . && docker run -p 8000:8000 app")
    if "pytest" in names:
        add("test", "pytest")
    if not cmds["run"]:
        for c in ("main.py", "app.py", "src/main.py", "server.py", "run.py", "bot.py"):
            if c in paths:
                add("run", f"python {c}")
                break
        if "Streamlit" in names:
            cand = next((p for p in paths if p.endswith(".py") and posixpath.basename(p) in ("app.py", "main.py", "streamlit_app.py")), None)
            if cand:
                cmds["run"].insert(0, f"streamlit run {cand}")
    if "Dockerfile" in {posixpath.basename(p) for p in paths} and not cmds["docker"]:
        df = next(p for p in sorted(paths, key=lambda x: x.count("/")) if posixpath.basename(p) == "Dockerfile")
        add("docker", f"docker build -f {df} -t app .")
    cmds["from_readme"] = readme_cmds
    return {k: v[:4] for k, v in cmds.items()}


def env_vars(contents: dict[str, str]) -> list[dict]:
    """Collect environment variables the code reads + documented in .env templates."""
    found: dict[str, dict] = {}
    rx = [
        re.compile(r"os\.environ(?:\.get)?\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"), re.compile(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
        re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"), re.compile(r"process\.env\.([A-Z][A-Z0-9_]{2,})"),
        re.compile(r"process\.env\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"), re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]{2,})"),
        re.compile(r"os\.Getenv\(\s*\"([A-Z][A-Z0-9_]{2,})\""), re.compile(r"env::var\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
        re.compile(r"ENV\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"), re.compile(r"getenv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    ]
    for path, text in contents.items():
        name = posixpath.basename(path)
        if re.match(r"\.env\.(example|sample|template|dist)$|^env\.example$", name):
            for m in re.finditer(r"^\s*([A-Z][A-Z0-9_]+)\s*=", text, re.M):
                found.setdefault(m.group(1), {"name": m.group(1), "files": [], "documented": False})["documented"] = True
            continue
        if not path.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".go", ".rs", ".rb", ".php")):
            continue
        for r in rx:
            for m in r.finditer(text):
                e = found.setdefault(m.group(1), {"name": m.group(1), "files": [], "documented": False})
                if path not in e["files"] and len(e["files"]) < 3:
                    e["files"].append(path)
    skip = {"NODE_ENV", "HOME", "PATH", "PWD", "USER", "CI"}
    return sorted((v for k, v in found.items() if k not in skip), key=lambda v: v["name"])[:80]
