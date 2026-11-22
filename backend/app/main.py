"""RepoXray API."""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, jobs
from .analyzer import scanner
from .config import get_settings
from .github import RepoError, parse_github_url
from .llm import insights as ins
from .llm import providers
from .rag import index as rag
from .report import to_markdown

app = FastAPI(title="RepoXray API", version="1.0.0", description="Deep, visual analysis of any GitHub repository.")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"], allow_headers=["*"],
)


class AnalyzeIn(BaseModel):
    url: str = Field(..., examples=["https://github.com/pallets/flask"])
    force: bool = False
    use_llm: bool = True


class ChatIn(BaseModel):
    question: str
    history: list[dict] = []


class ExplainIn(BaseModel):
    path: str


class LLMSettingsIn(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    embed_model: str | None = None
    temperature: float | None = None
    clear_api_key: bool = False


def _require(aid: str, done: bool = True) -> dict:
    a = db.get_analysis(aid)
    if not a:
        raise HTTPException(404, "Analysis not found")
    if done and not a.get("result"):
        raise HTTPException(409, "Analysis has no results yet")
    return a


def _repo_root(a: dict) -> Path:
    root = settings.repos_dir / a["id"]
    sub = (a.get("result") or {}).get("subpath")
    if sub and (root / sub).is_dir():
        root = root / sub
    return root


# ------------------------------------------------------------------ core endpoints

@app.get("/api/health")
def health():
    cfg = providers.get_config()
    return {"ok": True, "version": app.version, "llm": cfg.public()}


@app.post("/api/analyze")
def analyze(body: AnalyzeIn):
    try:
        ref = parse_github_url(body.url)
    except RepoError as e:
        raise HTTPException(400, str(e))
    canonical = ref.canonical_url + (f"/tree/{ref.ref}" if ref.ref else "") + (f"/{ref.subpath}" if ref.subpath else "")
    if not body.force:
        hit = db.find_recent_done(canonical, max_age_s=6 * 3600)
        if hit:
            return {"id": hit["id"], "cached": True}
    aid = jobs.submit(ref, canonical, body.use_llm)
    return {"id": aid, "cached": False}


@app.get("/api/analyses")
def list_analyses(limit: int = 50):
    return db.list_analyses(limit)


@app.get("/api/analyses/{aid}")
def get_analysis(aid: str):
    return _require(aid, done=False)


@app.get("/api/analyses/{aid}/status")
def get_status(aid: str):
    a = db.get_analysis(aid, with_result=False)
    if not a:
        raise HTTPException(404, "Analysis not found")
    return a


@app.delete("/api/analyses/{aid}")
def delete_analysis(aid: str):
    _require(aid, done=False)
    db.delete_analysis(aid)
    rag.drop_index(aid)
    shutil.rmtree(settings.repos_dir / aid, ignore_errors=True)
    shutil.rmtree(settings.index_dir / aid, ignore_errors=True)
    return {"ok": True}


@app.get("/api/analyses/{aid}/file")
def get_file(aid: str, path: str = Query(...)):
    a = _require(aid)
    root = _repo_root(a).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(404, "File not found")
    if target.stat().st_size > 2_000_000:
        raise HTTPException(413, "File too large to preview")
    text = scanner._read_text(target)
    if text is None:
        raise HTTPException(415, "Binary file")
    symbols = a["result"]["symbols"].get(path, [])
    return {"path": path, "content": text, "symbols": symbols,
            "language": next((f["language"] for f in a["result"]["files"] if f["path"] == path), None)}


@app.post("/api/analyses/{aid}/explain")
def explain(aid: str, body: ExplainIn):
    a = _require(aid)
    f = get_file(aid, body.path)
    md, src = ins.explain_file(body.path, f["content"], f["symbols"], providers.get_config())
    return {"markdown": md, "source": src}


@app.get("/api/analyses/{aid}/search")
def search(aid: str, q: str, k: int = 10):
    _require(aid)
    idx = rag.get_index(aid)
    if not idx:
        raise HTTPException(409, "Index not built yet")
    cfg = providers.get_config()
    hits = idx.search(q, k, cfg if idx.vectors is not None else None)
    return [{k_: h[k_] for k_ in ("path", "start", "end", "score", "text")} for h in hits]


@app.post("/api/analyses/{aid}/chat")
def chat(aid: str, body: ChatIn):
    a = _require(aid)
    idx = rag.get_index(aid)
    if not idx:
        raise HTTPException(409, "Knowledge index not ready yet — wait for the analysis to finish.")
    cfg = providers.get_config()
    hits = idx.search(body.question, 8, cfg if (cfg.enabled and idx.vectors is not None) else None)
    r = a["result"]
    overview = f"{r['insights'].get('summary', '')}\nStack: {', '.join(t['name'] for t in r['stack'][:25])}\n" \
               f"Entry points: {', '.join(e['path'] for e in r['entry_points'][:3])}\n" \
               f"Top-level dirs: {', '.join(c['name'] for c in r['tree']['children'][:30])}"

    def gen():
        yield json.dumps({"type": "sources", "data": [{"path": h["path"], "start": h["start"], "end": h["end"]} for h in hits]}) + "\n"
        if not cfg.enabled:
            yield json.dumps({"type": "token", "data": rag.fallback_answer(body.question, hits)}) + "\n"
        else:
            try:
                for tok in rag.answer_stream(body.question, body.history, r["repo"], overview, hits, cfg):
                    yield json.dumps({"type": "token", "data": tok}) + "\n"
            except providers.LLMError as e:
                yield json.dumps({"type": "token", "data": rag.fallback_answer(body.question, hits, str(e))}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/analyses/{aid}/insights/regenerate")
def regenerate(aid: str):
    a = _require(aid)
    cfg = providers.get_config()
    if not cfg.enabled:
        raise HTTPException(400, "Configure an LLM in Settings first.")

    def work():
        r = a["result"]
        sc = scanner.scan(_repo_root(a), settings.max_files, settings.max_file_bytes)
        try:
            base = ins.heuristic(r)
            extra = ins.llm_insights(r, sc.contents, cfg, cfg.context_budget(settings.llm_context_chars))
            r["insights"] = ins.merge(base, extra)
            r["insights"]["model"] = f"{cfg.provider}/{cfg.model}"
            if extra.get("mermaid"):
                r["diagrams"]["ai_flow"] = extra["mermaid"]
            if not (r.get("rag") or {}).get("dense"):
                r["rag"] = rag.build_index(aid, sc.contents, {}, cfg)
        except providers.LLMError as e:
            r["insights"]["llm_error"] = str(e)
        r.pop("regenerating", None)
        db.update_analysis(aid, result=r)

    r = a["result"]
    r["regenerating"] = True
    db.update_analysis(aid, result=r)
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


@app.get("/api/analyses/{aid}/report.md", response_class=PlainTextResponse)
def report_md(aid: str):
    a = _require(aid)
    return PlainTextResponse(to_markdown(a["result"]), headers={
        "Content-Disposition": f'attachment; filename="{a["repo"]}-repoxray.md"'})


@app.get("/api/analyses/{aid}/report.json")
def report_json(aid: str):
    a = _require(aid)
    return JSONResponse(a["result"], headers={"Content-Disposition": f'attachment; filename="{a["repo"]}-repoxray.json"'})


# ------------------------------------------------------------------ settings

@app.get("/api/settings/llm")
def get_llm():
    return providers.get_config().public()


@app.put("/api/settings/llm")
def put_llm(body: LLMSettingsIn):
    if body.provider and body.provider not in providers.PROVIDERS:
        raise HTTPException(400, f"provider must be one of {', '.join(providers.PROVIDERS)}")
    return providers.save_config(body.model_dump()).public()


@app.post("/api/settings/llm/test")
def test_llm():
    return providers.health()


@app.get("/api/settings/llm/models")
def llm_models():
    try:
        ms = providers.list_models()
        return {"models": [m for m in ms if "embed" not in m.lower()], "embed_models": [m for m in ms if "embed" in m.lower()]}
    except providers.LLMError as e:
        return {"models": [], "error": str(e)}


# ------------------------------------------------------------------ static frontend (single-container mode)

_static = Path(__file__).resolve().parent.parent / "static"
if _static.is_dir() and (_static / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = (_static / full_path).resolve()
        if full_path and str(f).startswith(str(_static.resolve())) and f.is_file():
            return FileResponse(f)
        return FileResponse(_static / "index.html")
