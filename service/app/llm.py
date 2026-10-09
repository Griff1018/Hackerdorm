"""LLM client. Hunyuan exposes an OpenAI-compatible API, so any compatible provider works."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from . import cloud_client
from .config import settings

log = logging.getLogger(__name__)

# hy3/hy4 are reasoning models: hidden "thinking" tokens count against max_tokens.
# Reply length is governed by the prompts, so give generous room; if the model still
# runs out before writing an answer, retry once with a bigger budget.
MAX_TOKENS = 6000
RETRY_MAX_TOKENS = 16000
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is not configured")
        _client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url, timeout=120)
    return _client


async def _create(**kwargs: Any) -> Any:
    extra = {"reasoning_effort": settings.llm_reasoning_effort} if settings.llm_reasoning_effort else None
    resp = await client().chat.completions.create(max_tokens=MAX_TOKENS, extra_body=extra, **kwargs)
    choice = resp.choices[0]
    if choice.finish_reason == "length" and not (choice.message.content or choice.message.tool_calls):
        log.warning("Model used the whole token budget thinking; retrying with %d", RETRY_MAX_TOKENS)
        resp = await client().chat.completions.create(max_tokens=RETRY_MAX_TOKENS, extra_body=extra, **kwargs)
    return resp


# --- cloud routing (active only when settings.use_cloud) ----------------------- #
async def _cloud_complete(system: str, user: str | None, *, model: str | None,
                         temperature: float) -> str:
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if user is not None:
        messages.append({"role": "user", "content": user})
    out = await cloud_client.llm_stream(messages, model or settings.llm_model_task, temperature=temperature)
    return _THINK_RE.sub("", out.get("content") or "").strip()


def _ensure_system(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cloud LLM requires a system message as messages[0]; add a default if missing."""
    if not messages or messages[0].get("role") != "system":
        return [{"role": "system", "content": "You are a helpful assistant. Be concise and helpful."}, *messages]
    return messages


async def _cloud_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, *,
                     model: str | None, temperature: float) -> dict[str, Any]:
    messages = _ensure_system(messages)
    return await cloud_client.llm_stream(
        messages, model or settings.llm_model_task, temperature=temperature, tools=tools,
    )


async def complete(
    system: str,
    user: str | None = None,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,  # kept for call-site readability; see MAX_TOKENS
) -> str:
    if settings.use_cloud:
        return await _cloud_complete(system, user, model=model, temperature=temperature)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if user is not None:
        messages.append({"role": "user", "content": user})
    resp = await _create(model=model or settings.llm_model_task, messages=messages, temperature=temperature)
    text = resp.choices[0].message.content or ""
    return _THINK_RE.sub("", text).strip()


async def chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
               *, model: str | None = None, temperature: float = 0.3) -> dict[str, Any]:
    """One tool-calling turn. Returns the assistant message as a plain dict
    ({"role", "content", "tool_calls"?}) so it can be appended to `messages` as-is."""
    if settings.use_cloud:
        return await _cloud_chat(messages, tools, model=model, temperature=temperature)
    kwargs: dict[str, Any] = {"model": model or settings.llm_model_task, "messages": messages,
                              "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
    msg = (await _create(**kwargs)).choices[0].message
    out: dict[str, Any] = {"role": "assistant", "content": _THINK_RE.sub("", msg.content or "").strip()}
    if msg.tool_calls:
        out["tool_calls"] = [
            {"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}}
            for t in msg.tool_calls
        ]
    return out


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply, tolerating code fences and chatter."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object in model output: {text[:200]!r}")
    return json.loads(cleaned[start : end + 1])


async def complete_json(system: str, user: str | None = None, **kwargs: Any) -> dict[str, Any]:
    if settings.use_cloud:
        temperature = kwargs.get("temperature", 0)
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        if user is not None:
            messages.append({"role": "user", "content": user})
        out = await cloud_client.llm_stream(
            messages, settings.llm_model_chat, temperature=temperature,
            response_format={"type": "json_object"},
        )
        text = out.get("content") or ""
        try:
            return parse_json_object(text)
        except (ValueError, json.JSONDecodeError):
            log.warning("Cloud LLM returned invalid JSON, retrying once")
            out = await cloud_client.llm_stream(
                messages + [{"role": "user",
                             "content": "IMPORTANT: Reply with ONE JSON object only."}],
                settings.llm_model_chat, temperature=temperature,
                response_format={"type": "json_object"},
            )
            return parse_json_object(out.get("content") or "")
    kwargs.setdefault("temperature", 0)
    text = await complete(system, user, **kwargs)
    try:
        return parse_json_object(text)
    except (ValueError, json.JSONDecodeError):
        log.warning("Model returned invalid JSON, retrying once")
        text = await complete(
            system + "\n\nIMPORTANT: Your previous reply was not valid JSON. Reply with ONE JSON object only.",
            user,
            **kwargs,
        )
        return parse_json_object(text)
