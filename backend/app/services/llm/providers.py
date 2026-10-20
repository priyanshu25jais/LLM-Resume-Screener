"""LLM providers: Gemini, OpenAI-compatible (OpenAI, Groq), Ollama, offline, and the backup chain."""
from __future__ import annotations

import asyncio
import contextvars
import logging
import random
import time

import httpx

from ...config import settings
from .base import LLMClient, LLMError, RateLimitError, record_usage

log = logging.getLogger("screener.llm")
RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class _RateLimiter:
    def __init__(self):
        self._lock: asyncio.Lock | None = None
        self._next = 0.0

    async def wait(self) -> None:
        rpm = settings.LLM_REQUESTS_PER_MINUTE
        if rpm <= 0:
            return
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = asyncio.get_running_loop().time()
            if now < self._next:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + 60.0 / rpm


_limiter = _RateLimiter()


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        if resp.headers.get("retry-after"):
            return float(resp.headers["retry-after"])
        for d in resp.json().get("error", {}).get("details", []):
            if str(d.get("@type", "")).endswith("RetryInfo") and d.get("retryDelay"):
                return float(str(d["retryDelay"]).rstrip("s"))
    except (ValueError, AttributeError):
        pass
    return None


async def _post_json(url: str, *, headers: dict, payload: dict, attempts: int = 4, patient: bool = True) -> dict:
    delay = 2.0
    last = ""
    if not patient:
        attempts = min(attempts, 2)
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        for attempt in range(attempts):
            wait = None
            await _limiter.wait()
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last = f"network error: {exc}"
            else:
                if resp.status_code < 400:
                    return resp.json()
                last = f"HTTP {resp.status_code}: {resp.text[:400]}"
                if resp.status_code not in RETRY_STATUS:
                    raise LLMError(last)
                if resp.status_code == 429:
                    wait = _retry_after(resp)
                    if "perday" in resp.text.lower().replace("_", "") or (wait or 0) > 65:
                        raise RateLimitError(f"daily quota exhausted ({last[:200]})", retry_after=max(wait or 0, 3600))
                    if not patient:
                        raise RateLimitError(f"rate limited ({last[:200]})", retry_after=wait or 30)
                    log.warning("rate limited by provider; waiting %.0f s", wait or delay)
            if attempt < attempts - 1:
                await asyncio.sleep(min(wait or delay, 65) + random.random())
                delay *= 2
    raise LLMError(f"request failed after {attempts} attempts ({last})")


class GeminiClient(LLMClient):
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model
        self._cap_output = True

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        config = {"temperature": settings.LLM_TEMPERATURE if temperature is None else temperature}
        if json_mode:
            config["responseMimeType"] = "application/json"
        if self._cap_output and settings.LLM_MAX_OUTPUT_TOKENS > 0:
            config["maxOutputTokens"] = settings.LLM_MAX_OUTPUT_TOKENS
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": config,
        }
        try:
            data = await _post_json(
                f"{self.BASE}/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                payload=payload, patient=self.patient,
            )
        except LLMError as exc:
            if self._cap_output and "maxoutputtokens" in str(exc).lower():
                self._cap_output = False
                return await self.complete(system, user, json_mode=json_mode, temperature=temperature)
            raise
        meta = data.get("usageMetadata") or {}
        record_usage(meta.get("promptTokenCount", 0),
                     meta.get("candidatesTokenCount", 0) + meta.get("thoughtsTokenCount", 0))
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError) as exc:
            cands = data.get("candidates") or [{}]
            reason = (data.get("promptFeedback") or {}).get("blockReason") or cands[0].get("finishReason", "unknown")
            raise LLMError(f"Gemini returned no text (reason: {reason})") from exc


class OpenAICompatibleClient(LLMClient):
    OPTIONAL = ("temperature", "max_completion_tokens", "reasoning_effort")

    def __init__(self, name: str, api_key: str, model: str, base_url: str):
        self.name, self.api_key, self.model = name, api_key, model
        self.base_url = base_url.rstrip("/")
        self._unsupported: set[str] = set()

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        }
        if settings.LLM_MAX_OUTPUT_TOKENS > 0:
            payload["max_completion_tokens"] = settings.LLM_MAX_OUTPUT_TOKENS
        if settings.LLM_REASONING_EFFORT:
            payload["reasoning_effort"] = settings.LLM_REASONING_EFFORT
        for key in self._unsupported:
            payload.pop(key, None)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            data = await _post_json(f"{self.base_url}/chat/completions", headers=headers, payload=payload,
                                    patient=self.patient)
        except LLMError as exc:
            # Some models reject an optional setting: drop it and try once more
            rejected = [k for k in self.OPTIONAL if k in payload and k in str(exc)]
            if rejected and not isinstance(exc, RateLimitError):
                self._unsupported.update(rejected)
                return await self.complete(system, user, json_mode=json_mode, temperature=temperature)
            raise
        usage = data.get("usage") or {}
        record_usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"{self.name} returned an unexpected response") from exc


class OllamaClient(LLMClient):
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url, self.model = base_url.rstrip("/"), model

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        options = {"temperature": settings.LLM_TEMPERATURE if temperature is None else temperature}
        if settings.LLM_MAX_OUTPUT_TOKENS > 0:
            options["num_predict"] = settings.LLM_MAX_OUTPUT_TOKENS
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": options,
        }
        if json_mode:
            payload["format"] = "json"
        data = await _post_json(f"{self.base_url}/api/chat", headers={}, payload=payload, attempts=2,
                                patient=self.patient)
        record_usage(data.get("prompt_eval_count", 0), data.get("eval_count", 0))
        return (data.get("message") or {}).get("content", "")


class OfflineClient(LLMClient):
    name = "offline"
    model = "rule-based"

    @property
    def available(self) -> bool:
        return False

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        raise LLMError("offline mode: no LLM configured")


_answered_by: contextvars.ContextVar[str] = contextvars.ContextVar("answered_by", default="")


class FallbackClient(LLMClient):
    def __init__(self, clients: list[LLMClient]):
        self.clients = clients
        self.name, self.model = clients[0].name, clients[0].model
        self._cooldown: dict[int, float] = {}
        for c in clients:
            c.patient = False

    @property
    def last_label(self) -> str:
        return _answered_by.get() or self.clients[0].label

    @property
    def chain(self) -> list[str]:
        return [c.label for c in self.clients]

    def status(self) -> list[dict]:
        now = time.monotonic()
        return [{"provider": c.label, "cooling_down_s": max(0, round(self._cooldown.get(i, 0) - now))}
                for i, c in enumerate(self.clients)]

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        errors: list[str] = []
        for round_ in range(2):
            now = time.monotonic()
            for i, c in enumerate(self.clients):
                if self._cooldown.get(i, 0) > now:
                    continue
                try:
                    out = await c.complete(system, user, json_mode=json_mode, temperature=temperature)
                    _answered_by.set(c.label)
                    return out
                except RateLimitError as exc:
                    self._cooldown[i] = time.monotonic() + exc.retry_after
                    errors.append(f"{c.label}: {str(exc)[:120]}")
                    log.warning("%s hit its quota (cooling down %.0f s); trying the next provider",
                                c.label, exc.retry_after)
                except LLMError as exc:
                    errors.append(f"{c.label}: {str(exc)[:120]}")
                    log.warning("%s failed, trying the next provider: %s", c.label, str(exc)[:160])
            # All failed or cooling down: if one frees up within a minute, wait once for it
            soonest = min((t for t in self._cooldown.values() if t > time.monotonic()), default=None)
            if round_ == 0 and soonest is not None and soonest - time.monotonic() <= 65:
                await asyncio.sleep(soonest - time.monotonic() + random.random())
                continue
            break
        raise LLMError("all providers failed or are out of quota - " + " | ".join(errors[-4:]))


_client: LLMClient | None = None
_KEYED = [("gemini", lambda: settings.GEMINI_API_KEY), ("groq", lambda: settings.GROQ_API_KEY),
          ("openai", lambda: settings.OPENAI_API_KEY)]


def configured_providers() -> list[str]:
    return [name for name, key in _KEYED if key()]


def build_client(provider: str | None = None, fallbacks: str | None = None) -> LLMClient:
    p = (provider or settings.LLM_PROVIDER or "auto").lower()
    if p == "auto":
        keyed = configured_providers()
        p = keyed[0] if keyed else "offline"
    main = _single(p)
    if isinstance(main, OfflineClient):
        return main
    spec = (fallbacks if fallbacks is not None else settings.LLM_FALLBACKS).lower()
    if spec in ("", "none", "off"):
        return main
    names = configured_providers() if spec == "auto" else [x.strip() for x in spec.split(",") if x.strip()]
    backups = []
    for name in names:
        if name == p:
            continue
        try:
            backups.append(_single(name))
        except LLMError as exc:
            log.warning("backup provider %s skipped: %s", name, exc)
    return FallbackClient([main, *backups]) if backups else main


def _single(p: str) -> LLMClient:
    if p == "gemini":
        if not settings.GEMINI_API_KEY:
            raise LLMError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
        return GeminiClient(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
    if p == "openai":
        if not settings.OPENAI_API_KEY:
            raise LLMError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        return OpenAICompatibleClient("openai", settings.OPENAI_API_KEY, settings.OPENAI_MODEL,
                                      settings.OPENAI_BASE_URL)
    if p == "groq":
        if not settings.GROQ_API_KEY:
            raise LLMError("LLM_PROVIDER=groq but GROQ_API_KEY is not set")
        return OpenAICompatibleClient("groq", settings.GROQ_API_KEY, settings.GROQ_MODEL,
                                      "https://api.groq.com/openai/v1")
    if p == "ollama":
        return OllamaClient(settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)
    return OfflineClient()


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        try:
            _client = build_client()
        except LLMError as exc:
            log.error("%s - falling back to offline mode", exc)
            _client = OfflineClient()
        log.info("LLM provider: %s", _client.label)
    return _client
