"""Common LLM client: JSON validation, retries and token counting."""
from __future__ import annotations

import contextvars
import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger("screener.llm")
T = TypeVar("T", bound=BaseModel)

# Token counter for the current request (each asyncio task gets its own copy)
_usage: contextvars.ContextVar[dict | None] = contextvars.ContextVar("llm_usage", default=None)


def start_usage() -> dict:
    usage = {"input": 0, "output": 0, "total": 0, "calls": 0}
    _usage.set(usage)
    return usage


def record_usage(input_tokens: int, output_tokens: int) -> None:
    usage = _usage.get()
    if usage is not None:
        usage["input"] += int(input_tokens or 0)
        usage["output"] += int(output_tokens or 0)
        usage["total"] = usage["input"] + usage["output"]
        usage["calls"] += 1


def estimate_tokens(text: str) -> int:
    # Rough rule for English text: about 4 characters per token
    return max(1, len(text or "") // 4)


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


class LLMClient:
    name: str = "base"
    model: str = ""
    patient: bool = True  # False when a backup provider can take over instead of waiting

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}" if self.model else self.name

    @property
    def available(self) -> bool:
        return True

    @property
    def last_label(self) -> str:
        return self.label

    @property
    def chain(self) -> list[str]:
        return [self.label]

    async def complete(self, system: str, user: str, *, json_mode: bool = True,
                       temperature: float | None = None) -> str:
        raise NotImplementedError

    async def complete_json(self, system: str, user: str, schema: type[T], *,
                            retries: int = 2, temperature: float | None = None) -> T:
        """Ask the model and parse the reply into `schema`; on bad JSON, ask again with the error."""
        prompt = user
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            usage = _usage.get()
            calls_before = usage["calls"] if usage else 0
            raw = await self.complete(system, prompt, json_mode=True, temperature=temperature)
            if usage is not None and usage["calls"] == calls_before:
                record_usage(estimate_tokens(system + prompt), estimate_tokens(raw))  # provider gave no counts
            try:
                return schema.model_validate(extract_json(raw))
            except (ValueError, ValidationError) as exc:
                last_err = exc
                log.warning("LLM JSON invalid (attempt %d): %s", attempt + 1, str(exc)[:300])
                prompt = (
                    f"{user}\n\nYOUR PREVIOUS REPLY WAS INVALID: {str(exc)[:500]}\n"
                    "Reply again with ONLY one valid JSON object that follows the schema exactly."
                )
        raise LLMError(f"Model did not return valid JSON after {retries + 1} attempts: {last_err}")


def extract_json(raw: str) -> dict:
    """Pull the first JSON object out of a reply, even inside ```json fences or extra text."""
    if raw is None:
        raise ValueError("empty reply")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise ValueError("no JSON object found in reply") from None
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(text[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    obj = json.loads(text[start:i + 1])
                    break
        else:
            raise ValueError("unterminated JSON object in reply")
    if not isinstance(obj, dict):
        raise ValueError("reply JSON is not an object")
    return obj
