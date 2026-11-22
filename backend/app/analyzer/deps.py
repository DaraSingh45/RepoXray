"""Manifest parsing for many ecosystems + optional 'outdated' check against public registries."""
from __future__ import annotations

import json
import re
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath

import httpx
import yaml


def _dep(name: str, spec: str, eco: str, manifest: str, dev: bool = False) -> dict:
    return {"name": name.strip(), "spec": (spec or "").strip() or "*", "ecosystem": eco, "manifest": manifest, "dev": dev}


def parse_package_json(text: str, path: str) -> tuple[list[dict], dict]:
    try:
        j = json.loads(text)
    except Exception:
        return [], {}
    if not isinstance(j, dict):
        return [], {}
    deps = []
    for key, dev in (("dependencies", False), ("devDependencies", True), ("peerDependencies", False),
                     ("optionalDependencies", False)):
        for n, v in (j.get(key) or {}).items():
            deps.append(_dep(n, str(v), "npm", path, dev))
    info = {
        "name": j.get("name"), "version": j.get("version"), "description": j.get("description"),
        "scripts": j.get("scripts") or {}, "main": j.get("main"), "bin": j.get("bin"),
        "workspaces": j.get("workspaces"), "engines": j.get("engines"), "type": j.get("type"),
    }
    return deps, info


REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*([<>=!~^].*)?$")


def parse_requirements(text: str, path: str) -> list[dict]:
    deps = []
    dev = any(k in path.lower() for k in ("dev", "test", "lint", "doc"))
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith(("-", "git+", "http")):
            continue
        line = line.split(";")[0].strip()
        m = REQ_LINE.match(line)
        if m:
            deps.append(_dep(re.sub(r"\[.*\]", "", m.group(1)), m.group(2) or "", "pypi", path, dev))
    return deps


def _pep508(s: str) -> tuple[str, str]:
    s = s.split(";")[0].strip()
    m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*\(?([^)]*)\)?", s)
    return (m.group(1), m.group(3).strip()) if m else (s, "")


def parse_pyproject(text: str, path: str) -> tuple[list[dict], dict]:
    try:
        t = tomllib.loads(text)
    except Exception:
        return [], {}
    deps: list[dict] = []
    proj = t.get("project") or {}
    for d in proj.get("dependencies") or []:
        n, v = _pep508(d)
        deps.append(_dep(n, v, "pypi", path))
    for group, items in (proj.get("optional-dependencies") or {}).items():
        for d in items or []:
            n, v = _pep508(d)
            deps.append(_dep(n, v, "pypi", path, True))
    for group, items in (t.get("dependency-groups") or {}).items():
        for d in items or []:
            if isinstance(d, str):
                n, v = _pep508(d)
                deps.append(_dep(n, v, "pypi", path, True))
    poetry = (t.get("tool") or {}).get("poetry") or {}
    for key, dev in (("dependencies", False), ("dev-dependencies", True)):
        for n, v in (poetry.get(key) or {}).items():
            if n.lower() == "python":
                continue
            deps.append(_dep(n, v if isinstance(v, str) else (v or {}).get("version", "") if isinstance(v, dict) else "", "pypi", path, dev))
    for gname, g in (poetry.get("group") or {}).items():
        for n, v in ((g or {}).get("dependencies") or {}).items():
            deps.append(_dep(n, v if isinstance(v, str) else "", "pypi", path, True))
    info = {
        "name": proj.get("name") or poetry.get("name"), "version": proj.get("version") or poetry.get("version"),
        "description": proj.get("description") or poetry.get("description"),
        "scripts": proj.get("scripts") or poetry.get("scripts") or {},
        "requires_python": proj.get("requires-python"),
        "build_backend": (t.get("build-system") or {}).get("build-backend"),
    }
    return deps, info


def parse_setup_py(text: str, path: str) -> list[dict]:
    m = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.S)
    if not m:
        return []
    return [_dep(*_pep508(s), "pypi", path) for s in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))]


def parse_pipfile(text: str, path: str) -> list[dict]:
    try:
        t = tomllib.loads(text)
    except Exception:
        return []
    out = []
    for key, dev in (("packages", False), ("dev-packages", True)):
        for n, v in (t.get(key) or {}).items():
            out.append(_dep(n, v if isinstance(v, str) else "", "pypi", path, dev))
    return out


def parse_go_mod(text: str, path: str) -> tuple[list[dict], dict]:
    deps = []
    module = re.search(r"^module\s+(\S+)", text, re.M)
    gov = re.search(r"^go\s+(\S+)", text, re.M)
    block = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("require ("):
            block = True
            continue
        if block and s == ")":
            block = False
            continue
        m = re.match(r"^(?:require\s+)?([\w.\-/]+\.[\w.\-/]+)\s+(v[\w.\-+]+)(\s*//\s*indirect)?", s)
        if (block or s.startswith("require ")) and m:
            deps.append(_dep(m.group(1), m.group(2), "go", path, bool(m.group(3))))
    return deps, {"name": module.group(1) if module else None, "go_version": gov.group(1) if gov else None}


def parse_cargo(text: str, path: str) -> tuple[list[dict], dict]:
    try:
        t = tomllib.loads(text)
    except Exception:
        return [], {}
    deps = []
    for key, dev in (("dependencies", False), ("dev-dependencies", True), ("build-dependencies", True)):
        for n, v in (t.get(key) or {}).items():
            deps.append(_dep(n, v if isinstance(v, str) else (v or {}).get("version", "") if isinstance(v, dict) else "", "crates", path, dev))
    pkg = t.get("package") or {}
    return deps, {"name": pkg.get("name"), "version": pkg.get("version"), "description": pkg.get("description"),
                  "workspace": bool(t.get("workspace"))}


def parse_pom(text: str, path: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<dependency>(.*?)</dependency>", text, re.S):
        b = m.group(1)
        g = re.search(r"<groupId>(.*?)</groupId>", b)
        a = re.search(r"<artifactId>(.*?)</artifactId>", b)
        v = re.search(r"<version>(.*?)</version>", b)
        sc = re.search(r"<scope>(.*?)</scope>", b)
        if a:
            out.append(_dep(f"{g.group(1) if g else ''}:{a.group(1)}", v.group(1) if v else "", "maven", path,
                            bool(sc and sc.group(1) == "test")))
    return out


def parse_gradle(text: str, path: str) -> list[dict]:
    out = []
    for m in re.finditer(r"(implementation|api|compileOnly|runtimeOnly|testImplementation|kapt|ksp)\s*\(?\s*['\"]([^'\"]+)['\"]", text):
        parts = m.group(2).split(":")
        if len(parts) >= 2:
            out.append(_dep(":".join(parts[:2]), parts[2] if len(parts) > 2 else "", "maven", path,
                            m.group(1).startswith("test")))
    return out


def parse_gemfile(text: str, path: str) -> list[dict]:
    return [_dep(m.group(1), m.group(2) or "", "rubygems", path)
            for m in re.finditer(r"^\s*gem\s+['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?", text, re.M)]


def parse_composer(text: str, path: str) -> list[dict]:
    try:
        j = json.loads(text)
    except Exception:
        return []
    out = []
    for key, dev in (("require", False), ("require-dev", True)):
        for n, v in (j.get(key) or {}).items():
            if n != "php" and not n.startswith("ext-"):
                out.append(_dep(n, str(v), "packagist", path, dev))
    return out


def parse_pubspec(text: str, path: str) -> list[dict]:
    try:
        y = yaml.safe_load(text) or {}
    except Exception:
        return []
    out = []
    for key, dev in (("dependencies", False), ("dev_dependencies", True)):
        for n, v in (y.get(key) or {}).items():
            out.append(_dep(n, v if isinstance(v, str) else "", "pub", path, dev))
    return out


def parse_csproj(text: str, path: str) -> list[dict]:
    return [_dep(m.group(1), m.group(2), "nuget", path)
            for m in re.finditer(r'<PackageReference\s+Include="([^"]+)"(?:\s+Version="([^"]*)")?', text)]


def collect(contents: dict[str, str]) -> dict:
    """Parse every manifest in the repo (supports monorepos)."""
    deps: list[dict] = []
    manifests: list[dict] = []
    projects: list[dict] = []
    for path, text in contents.items():
        name = PurePosixPath(path).name
        low = name.lower()
        parsed: list[dict] = []
        info: dict = {}
        eco = None
        try:
            if name == "package.json":
                parsed, info = parse_package_json(text, path); eco = "npm"
            elif low.startswith("requirements") and low.endswith((".txt", ".in")):
                parsed = parse_requirements(text, path); eco = "pypi"
            elif name == "pyproject.toml":
                parsed, info = parse_pyproject(text, path); eco = "pypi"
            elif name == "setup.py":
                parsed = parse_setup_py(text, path); eco = "pypi"
            elif name == "Pipfile":
                parsed = parse_pipfile(text, path); eco = "pypi"
            elif name == "go.mod":
                parsed, info = parse_go_mod(text, path); eco = "go"
            elif name == "Cargo.toml":
                parsed, info = parse_cargo(text, path); eco = "crates"
            elif name == "pom.xml":
                parsed = parse_pom(text, path); eco = "maven"
            elif name in ("build.gradle", "build.gradle.kts"):
                parsed = parse_gradle(text, path); eco = "maven"
            elif name == "Gemfile":
                parsed = parse_gemfile(text, path); eco = "rubygems"
            elif name == "composer.json":
                parsed = parse_composer(text, path); eco = "packagist"
            elif name == "pubspec.yaml":
                parsed = parse_pubspec(text, path); eco = "pub"
            elif low.endswith((".csproj", ".fsproj")):
                parsed = parse_csproj(text, path); eco = "nuget"
        except Exception:
            parsed, info = [], {}
        if eco:
            manifests.append({"path": path, "ecosystem": eco, "count": len(parsed)})
            deps.extend(parsed)
            if info:
                projects.append({"path": path, "ecosystem": eco, **{k: v for k, v in info.items() if v}})
    # de-duplicate by (eco, name, manifest)
    seen = set()
    uniq = []
    for d in deps:
        k = (d["ecosystem"], d["name"].lower(), d["manifest"])
        if k not in seen and d["name"]:
            seen.add(k)
            uniq.append(d)
    return {"dependencies": uniq, "manifests": manifests, "projects": projects}


# ---------------------------------------------------------------- outdated check

VER_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _ver(s: str | None) -> tuple[int, int, int] | None:
    if not s:
        return None
    m = VER_RE.search(s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)


def _latest(client: httpx.Client, d: dict) -> str | None:
    n, eco = d["name"], d["ecosystem"]
    try:
        if eco == "pypi":
            r = client.get(f"https://pypi.org/pypi/{n}/json")
            return r.json()["info"]["version"] if r.status_code == 200 else None
        if eco == "npm":
            r = client.get(f"https://registry.npmjs.org/{n.replace('/', '%2F')}/latest")
            return r.json().get("version") if r.status_code == 200 else None
        if eco == "crates":
            r = client.get(f"https://crates.io/api/v1/crates/{n}")
            return r.json()["crate"]["max_stable_version"] if r.status_code == 200 else None
        if eco == "go":
            r = client.get(f"https://proxy.golang.org/{n.lower()}/@latest")
            return r.json().get("Version") if r.status_code == 200 else None
    except Exception:
        return None
    return None


def check_outdated(deps: list[dict], limit: int = 60) -> list[dict]:
    """Annotates deps with latest version + status. Silently skips on network failure."""
    candidates = [d for d in deps if d["ecosystem"] in ("pypi", "npm", "crates", "go")
                  and not d["spec"].startswith(("file:", "link:", "workspace:", "git", "http", "github:"))]
    # prioritise runtime deps
    candidates.sort(key=lambda d: d["dev"])
    candidates = candidates[:limit]
    if not candidates:
        return deps
    try:
        with httpx.Client(timeout=6, headers={"User-Agent": "RepoXray (repo analyzer)"}, follow_redirects=True) as c:
            with ThreadPoolExecutor(max_workers=12) as ex:
                latest = list(ex.map(lambda d: _latest(c, d), candidates))
    except Exception:
        return deps
    for d, lv in zip(candidates, latest):
        if not lv:
            continue
        d["latest"] = lv
        cur, new = _ver(d["spec"]), _ver(lv)
        if cur is None or new is None or d["spec"] in ("*", "latest"):
            d["status"] = "unpinned"
        elif new[0] > cur[0]:
            d["status"] = "major"
        elif new[:2] > cur[:2]:
            d["status"] = "minor"
        elif new > cur:
            d["status"] = "patch"
        else:
            d["status"] = "current"
    return deps
