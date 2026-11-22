"""Health scoring, security checks and rule-based improvement suggestions."""
from __future__ import annotations

import posixpath
import re
import time
from datetime import datetime, timezone

SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("OpenAI key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{32,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("Stripe secret key", re.compile(r"\bsk_live_[0-9a-zA-Z]{24,}\b")),
    ("Private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("Hard-coded password", re.compile(r"""(?i)\b(password|passwd|pwd|secret|api_key|apikey|token)\s*[:=]\s*['"][^'"\s${}]{8,}['"]""")),
]
RISKY_CODE = [
    ("Use of eval()", re.compile(r"(?<![\w.])eval\s*\("), (".py", ".js", ".ts", ".php")),
    ("Shell command with shell=True", re.compile(r"shell\s*=\s*True"), (".py",)),
    ("Unsafe pickle load", re.compile(r"pickle\.loads?\("), (".py",)),
    ("yaml.load without SafeLoader", re.compile(r"yaml\.load\((?![^)]*Loader)"), (".py",)),
    ("innerHTML assignment (XSS risk)", re.compile(r"\.innerHTML\s*="), (".js", ".ts", ".jsx", ".tsx")),
    ("dangerouslySetInnerHTML", re.compile(r"dangerouslySetInnerHTML"), (".jsx", ".tsx", ".js")),
    ("Debug mode enabled", re.compile(r"(?:DEBUG\s*=\s*True|debug\s*=\s*True)"), (".py",)),
    ("SQL built with string formatting", re.compile(r"""(?i)execute\(\s*f?["'](?:SELECT|INSERT|UPDATE|DELETE)[^"']*["']\s*(?:%|\+|\.format)|execute\(\s*f["'](?:SELECT|INSERT|UPDATE|DELETE)[^"']*\{"""), (".py",)),
    ("Disabled TLS verification", re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify:\s*true"), (".py", ".js", ".ts", ".go")),
]


ACTION_TITLES = {
    "README present": "Add a README", "README is detailed": "Expand the README", "License": "Add a license",
    "Contributing guide": "Add a contributing guide", "Changelog": "Keep a changelog", "Inline comments": "Document the code",
    "Has automated tests": "Add automated tests", "Test-to-code ratio": "Increase test coverage",
    "Continuous integration": "Set up continuous integration", "Containerised": "Add a Dockerfile",
    "Dependency updates automated": "Automate dependency updates", ".gitignore": "Add a .gitignore",
    "Linter / formatter configured": "Configure a linter and formatter", "No oversized files": "Split oversized files",
    "Manageable complexity": "Reduce complexity in hotspots", "Static typing": "Adopt static typing",
    "Few open TODO/FIXME": "Triage TODO and FIXME notes", "No leaked secrets": "Remove committed secrets",
    "No risky code patterns": "Fix risky code patterns", "Env template provided": "Add a .env.example",
    "Dependencies up to date": "Upgrade outdated dependencies", "Versions pinned": "Pin dependency versions",
    "Lockfile committed": "Commit a lockfile", "Recently active": "Revive maintenance", "Not archived": "Move to a maintained fork",
    "Bus factor > 1": "Share ownership with more contributors",
}


def _find(files: list, rx: str) -> list[str]:
    r = re.compile(rx, re.I)
    return [f.path for f in files if r.search(f.path)]


def security_scan(files: list, contents: dict[str, str]) -> list[dict]:
    findings: list[dict] = []
    for f in files:
        name = posixpath.basename(f.path)
        if name in (".env", ".env.local", ".env.production") or name.endswith((".pem", ".key", ".p12", ".pfx", "id_rsa")):
            fixture = bool(re.search(r"(?i)(^|/)(tests?|testdata|fixtures?|examples?|samples?|certs?/dev)/", f.path))
            findings.append({"severity": "low" if fixture else "high", "type": "Sensitive file committed", "file": f.path, "line": 0,
                             "detail": f"`{name}` may contain secrets and should not be in version control."})
    for path, text in contents.items():
        if f"/{path}".count("/test") or path.endswith((".md", ".lock", ".example", ".sample")) or "example" in path.lower():
            continue
        ext = posixpath.splitext(path)[1]
        for label, rx in SECRET_PATTERNS:
            for m in rx.finditer(text):
                val = m.group(0)
                if label == "Hard-coded password" and re.search(r"(?i)example|changeme|your|xxx|placeholder|dummy|test|<|\*\*\*", val):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                findings.append({"severity": "high" if label != "Hard-coded password" else "medium", "type": label,
                                 "file": path, "line": line, "detail": _mask(val)})
                break
        for label, rx, exts in RISKY_CODE:
            if ext in exts:
                m = rx.search(text)
                if m:
                    findings.append({"severity": "low" if "Debug" in label else "medium", "type": label, "file": path,
                                     "line": text.count("\n", 0, m.start()) + 1, "detail": text.splitlines()[text.count("\n", 0, m.start())].strip()[:140]})
        if len(findings) > 80:
            break
    return findings


def _mask(v: str) -> str:
    return v[:6] + "…" + "*" * 6 if len(v) > 10 else "******"


def evaluate(files: list, contents: dict[str, str], deps: list[dict], stack: list[dict], meta: dict,
             git: dict, security: list[dict], languages: list[dict], todos: list[dict]) -> dict:
    names = {t["name"] for t in stack}
    paths = [f.path for f in files]
    code = [f for f in files if f.is_code]
    tests = [f for f in code if f.is_test]
    src = [f for f in code if not f.is_test]
    loc = sum(f.code_lines for f in src) or 1
    test_loc = sum(f.code_lines for f in tests)
    readme = next((p for p in paths if re.match(r"(?i)^readme(\.\w+)?$", p)), None)
    readme_len = len(contents.get(readme, "")) if readme else 0
    has = lambda rx: bool(_find(files, rx))  # noqa: E731

    checks: list[dict] = []

    def check(cat: str, name: str, ok: bool, weight: int, fix: str, partial: float | None = None):
        score = (1.0 if ok else 0.0) if partial is None else max(0.0, min(1.0, partial))
        checks.append({"category": cat, "name": name, "passed": score >= 0.99, "score": score, "weight": weight, "fix": fix})

    # Documentation
    check("Documentation", "README present", bool(readme), 8, "Add a README.md explaining purpose, setup and usage.")
    check("Documentation", "README is detailed", readme_len > 1500, 5, "Expand the README with installation, usage examples, architecture and screenshots.",
          readme_len / 1500 if readme else 0)
    check("Documentation", "License", has(r"(?i)^(license|licence|copying)(\.\w+)?$") or bool(meta.get("license")), 4,
          "Add a LICENSE file so others know how they may use the code.")
    check("Documentation", "Contributing guide", has(r"(?i)(^|/)contributing(\.\w+)?$"), 2, "Add CONTRIBUTING.md describing how to set up, test and submit changes.")
    check("Documentation", "Changelog", has(r"(?i)(^|/)(changelog|history|releases)(\.\w+)?$"), 1, "Keep a CHANGELOG.md to track releases.")
    doc_ratio = sum(f.comment_lines for f in src) / loc
    check("Documentation", "Inline comments", doc_ratio > 0.08, 3, "Add docstrings/comments to public functions and complex logic.", doc_ratio / 0.08)

    # Testing
    ratio = test_loc / loc
    check("Testing", "Has automated tests", bool(tests), 10, "Add unit tests (e.g. pytest / Jest / Vitest / go test).")
    check("Testing", "Test-to-code ratio", ratio >= 0.25, 6, f"Test code is {ratio:.0%} of source; aim for 25%+ around critical logic.", ratio / 0.25)

    # CI/CD & DevOps
    ci = bool(names & {"GitHub Actions", "GitLab CI", "CircleCI", "Jenkins", "Travis CI"})
    check("CI/CD & DevOps", "Continuous integration", ci, 7, "Add a CI workflow (e.g. .github/workflows/ci.yml) that runs lint + tests on every PR.")
    check("CI/CD & DevOps", "Containerised", "Docker" in names, 4, "Add a Dockerfile (and docker-compose.yml) for reproducible runs.")
    check("CI/CD & DevOps", "Dependency updates automated", "Dependabot" in names or has(r"renovate\.json"), 2, "Enable Dependabot or Renovate for automatic dependency PRs.")
    check("CI/CD & DevOps", ".gitignore", has(r"(^|/)\.gitignore$"), 3, "Add a .gitignore to keep build artefacts and secrets out of git.")

    # Code quality
    lint = bool(names & {"ESLint", "Prettier", "Ruff", "Black", "Biome", "mypy", "pre-commit", "EditorConfig"}) or has(
        r"(^|/)(\.eslintrc[^/]*|eslint\.config\.\w+|\.flake8|setup\.cfg|\.pylintrc|\.golangci\.ya?ml|rustfmt\.toml|\.rubocop\.yml|\.prettierrc[^/]*)$")
    check("Code Quality", "Linter / formatter configured", lint, 5, "Configure a linter and formatter (ESLint+Prettier, Ruff, golangci-lint…).")
    big = [f for f in src if f.code_lines > 600]
    check("Code Quality", "No oversized files", not big, 4, f"{len(big)} file(s) exceed 600 lines — split them into smaller modules.",
          1 - len(big) / max(1, len(src)) * 5)
    complex_files = [f for f in src if f.complexity > 60]
    check("Code Quality", "Manageable complexity", not complex_files, 4,
          f"{len(complex_files)} file(s) have high branching complexity; refactor into smaller functions.",
          1 - len(complex_files) / max(1, len(src)) * 5)
    ts = any(l["name"] == "TypeScript" for l in languages) or "mypy" in names or any(p.endswith("py.typed") for p in paths)
    js_heavy = any(l["name"] == "JavaScript" and l["percent"] > 30 for l in languages)
    py_heavy = any(l["name"] == "Python" and l["percent"] > 30 for l in languages)
    if js_heavy or py_heavy:
        check("Code Quality", "Static typing", ts, 3, "Adopt TypeScript or Python type hints + mypy for safer refactoring.")
    check("Code Quality", "Few open TODO/FIXME", len(todos) < 15, 2, f"{len(todos)} TODO/FIXME markers found — triage them into issues.", 1 - len(todos) / 60)

    # Security
    high = [s for s in security if s["severity"] == "high"]
    med = [s for s in security if s["severity"] == "medium"]
    check("Security", "No leaked secrets", not high, 10, "Remove committed secrets, rotate them, and load config from environment variables.")
    check("Security", "No risky code patterns", len(med) == 0, 4, "Review flagged risky patterns (eval, shell=True, SQL formatting…).", 1 - len(med) / 8)
    check("Security", "Env template provided", has(r"\.env\.(example|sample|template)$") or not has(r"(?i)dotenv|os\.environ|process\.env"), 2,
          "Provide a .env.example documenting required environment variables.")

    # Dependencies
    known = [d for d in deps if d.get("status")]
    major = [d for d in known if d["status"] == "major"]
    unpinned = [d for d in deps if d["spec"] in ("*", "", "latest")]
    if deps:
        check("Dependencies", "Dependencies up to date", not major, 6,
              f"{len(major)} dependencies are a major version behind — plan upgrades.", 1 - (len(major) / max(1, len(known))) * 2)
        check("Dependencies", "Versions pinned", len(unpinned) <= len(deps) * 0.2, 3, "Pin dependency versions (or commit a lockfile) for reproducible builds.",
              1 - len(unpinned) / max(1, len(deps)))
        lock = has(r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|uv\.lock|Pipfile\.lock|Cargo\.lock|go\.sum|composer\.lock|Gemfile\.lock|bun\.lockb?)$")
        check("Dependencies", "Lockfile committed", lock, 2, "Commit a lockfile so every install resolves the same versions.")

    # Maintenance
    last = git.get("last_commit") or meta.get("pushed_at")
    days = None
    if last:
        try:
            dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - dt).days
        except Exception:
            days = None
    if days is not None:
        check("Maintenance", "Recently active", days < 180, 5, f"Last commit was {days} days ago — the project may be stale or unmaintained.",
              1 - (days - 180) / 540 if days >= 180 else 1)
    if meta.get("archived"):
        check("Maintenance", "Not archived", False, 4, "Repository is archived (read-only); consider an actively maintained fork.")
    contributors = len(git.get("contributors") or [])
    if git.get("contributors") is not None and git.get("available"):
        check("Maintenance", "Bus factor > 1", contributors > 1, 2, "Only one contributor — document knowledge and invite collaborators.")

    total_w = sum(c["weight"] for c in checks) or 1
    score = round(100 * sum(c["weight"] * c["score"] for c in checks) / total_w)
    cats: dict[str, dict] = {}
    for c in checks:
        a = cats.setdefault(c["category"], {"name": c["category"], "w": 0, "s": 0.0, "passed": 0, "total": 0})
        a["w"] += c["weight"]; a["s"] += c["weight"] * c["score"]; a["total"] += 1; a["passed"] += int(c["passed"])
    categories = [{"name": a["name"], "score": round(100 * a["s"] / a["w"]), "passed": a["passed"], "total": a["total"]} for a in cats.values()]

    improvements = []
    for c in sorted(checks, key=lambda c: -(c["weight"] * (1 - c["score"]))):
        if c["passed"]:
            continue
        impact = c["weight"] * (1 - c["score"])
        improvements.append({
            "title": ACTION_TITLES.get(c["name"], c["name"]),
            "category": c["category"], "detail": c["fix"],
            "priority": "high" if impact >= 5 else "medium" if impact >= 2.5 else "low",
            "effort": "low" if c["category"] in ("Documentation", "CI/CD & DevOps") else "medium",
        })

    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "E"
    return {
        "score": score, "grade": grade, "categories": categories, "checks": checks, "improvements": improvements,
        "hotspots": sorted(
            [{"path": f.path, "lines": f.code_lines, "complexity": f.complexity, "functions": f.functions,
              "churn": git.get("churn", {}).get(f.path, 0)} for f in src],
            key=lambda h: -(h["complexity"] * (1 + h["churn"] / 5)),
        )[:15],
        "stats": {"source_files": len(src), "test_files": len(tests), "source_loc": loc if src else 0, "test_loc": test_loc,
                  "comment_ratio": round(doc_ratio, 3), "test_ratio": round(ratio, 3), "days_since_commit": days},
    }
