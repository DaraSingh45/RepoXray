"""A tiny fake LLM server speaking both the Ollama and OpenAI protocols (for tests / offline demos).

Run: uvicorn tests.mock_llm:app --port 11999
"""
import hashlib
import json

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

INSIGHTS = {
    "summary": "Mock summary: this repository implements a web application.",
    "purpose": "Demonstrates the analysed project.",
    "audience": "Developers",
    "use_cases": ["Learning", "Prototyping"],
    "how_it_works": [{"step": "Start", "detail": "The entry point boots the app."}],
    "key_components": [{"name": "main", "path": "README.md", "role": "Docs"}],
    "architecture": "Layered.",
    "learning_path": [{"path": "README.md", "why": "Start here"}],
    "improvements": [{"title": "Add tests", "detail": "More tests", "priority": "high", "category": "Testing"}],
    "mermaid": "flowchart TD\n  A[\"Client\"] --> B[\"Server\"]\n  B --> C[(\"DB\")]",
}


def _vec(text: str, dim: int = 64) -> list[float]:
    h = hashlib.sha256(text.encode()).digest() * 2
    return [b / 255 for b in h[:dim]]


def _reply(messages: list[dict], json_mode: bool) -> str:
    last = messages[-1]["content"] if messages else ""
    if json_mode or "respond ONLY with JSON" in last:
        return json.dumps(INSIGHTS)
    if "single word" in last:
        return "ready"
    return f"Mock answer about the repository. You asked: {last[:80]}. See `README.md:1`."


@app.get("/api/tags")
def tags():
    return {"models": [{"name": "mock:latest"}, {"name": "nomic-embed-text:latest"}]}


@app.post("/api/chat")
async def ollama_chat(req: Request):
    b = await req.json()
    text = _reply(b["messages"], b.get("format") == "json")
    if not b.get("stream", True):
        return {"message": {"role": "assistant", "content": text}, "done": True}

    def gen():
        for i in range(0, len(text), 12):
            yield json.dumps({"message": {"content": text[i:i + 12]}, "done": False}) + "\n"
        yield json.dumps({"done": True}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/embed")
async def ollama_embed(req: Request):
    b = await req.json()
    inp = b["input"] if isinstance(b["input"], list) else [b["input"]]
    return {"embeddings": [_vec(t) for t in inp]}


@app.get("/v1/models")
def models():
    return {"data": [{"id": "models/mock-gpt"}, {"id": "mock-embed"}, {"id": "whisper-large-v3"}]}


@app.post("/v1/chat/completions")
async def oa_chat(req: Request):
    from fastapi.responses import JSONResponse
    if req.headers.get("authorization") == "Bearer bad-key":
        return JSONResponse({"error": {"message": "Invalid API Key"}}, status_code=401)
    b = await req.json()
    if "reasoning_effort" in b:          # like servers that don't support it -> client must retry without
        return JSONResponse({"error": {"message": "Unknown name reasoning_effort"}}, status_code=400)
    text = _reply(b["messages"], bool(b.get("response_format")))
    if not b.get("stream"):
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}

    def gen():
        for i in range(0, len(text), 10):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": text[i:i + 10]}}]}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/embeddings")
async def oa_embed(req: Request):
    b = await req.json()
    inp = b["input"] if isinstance(b["input"], list) else [b["input"]]
    return {"data": [{"index": i, "embedding": _vec(t)} for i, t in enumerate(inp)]}
