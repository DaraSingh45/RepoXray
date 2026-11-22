"""Git history statistics: activity timeline, contributors, churn."""
from __future__ import annotations

import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _git(root: Path, *args: str, timeout: int = 60) -> str:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout,
                       errors="replace")
    return p.stdout if p.returncode == 0 else ""


def collect(root: Path) -> dict:
    if not (root / ".git").exists():
        return {"available": False, "contributors": None}
    try:
        sha = _git(root, "rev-parse", "HEAD").strip()
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        log = _git(root, "log", "--no-merges", "--date=iso-strict", "--pretty=format:@@%H|%an|%ae|%ad|%s", "--numstat", "-n", "400")
    except Exception:
        return {"available": False, "contributors": None}
    commits = []
    churn: Counter = Counter()
    authors: dict[str, dict] = {}
    cur = None
    cur_author: dict = {}
    for line in log.splitlines():
        if line.startswith("@@"):
            parts = line[2:].split("|", 4)
            if len(parts) < 5:
                continue
            h, an, ae, ad, subj = parts
            cur = {"sha": h[:8], "author": an, "date": ad, "message": subj[:140], "added": 0, "deleted": 0, "files": 0}
            commits.append(cur)
            cur_author = authors.setdefault(ae.lower() or an, {"name": an, "commits": 0, "added": 0, "deleted": 0, "last": ad})
            cur_author["commits"] += 1
        elif line.strip() and cur is not None:
            seg = line.split("\t")
            if len(seg) == 3:
                ad_, de_, path = seg
                ad_i = int(ad_) if ad_.isdigit() else 0
                de_i = int(de_) if de_.isdigit() else 0
                cur["added"] += ad_i; cur["deleted"] += de_i; cur["files"] += 1
                if "=>" not in path:
                    churn[path] += 1
                cur_author["added"] += ad_i; cur_author["deleted"] += de_i
    weekly: dict[str, int] = defaultdict(int)
    hours = Counter()
    for c in commits:
        try:
            dt = datetime.fromisoformat(c["date"])
            iso = dt.isocalendar()
            weekly[f"{iso[0]}-W{iso[1]:02d}"] += 1
            hours[dt.weekday()] += 1
        except Exception:
            pass
    total = _git(root, "rev-list", "--count", "HEAD").strip()
    return {
        "available": True,
        "sha": sha[:12], "branch": branch,
        "commit_count_sampled": len(commits),
        "commit_count": int(total) if total.isdigit() else len(commits),
        "shallow": (root / ".git" / "shallow").exists(),
        "first_commit": commits[-1]["date"] if commits else None,
        "last_commit": commits[0]["date"] if commits else None,
        "recent_commits": commits[:25],
        "contributors": sorted(authors.values(), key=lambda a: -a["commits"])[:20],
        "weekly": [{"week": k, "commits": v} for k, v in sorted(weekly.items())][-52:],
        "weekday": [hours.get(i, 0) for i in range(7)],
        "churn": dict(churn.most_common(200)),
        "now": datetime.now(timezone.utc).isoformat(),
    }
