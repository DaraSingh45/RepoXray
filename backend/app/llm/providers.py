"""LLM provider abstraction: Ollama (local), OpenAI-compatible APIs, Anthropic, or none.

Every call degrades gracefully: callers get LLMError and fall back to heuristics."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterator

import httpx

from .. import db
from ..config import get_settings


class LLMError(Exception):
    pass


OPENAI_COMPAT = ("openai", "groq", "gemini")
PROVIDERS = ("ollama", "groq", "gemini", "openai", "anthropic", "none")

# Defaults used when a provider is chosen for the first time. Model names change over time:
# the Settings page lists the provider's live models once a key is saved.
DEFAULTS: dict[str, dict] = {
    "ollama": {"base_url": "http://localhost:11434", "model": "llama3.1:8b", "embed_model": "nomic-embed-text"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile", "embed_model": ""},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash",
               "embed_model": "gemini-embedding-001"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "embed_model": "text-embedding-3-small"},
    "anthropic": {"base_url": "https://api.anthropic.com", "model": "", "embed_model": ""},
    "none": {"base_url": "", "model": "", "embed_model": ""},
}
DEFAULT_URLS = {k: v["base_url"] for k, v in DEFAULTS.items()}

# Free tiers of hosted APIs have small per-minute token limits; keep prompts within them.
CONTEXT_CAP = {"groq": 14_000, "gemini": 60_000}


@dataclass
class LLMConfig:
    provider: str = "ollama"      # ollama | groq | gemini | openai | anthropic | none
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    embed_model: str = ""
    temperature: float = 0.2
    key_source: str = ""          # "settings" | "env" | ""

    @property
    def enabled(self) -> bool:
        return self.provider != "none" and bool(self.model)

    @property
    def compat(self) -> bool:
        return self.provider in OPENAI_COMPAT

    def context_budget(self, default: int) -> int:
        return min(default, CONTEXT_CAP.get(self.provider, default))

    def public(self) -> dict:
        d = asdict(self)
        d["api_key"] = ("•" * 8 + self.api_key[-4:]) if self.api_key else ""
        d["has_api_key"] = bool(self.api_key)
        saved = _saved()
        d["profiles"] = {p: _profile(p, saved) for p in PROVIDERS}
        d["keys"] = {p: _key(p, saved)[1] for p in PROVIDERS if p not in ("ollama", "none")}
        return d


def _saved() -> dict:
    saved = db.get_setting("llm") or {}
    if "profiles" not in saved and saved.get("provider"):          # migrate old flat format
        p = saved["provider"]
        saved = {"provider": p, "temperature": saved.get("temperature", 0.2),
                 "profiles": {p: {k: saved[k] for k in ("base_url", "model", "embed_model") if k in saved}},
                 "api_keys": {p: saved["api_key"]} if saved.get("api_key") else {}}
    return saved


def _env_key(provider: str) -> str:
    s = get_settings()
    specific = {"groq": s.groq_api_key, "gemini": s.gemini_api_key, "openai": s.openai_api_key,
                "anthropic": s.anthropic_api_key}.get(provider, "")
    if specific:
        return specific
    # generic key only applies to the provider configured in .env
    return s.llm_api_key if provider == s.llm_provider else ""


def _key(provider: str, saved: dict) -> tuple[str, str]:
    k = (saved.get("api_keys") or {}).get(provider)
    if k:
        return k, "settings"
    k = _env_key(provider)
    return (k, "env") if k else ("", "")


def _profile(provider: str, saved: dict) -> dict:
    s = get_settings()
    base = dict(DEFAULTS.get(provider, DEFAULTS["none"]))
    if provider == "ollama" and s.llm_base_url:          # REPOXRAY_LLM_BASE_URL / OLLAMA_URL point at Ollama
        base["base_url"] = s.llm_base_url
    if provider == s.llm_provider:                       # .env model defaults apply to the .env provider
        base.update({"model": s.llm_model or base["model"],
                     "embed_model": s.embed_model if provider in ("ollama", "openai", "gemini") else ""})
    for k, v in ((saved.get("profiles") or {}).get(provider) or {}).items():
        if v is not None:
            base[k] = v
    return base


def get_config() -> LLMConfig:
    s = get_settings()
    saved = _saved()
    provider = saved.get("provider") or s.llm_provider
    if provider not in PROVIDERS:
        provider = "none"
    prof = _profile(provider, saved)
    key, src = _key(provider, saved)
    cfg = LLMConfig(provider=provider, base_url=(prof.get("base_url") or DEFAULT_URLS.get(provider, "")).rstrip("/"),
                    model=prof.get("model") or "", embed_model=prof.get("embed_model") or "", api_key=key,
                    temperature=float(saved.get("temperature", 0.2)), key_source=src)
    return cfg


def save_config(data: dict) -> LLMConfig:
    saved = _saved()
    provider = data.get("provider") or saved.get("provider") or get_settings().llm_provider
    saved["provider"] = provider
    if data.get("temperature") is not None:
        saved["temperature"] = data["temperature"]
    prof = (saved.setdefault("profiles", {})).setdefault(provider, {})
    for k in ("base_url", "model", "embed_model"):
        if data.get(k) is not None:
            prof[k] = data[k].strip()
    keys = saved.setdefault("api_keys", {})
    if data.get("api_key"):            # only overwrite a key when a new one is typed
        keys[provider] = data["api_key"].strip()
    if data.get("clear_api_key"):
        keys.pop(provider, None)
    db.set_setting("llm", saved)
    return get_config()


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(get_settings().llm_timeout, connect=8)


def _err(r: httpx.Response) -> LLMError:
    try:
        j = r.json()
        msg = j.get("error", {}).get("message") if isinstance(j.get("error"), dict) else j.get("error") or j.get("message") or r.text
    except Exception:
        msg = r.text
    return LLMError(f"{r.status_code}: {str(msg)[:300]}")


# ------------------------------------------------------------------ chat

THINK_RE = __import__("re").compile(r"<think>.*?(</think>|$)", __import__("re").S)


def strip_thinking(text: str) -> str:
    return THINK_RE.sub("", text or "").strip()


def chat(messages: list[dict], cfg: LLMConfig | None = None, json_mode: bool = False, max_tokens: int = 3000) -> str:
    return strip_thinking("".join(chat_stream(messages, cfg, json_mode=json_mode, max_tokens=max_tokens, stream=False)))


def without_thinking(tokens: Iterator[str]) -> Iterator[str]:
    """Filters <think>...</think> sections out of a token stream."""
    buf, inside = "", False
    for tok in tokens:
        buf += tok
        while True:
            if inside:
                end = buf.find("</think>")
                if end == -1:
                    buf = buf[-8:]
                    break
                buf, inside = buf[end + 8:].lstrip(), False
            else:
                start = buf.find("<think>")
                if start == -1:
                    keep = 7 if "<" in buf[-7:] else 0          # a tag may be split across tokens
                    out, buf = (buf[:-keep], buf[-keep:]) if keep else (buf, "")
                    if out:
                        yield out
                    break
                if buf[:start]:
                    yield buf[:start]
                buf, inside = buf[start + 7:], True
    if buf and not inside:
        yield buf


def chat_stream(messages: list[dict], cfg: LLMConfig | None = None, json_mode: bool = False,
                max_tokens: int = 3000, stream: bool = True) -> Iterator[str]:
    cfg = cfg or get_config()
    if not cfg.enabled:
        raise LLMError("No LLM configured")
    try:
        if cfg.provider == "ollama":
            yield from _ollama_chat(cfg, messages, json_mode, stream)
        elif cfg.compat:
            if not cfg.api_key and cfg.provider in ("groq", "gemini"):
                raise LLMError(f"No API key for {cfg.provider}. Add it in Settings or in .env.")
            yield from _openai_chat(cfg, messages, json_mode, max_tokens, stream)
        elif cfg.provider == "anthropic":
            if not cfg.api_key:
                raise LLMError("No API key for anthropic. Add it in Settings or in .env.")
            yield from _anthropic_chat(cfg, messages, max_tokens, stream)
        else:
            raise LLMError(f"Unknown provider {cfg.provider}")
    except httpx.ConnectError as e:
        raise LLMError(f"Cannot reach {cfg.provider} at {cfg.base_url}. Is it running?") from e
    except httpx.TimeoutException as e:
        raise LLMError(f"{cfg.provider} timed out") from e
    except httpx.HTTPError as e:
        raise LLMError(f"{cfg.provider} request failed: {type(e).__name__}") from e
    except (ValueError, KeyError, IndexError) as e:
        raise LLMError(f"{cfg.provider} returned an unexpected response") from e


def _ollama_chat(cfg: LLMConfig, messages, json_mode, stream) -> Iterator[str]:
    body = {"model": cfg.model, "messages": messages, "stream": stream,
            "options": {"temperature": cfg.temperature, "num_ctx": 16384}}
    if json_mode:
        body["format"] = "json"
    with httpx.Client(timeout=_timeout()) as c:
        if not stream:
            r = c.post(f"{cfg.base_url}/api/chat", json=body)
            if r.status_code != 200:
                raise _err(r)
            yield r.json().get("message", {}).get("content", "")
            return
        with c.stream("POST", f"{cfg.base_url}/api/chat", json=body) as r:
            if r.status_code != 200:
                r.read()
                raise _err(r)
            for line in r.iter_lines():
                if not line:
                    continue
                j = json.loads(line)
                if j.get("error"):
                    raise LLMError(j["error"])
                piece = j.get("message", {}).get("content", "")
                if piece:
                    yield piece


def _post_with_retry(c: httpx.Client, url: str, body: dict, stream: bool):
    """POST with two safety nets: retry once without optional fields on 400 (some compatible
    servers reject response_format / reasoning_effort) and wait once on 429 rate limits."""
    import time
    attempt_body = dict(body)
    for attempt in range(3):
        req = c.build_request("POST", url, json=attempt_body)
        r = c.send(req, stream=stream)
        optional = ("response_format", "reasoning_effort", "reasoning_format")
        if r.status_code == 400 and any(k in attempt_body for k in optional):
            r.read(); r.close()
            attempt_body = {k: v for k, v in attempt_body.items() if k not in optional}
            continue
        if r.status_code == 429 and attempt < 2:
            wait = r.headers.get("retry-after")
            r.read(); r.close()
            try:
                delay = min(float(wait), 25.0) if wait else 8.0
            except ValueError:
                delay = 8.0
            time.sleep(delay)
            continue
        return r
    return r


def _openai_chat(cfg: LLMConfig, messages, json_mode, max_tokens, stream) -> Iterator[str]:
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    body: dict = {"model": cfg.model, "messages": messages, "temperature": cfg.temperature, "stream": stream,
                  "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if cfg.provider == "gemini":
        body["reasoning_effort"] = "low"          # keep "thinking" short so the answer fits max_tokens
        body["max_tokens"] = max_tokens + 2048
    if cfg.provider == "groq":
        body["max_tokens"] = min(max_tokens, 4096)
        if any(x in cfg.model.lower() for x in ("qwen", "gpt-oss", "deepseek", "qwq", "kimi", "minimax")):
            body["reasoning_format"] = "hidden"   # return only the final answer, no <think> text
    url = f"{cfg.base_url}/chat/completions"
    with httpx.Client(timeout=_timeout(), headers=headers) as c:
        r = _post_with_retry(c, url, body, stream)
        try:
            if r.status_code != 200:
                r.read()
                raise _err(r)
            if not stream:
                r.read()
                yield r.json()["choices"][0]["message"].get("content") or ""
                return
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                except Exception:
                    continue
                if delta:
                    yield delta
        finally:
            r.close()


def _anthropic_chat(cfg: LLMConfig, messages, max_tokens, stream) -> Iterator[str]:
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    msgs = [m for m in messages if m["role"] != "system"]
    headers = {"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    body = {"model": cfg.model, "max_tokens": max_tokens, "messages": msgs, "temperature": cfg.temperature, "stream": stream}
    if system:
        body["system"] = system
    url = f"{cfg.base_url}/v1/messages"
    with httpx.Client(timeout=_timeout(), headers=headers) as c:
        if not stream:
            r = c.post(url, json=body)
            if r.status_code != 200:
                raise _err(r)
            yield "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
            return
        with c.stream("POST", url, json=body) as r:
            if r.status_code != 200:
                r.read()
                raise _err(r)
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    j = json.loads(line[5:].strip())
                except Exception:
                    continue
                if j.get("type") == "content_block_delta":
                    t = j.get("delta", {}).get("text")
                    if t:
                        yield t
                elif j.get("type") == "error":
                    raise LLMError(str(j.get("error")))


# ------------------------------------------------------------------ embeddings

def embed(texts: list[str], cfg: LLMConfig | None = None) -> list[list[float]]:
    cfg = cfg or get_config()
    if (cfg.provider != "ollama" and not cfg.compat) or not cfg.embed_model:
        raise LLMError("Embeddings not available for this provider")
    try:
        if cfg.provider == "ollama":
            with httpx.Client(timeout=_timeout()) as c:
                r = c.post(f"{cfg.base_url}/api/embed", json={"model": cfg.embed_model, "input": texts})
                if r.status_code == 404:  # older Ollama versions
                    out = []
                    for t in texts:
                        r1 = c.post(f"{cfg.base_url}/api/embeddings", json={"model": cfg.embed_model, "prompt": t})
                        if r1.status_code != 200:
                            raise _err(r1)
                        out.append(r1.json()["embedding"])
                    return out
                if r.status_code != 200:
                    raise _err(r)
                return r.json()["embeddings"]
        headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
        with httpx.Client(timeout=_timeout(), headers=headers) as c:
            r = _post_with_retry(c, f"{cfg.base_url}/embeddings", {"model": cfg.embed_model, "input": texts}, False)
            r.read()
            if r.status_code != 200:
                raise _err(r)
            data = r.json()["data"]
            return [d["embedding"] for d in sorted(data, key=lambda d: d.get("index", 0))]
    except httpx.HTTPError as e:
        raise LLMError(f"Embedding request failed: {e}") from e


# ------------------------------------------------------------------ health / models

def health(cfg: LLMConfig | None = None) -> dict:
    cfg = cfg or get_config()
    out = {"provider": cfg.provider, "model": cfg.model, "ok": False, "message": "", "models": [], "embeddings": False}
    if cfg.provider == "none":
        out["message"] = "LLM disabled — RepoXray runs in heuristic mode."
        return out
    try:
        out["models"] = list_models(cfg)
    except Exception as e:  # noqa: BLE001
        out["message"] = str(e)[:300]
    try:
        reply = chat([{"role": "user", "content": "Reply with the single word: ready"}], cfg, max_tokens=10)
        out["ok"] = bool(reply.strip())
        out["message"] = f"Model replied: {reply.strip()[:60]}"
    except Exception as e:  # noqa: BLE001
        out["message"] = str(e)[:300]
    if (cfg.provider == "ollama" or cfg.compat) and cfg.embed_model:
        try:
            out["embeddings"] = bool(embed(["hello"], cfg))
        except Exception as e:  # noqa: BLE001
            out["embed_message"] = str(e)[:200]
    return out


def list_models(cfg: LLMConfig | None = None) -> list[str]:
    cfg = cfg or get_config()
    try:
        with httpx.Client(timeout=8) as c:
            if cfg.provider == "ollama":
                r = c.get(f"{cfg.base_url}/api/tags")
                r.raise_for_status()
                return [m["name"] for m in r.json().get("models", [])]
            if cfg.compat:
                r = c.get(f"{cfg.base_url}/models", headers={"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {})
                r.raise_for_status()
                ids = [str(m.get("id", "")).removeprefix("models/") for m in r.json().get("data", [])]
                skip = ("whisper", "tts", "guard", "playai", "orpheus", "imagen", "veo", "aqa", "dall-e", "moderation", "audio", "image")
                return sorted(i for i in ids if i and not any(x in i.lower() for x in skip))[:300]
            if cfg.provider == "anthropic":
                r = c.get(f"{cfg.base_url}/v1/models", headers={"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01"})
                r.raise_for_status()
                return [m["id"] for m in r.json().get("data", [])]
    except httpx.HTTPStatusError as e:
        raise _err(e.response) from e
    except httpx.HTTPError as e:          # offline, DNS failure, proxy, TLS, timeout...
        raise LLMError(f"Cannot reach {cfg.base_url} ({type(e).__name__})") from e
    except (ValueError, KeyError) as e:
        raise LLMError(f"Unexpected response from {cfg.base_url}") from e
    return []


def parse_json(text: str) -> dict | None:
    """Tolerant JSON extraction for LLM output."""
    if not text:
        return None
    t = strip_thinking(text)
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        return None
    chunk = t[start:end + 1]
    for attempt in (chunk, _repair(chunk)):
        try:
            v = json.loads(attempt)
            return v if isinstance(v, dict) else None
        except Exception:
            continue
    return None


def _repair(s: str) -> str:
    import re
    s = re.sub(r",\s*([}\]])", r"\1", s)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s)
    return s
