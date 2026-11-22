"""Walks the repository and builds the file inventory + basic metrics."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .languages import (BINARY_EXT, CODE_LANGS, DOC_LANGS, GENERATED_HINTS, IGNORE_DIRS, LANG_COLOR,
                        detect_language)

BRANCH_RE = re.compile(
    r"\b(if|elif|else if|for|foreach|while|case|catch|except|when|guard|unless|until)\b|&&|\|\||\?\s*[^:\s]"
)
FUNC_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def |function\s|func |fn |pub fn |public |private |protected |static |"
    r"const \w+\s*=\s*(?:async\s*)?\(|(?:\w+\s*)?\([^)]*\)\s*=>)"
)
TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX|BUG)\b[:\s]?(.{0,120})")


@dataclass
class FileInfo:
    path: str            # posix relative path
    size: int
    language: str | None
    lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    functions: int = 0
    complexity: int = 0  # approximate cyclomatic complexity (sum of branch points + functions)
    is_binary: bool = False
    is_generated: bool = False
    is_test: bool = False
    read: bool = False   # whether content was read (size/limit)
    todos: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def is_code(self) -> bool:
        return self.language in CODE_LANGS and not self.is_generated


@dataclass
class ScanResult:
    root: Path
    files: list[FileInfo]
    truncated: bool
    total_files: int
    skipped_dirs: list[str]
    contents: dict[str, str]  # path -> text for readable code/config/docs files

    def by_path(self) -> dict[str, FileInfo]:
        return {f.path: f for f in self.files}


TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec|specs|testing)(/|$)|(_test|\.test|\.spec|_spec|Test|Tests)\.\w+$|(^|/)test_[^/]+$")
COMMENT_PREFIX = {
    "Python": ("#",), "Ruby": ("#",), "Shell": ("#",), "R": ("#",), "Perl": ("#",), "Elixir": ("#",),
    "YAML": ("#",), "TOML": ("#",), "Dockerfile": ("#",), "Makefile": ("#",), "PowerShell": ("#",),
    "SQL": ("--",), "Lua": ("--",), "Haskell": ("--",),
}


def scan(root: Path, max_files: int, max_file_bytes: int) -> ScanResult:
    files: list[FileInfo] = []
    contents: dict[str, str] = {}
    skipped: set[str] = set()
    total = 0
    truncated = False
    root = root.resolve()

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        keep = []
        for d in sorted(dirnames):
            if d in IGNORE_DIRS or (d.startswith(".") and d not in (".github", ".gitlab", ".circleci", ".devcontainer", ".husky")):
                skipped.add(os.path.normpath(os.path.join(rel_dir, d)).replace(os.sep, "/"))
            else:
                keep.append(d)
        dirnames[:] = keep
        for name in sorted(filenames):
            total += 1
            if len(files) >= max_files:
                truncated = True
                continue
            full = Path(dirpath) / name
            try:
                if full.is_symlink() or not full.is_file():
                    continue
                size = full.stat().st_size
            except OSError:
                continue
            rel = full.relative_to(root).as_posix()
            ext = os.path.splitext(name)[1].lower()
            lang = detect_language(name)
            fi = FileInfo(path=rel, size=size, language=lang)
            fi.is_binary = ext in BINARY_EXT or name == ".DS_Store"
            fi.is_generated = any(h in name for h in GENERATED_HINTS) or name in (
                "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "composer.lock",
                "Gemfile.lock", "go.sum", "uv.lock", "bun.lockb")
            fi.is_test = bool(TEST_RE.search(rel))
            if not fi.is_binary and size <= max_file_bytes and (lang or _is_textish(name)):
                text = _read_text(full)
                if text is not None:
                    fi.read = True
                    _measure(fi, text)
                    if not fi.is_generated:
                        contents[rel] = text
                else:
                    fi.is_binary = True
            files.append(fi)

    return ScanResult(root=root, files=files, truncated=truncated, total_files=total,
                      skipped_dirs=sorted(skipped)[:200], contents=contents)


TEXTISH_NAMES = {"LICENSE", "LICENCE", "COPYING", "README", "CHANGELOG", "AUTHORS", "CONTRIBUTING", "NOTICE",
                 ".gitignore", ".dockerignore", ".env.example", ".env.sample", ".editorconfig", ".nvmrc",
                 ".python-version", "requirements.txt", "Pipfile", "go.mod", "CODEOWNERS", ".env"}


def _is_textish(name: str) -> bool:
    base = name.split(".")[0].upper()
    return (name in TEXTISH_NAMES or base in {"LICENSE", "README", "CHANGELOG", "CONTRIBUTING"}
            or name.endswith((".txt", ".cfg", ".ini", ".conf", ".env", ".lock", ".properties", ".example")))


def _read_text(p: Path) -> str | None:
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8000]:
        return None
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _measure(fi: FileInfo, text: str) -> None:
    lines = text.splitlines()
    fi.lines = len(lines)
    if fi.language == "Jupyter Notebook":
        fi.code_lines = text.count('"cell_type": "code"') * 10
        return
    prefixes = COMMENT_PREFIX.get(fi.language or "", ("//",))
    in_block = False
    branches = 0
    funcs = 0
    is_code = fi.language in CODE_LANGS
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s:
            fi.blank_lines += 1
            continue
        if in_block:
            fi.comment_lines += 1
            if "*/" in s or '"""' in s or "'''" in s:
                in_block = False
            continue
        if s.startswith(("/*", "<!--")):
            fi.comment_lines += 1
            in_block = "*/" not in s and "-->" not in s
            continue
        if s.startswith(prefixes) or (fi.language in DOC_LANGS):
            fi.comment_lines += 1 if fi.language not in DOC_LANGS else 0
        else:
            fi.code_lines += 1
        if is_code:
            if len(fi.todos) < 30:
                m = TODO_RE.search(s)
                if m and (s.startswith(prefixes) or "//" in s or "#" in s or "/*" in s):
                    fi.todos.append((i, m.group(1), m.group(2).strip(" :-*/")))
            if len(s) < 400:
                branches += len(BRANCH_RE.findall(s))
                if FUNC_RE.match(line):
                    funcs += 1
    if fi.language in DOC_LANGS:
        fi.code_lines = 0
    fi.functions = funcs
    fi.complexity = branches + funcs


def language_breakdown(files: list[FileInfo]) -> list[dict]:
    agg: dict[str, dict] = {}
    for f in files:
        if f.is_binary or f.is_generated:
            continue
        lang = f.language or "Other"
        a = agg.setdefault(lang, {"name": lang, "files": 0, "lines": 0, "bytes": 0, "color": LANG_COLOR.get(lang, "#6b7280")})
        a["files"] += 1
        a["lines"] += f.code_lines or f.lines
        a["bytes"] += f.size
    code_total = sum(a["bytes"] for a in agg.values() if a["name"] in CODE_LANGS) or 1
    all_total = sum(a["bytes"] for a in agg.values()) or 1
    out = sorted(agg.values(), key=lambda a: (a["name"] in CODE_LANGS, a["bytes"]), reverse=True)
    for a in out:
        a["is_code"] = a["name"] in CODE_LANGS
        # code languages: share of code; others: share of all text files
        a["percent"] = round(100 * a["bytes"] / (code_total if a["is_code"] else all_total), 2)
    return out


def build_tree(files: list[FileInfo], max_nodes: int = 4000) -> dict:
    """Nested tree with aggregated size/lines for treemap + explorer."""
    root: dict = {"name": "/", "path": "", "type": "dir", "children": {}, "size": 0, "lines": 0, "files": 0}
    count = 0
    for f in files:
        if count >= max_nodes:
            break
        count += 1
        parts = f.path.split("/")
        node = root
        node["size"] += f.size
        loc = 0 if f.is_generated else f.code_lines
        node["lines"] += loc
        node["files"] += 1
        for i, part in enumerate(parts[:-1]):
            child = node["children"].get(part)
            if child is None:
                child = {"name": part, "path": "/".join(parts[: i + 1]), "type": "dir", "children": {},
                         "size": 0, "lines": 0, "files": 0}
                node["children"][part] = child
            node = child
            node["size"] += f.size
            node["lines"] += loc
            node["files"] += 1
        node["children"][parts[-1]] = {
            "name": parts[-1], "path": f.path, "type": "file", "size": f.size, "lines": loc,
            "language": f.language, "complexity": f.complexity, "test": f.is_test,
        }

    def finalize(n: dict) -> dict:
        if n["type"] == "dir":
            kids = [finalize(c) for c in n["children"].values()]
            kids.sort(key=lambda c: (c["type"] != "dir", c["name"].lower()))
            n["children"] = kids
        return n

    return finalize(root)
