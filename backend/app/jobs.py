"""Background job execution for analyses."""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

from . import db
from .analyzer import pipeline
from .config import get_settings
from .github import RepoRef

_pool: ThreadPoolExecutor | None = None


def pool() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=get_settings().workers, thread_name_prefix="analysis")
    return _pool


def submit(ref: RepoRef, url: str, use_llm: bool = True) -> str:
    aid = uuid.uuid4().hex[:12]
    db.create_analysis(aid, url, ref.owner, ref.repo, ref.ref)
    pool().submit(pipeline.run, aid, ref, use_llm)
    return aid
