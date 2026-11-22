"""GitHub URL parsing, metadata fetching and cloning (with zipball fallback)."""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import get_settings


class RepoError(Exception):
    """User-facing error about the repository (bad URL, not found, too big...)."""


@dataclass
class RepoRef:
    owner: str
    repo: str
    ref: str | None = None      # branch / tag / sha from URL (optional)
    subpath: str | None = None  # /tree/<ref>/<path> -> focus folder

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


_NAME = r"[A-Za-z0-9_.-]+"


def parse_github_url(url: str) -> RepoRef:
    """Accepts: https://github.com/o/r, github.com/o/r.git, git@github.com:o/r.git,
    o/r, https://github.com/o/r/tree/branch/sub/dir, .../blob/..., trailing slashes, query strings."""
    u = (url or "").strip()
    if not u:
        raise RepoError("Please paste a GitHub repository URL.")
    u = u.split("#")[0].split("?")[0].rstrip("/")
    m = re.match(rf"^git@github\.com:({_NAME})/({_NAME})$", u)
    if m:
        return RepoRef(m.group(1), _strip_git(m.group(2)))
    u = re.sub(r"^(https?://)?(www\.)?", "", u)
    if u.startswith("github.com/"):
        u = u[len("github.com/"):]
    elif "/" in u and "." in u.split("/")[0]:
        raise RepoError("Only github.com repositories are supported.")
    parts = [p for p in u.split("/") if p]
    if len(parts) < 2 or not re.fullmatch(_NAME, parts[0]) or not re.fullmatch(_NAME, parts[1]):
        raise RepoError("That doesn't look like a GitHub repository URL (expected github.com/owner/repo).")
    ref = RepoRef(parts[0], _strip_git(parts[1]))
    if len(parts) >= 4 and parts[2] in ("tree", "blob", "commit"):
        ref.ref = parts[3]
        if len(parts) > 4 and parts[2] == "tree":
            ref.subpath = "/".join(parts[4:])
    return ref


def _strip_git(name: str) -> str:
    return name[:-4] if name.endswith(".git") else name


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "RepoXray"}
    tok = get_settings().github_token or os.environ.get("GITHUB_TOKEN", "")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def fetch_metadata(ref: RepoRef) -> dict:
    """Repo metadata from the GitHub API. Never fatal: returns {} on rate limits / network errors,
    but raises RepoError on a definite 404 so the user gets a clear message."""
    meta: dict = {}
    try:
        with httpx.Client(timeout=15, headers=_headers(), follow_redirects=True) as c:
            r = c.get(f"https://api.github.com/repos/{ref.full_name}")
            if r.status_code == 404:
                raise RepoError(
                    f"Repository '{ref.full_name}' was not found. If it is private, set REPOXRAY_GITHUB_TOKEN."
                )
            if r.status_code != 200:
                return {}
            j = r.json()
            meta = {
                "full_name": j.get("full_name"),
                "description": j.get("description"),
                "homepage": j.get("homepage"),
                "stars": j.get("stargazers_count"),
                "forks": j.get("forks_count"),
                "watchers": j.get("subscribers_count"),
                "open_issues": j.get("open_issues_count"),
                "default_branch": j.get("default_branch"),
                "license": (j.get("license") or {}).get("spdx_id"),
                "topics": j.get("topics") or [],
                "created_at": j.get("created_at"),
                "pushed_at": j.get("pushed_at"),
                "archived": j.get("archived"),
                "fork": j.get("fork"),
                "size_kb": j.get("size"),
                "avatar": (j.get("owner") or {}).get("avatar_url"),
                "private": j.get("private"),
            }
            r2 = c.get(f"https://api.github.com/repos/{ref.full_name}/languages")
            if r2.status_code == 200:
                meta["github_languages"] = r2.json()
    except RepoError:
        raise
    except Exception:
        return meta
    return meta


def fetch_repo(ref: RepoRef, dest: Path, meta: dict) -> dict:
    """Clone into dest. Falls back to downloading a zipball when git is unavailable or fails.
    Returns info about how it was fetched."""
    s = get_settings()
    size_kb = meta.get("size_kb") or 0
    if size_kb and size_kb / 1024 > s.max_repo_mb:
        raise RepoError(
            f"Repository is {size_kb/1024:.0f} MB, above the {s.max_repo_mb} MB limit (REPOXRAY_MAX_REPO_MB)."
        )
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)

    branch = ref.ref or meta.get("default_branch")
    err = ""
    if shutil.which("git"):
        url = ref.clone_url
        tok = s.github_token or os.environ.get("GITHUB_TOKEN", "")
        if tok:
            url = f"https://x-access-token:{tok}@github.com/{ref.full_name}.git"
        cmd = ["git", "clone", "--depth", str(s.clone_depth), "--single-branch", "--no-tags", "--quiet"]
        if branch and not re.fullmatch(r"[0-9a-f]{7,40}", branch):
            cmd += ["--branch", branch]
        cmd += [url, str(dest)]
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
        try:
            p = _run_with_size_guard(cmd, env, dest, s.max_repo_mb, s.clone_timeout)
            if p.returncode == 0:
                if branch and re.fullmatch(r"[0-9a-f]{7,40}", branch):
                    subprocess.run(["git", "-C", str(dest), "fetch", "--depth", "50", "origin", branch],
                                   capture_output=True, timeout=s.clone_timeout, env=env)
                    subprocess.run(["git", "-C", str(dest), "checkout", "-q", branch], capture_output=True, env=env)
                return {"method": "git", "branch": branch or _current_branch(dest)}
            err = (p.stderr or "").replace(tok, "***") if tok else (p.stderr or "")
            if "not found" in err.lower() and "branch" in err.lower():
                raise RepoError(f"Branch or tag '{branch}' does not exist in {ref.full_name}.")
        except subprocess.TimeoutExpired:
            err = "git clone timed out"
        shutil.rmtree(dest, ignore_errors=True)

    # Fallback: zipball through codeload (no history => no activity stats)
    zref = branch or "HEAD"
    try:
        with httpx.Client(timeout=s.clone_timeout, headers=_headers(), follow_redirects=True) as c:
            r = c.get(f"https://api.github.com/repos/{ref.full_name}/zipball/{zref}")
            if r.status_code == 404:
                raise RepoError(f"Could not download {ref.full_name} ({zref}). Does the repo/branch exist?")
            r.raise_for_status()
            if len(r.content) > s.max_repo_mb * 1024 * 1024:
                raise RepoError("Repository archive exceeds the size limit.")
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                _safe_extract(z, dest)
        # zipball wraps everything into one top-level folder
        children = list(dest.iterdir())
        if len(children) == 1 and children[0].is_dir():
            inner = children[0]
            for item in inner.iterdir():
                shutil.move(str(item), dest / item.name)
            inner.rmdir()
        return {"method": "zip", "branch": branch, "note": "History unavailable (downloaded archive)."}
    except RepoError:
        raise
    except Exception as e:  # noqa: BLE001
        low = err.lower()
        if any(k in low for k in ("authentication failed", "could not read username", "repository not found", "not found")):
            raise RepoError(
                f"Repository '{ref.full_name}' was not found or is private. Check the URL, or set "
                "REPOXRAY_GITHUB_TOKEN to analyse private repositories.") from e
        if any(k in low for k in ("could not resolve host", "timed out", "unable to access")):
            raise RepoError("Could not reach GitHub. Check your internet connection / proxy and try again.") from e
        msg = err.strip().splitlines()[-1] if err.strip() else str(e)
        raise RepoError(f"Could not fetch repository: {msg}") from e


class _Result:
    def __init__(self, returncode: int, stderr: str):
        self.returncode, self.stderr = returncode, stderr


def _dir_mb(path: Path) -> float:
    total = 0
    for dp, _, fns in os.walk(path):
        for f in fns:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total / 1024 / 1024


def _run_with_size_guard(cmd: list[str], env: dict, dest: Path, max_mb: int, timeout: int) -> _Result:
    """Runs git clone, killing it if the download grows beyond max_mb or exceeds the timeout."""
    import time
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env)
    start = time.time()
    while proc.poll() is None:
        time.sleep(1.5)
        if dest.exists() and _dir_mb(dest) > max_mb:
            proc.kill(); proc.wait()
            shutil.rmtree(dest, ignore_errors=True)
            raise RepoError(f"Repository is larger than the {max_mb} MB limit (set REPOXRAY_MAX_REPO_MB to raise it).")
        if time.time() - start > timeout:
            proc.kill(); proc.wait()
            raise subprocess.TimeoutExpired(cmd, timeout)
    return _Result(proc.returncode, proc.stderr.read() if proc.stderr else "")


def _safe_extract(z: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for m in z.infolist():
        target = (dest / m.filename).resolve()
        if not str(target).startswith(str(root)):
            continue  # zip-slip protection
        if m.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _current_branch(path: Path) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return p.stdout.strip() or None
    except Exception:
        return None
