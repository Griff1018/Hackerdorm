"""Cloud service client — the single isolated wrapper around the WorkBuddy cloud REST surfaces.

Why this exists: the official cloud SDK (`@tencent-ai/workbuddy-cloud-sdk`) is JavaScript/TypeScript
only, but this backend is Python. Every cloud operation here is server-side, so this module mirrors
the SDK's contract with `httpx`. It is the ONLY file that talks to the cloud; everything else
(`db.py`, `llm.py`, `dashboard.py`, ...) calls through here.

All paths are centralized in the BASE_* constants. They follow the SDK's documented surfaces
(`/.cloud/database/rest`, `/.cloud/auth/v1`, ...). VERIFY each one against the live SDK/activation
payload before flipping `use_cloud` on — the exact raw REST paths are reconfirmed when publicConfig
is available.

Behaviour is inert unless `settings.use_cloud` is True (i.e. CLOUD_ENDPOINT + CLOUD_PUBLISHABLE_KEY
are set). Nothing in here runs on the local-only app.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from .config import settings

log = logging.getLogger(__name__)

# --- REST base paths (VERIFY against live SDK on activation) -------------------
BASE_DB = "/.cloud/database/rest"          # PostgREST; tables under here
BASE_AUTH = "/.cloud/auth/v1"              # signin, user/me, token refresh
BASE_LLM = "/.cloud/llm/v1/chat/completions"  # OpenAI-compatible, streaming SSE
BASE_STORAGE = "/.cloud/storage/v1"        # object upload / signed url

# Agent session (set by auth_signin / refreshed automatically).
_agent_token: dict[str, Any] | None = None
_token_expiry = 0.0

# Module-level sync client (lazy) for DB/Auth/Storage.
_sync: httpx.Client | None = None


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #
def _endpoint() -> str:
    return settings.cloud_endpoint.rstrip("/")


def _pubkey() -> str:
    return settings.cloud_publishable_key


def _sync_client() -> httpx.Client:
    global _sync
    if _sync is None:
        _sync = httpx.Client(timeout=30.0)
    return _sync


def _base_headers() -> dict[str, str]:
    return {"apikey": _pubkey(), "Content-Type": "application/json"}


def _current_token() -> str | None:
    global _agent_token, _token_expiry
    if _agent_token and time.time() < _token_expiry - 30:
        return _agent_token.get("access_token")
    return None


def _auth_headers() -> dict[str, str]:
    h = _base_headers()
    tok = _current_token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def auth_signin(email: str, password: str) -> dict[str, Any]:
    """Sign in the agent (email+password) and cache the session. Returns the session dict."""
    global _agent_token, _token_expiry
    url = f"{_endpoint()}{BASE_AUTH}/signin"
    r = _sync_client().post(
        url,
        headers=_base_headers(),
        json={"email": email, "password": password},
    )
    r.raise_for_status()
    data = r.json()
    # Accept either {data:{session:...}} or a flat token object.
    sess = (data.get("data") or {}).get("session") or data.get("session") or data
    _agent_token = sess
    expires_in = float(sess.get("expires_in") or 3600)
    _token_expiry = time.time() + expires_in
    log.info("Cloud Auth: agent signed in (uid=%s)", sess.get("user", {}).get("id") if sess.get("user") else "?")
    return sess


def auth_token_valid() -> bool:
    return _current_token() is not None


def auth_user_me(token: str | None = None) -> dict[str, Any] | None:
    """Validate a session token; returns the user dict or None if not signed in.
    When `token` is given it is verified directly (used to authorize dashboard requests);
    otherwise the cached agent token is used."""
    tok = token or _current_token()
    if not tok:
        return None
    headers = {**_base_headers(), "Authorization": f"Bearer {tok}"}
    r = _sync_client().get(f"{_endpoint()}{BASE_AUTH}/user/me", headers=headers)
    if r.status_code == 401:
        return None
    r.raise_for_status()
    return r.json().get("data", {}).get("user") or r.json().get("user")


def agent_uid() -> str | None:
    user = auth_user_me()
    return user.get("id") if user else None


def ensure_signed_in() -> None:
    """Called at startup so all subsequent cloud calls carry the agent identity (owner_id RLS)."""
    if auth_token_valid():
        return
    if not (settings.cloud_admin_email and settings.cloud_admin_password):
        log.warning("Cloud: use_cloud=True but CLOUD_ADMIN_EMAIL/PASSWORD not set; writes will fail RLS.")
        return
    auth_signin(settings.cloud_admin_email, settings.cloud_admin_password)


# --------------------------------------------------------------------------- #
# Database (PostgREST)
# --------------------------------------------------------------------------- #
def db_select(table: str, columns: str = "*", filters: dict[str, Any] | None = None,
              raw_filters: dict[str, str] | None = None,
              order: str | None = None, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
    url = f"{_endpoint()}{BASE_DB}/{table}"
    params: dict[str, str] = {}
    if columns != "*":
        params["select"] = columns
    if filters:
        for k, v in filters.items():
            params[k] = f"eq.{v}"
    if raw_filters:
        params.update(raw_filters)
    if order:
        params["order"] = order
    if limit is not None:
        params["limit"] = str(limit)
        params["offset"] = str(offset)
    r = _sync_client().get(url, headers=_auth_headers(), params=params)
    r.raise_for_status()
    return r.json()


def db_select_one(table: str, columns: str = "*", filters: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = db_select(table, columns, filters, limit=1)
    return rows[0] if rows else None


def db_insert(table: str, row: dict[str, Any]) -> dict[str, Any]:
    # Never send owner_id; the DB fills DEFAULT auth.uid().
    row = {k: v for k, v in row.items() if k != "owner_id"}
    url = f"{_endpoint()}{BASE_DB}/{table}"
    r = _sync_client().post(
        url, headers={**_auth_headers(), "Prefer": "return=representation"}, json=row,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if isinstance(data, list) and data else (data or {})


def db_update(table: str, row_id: int | str, values: dict[str, Any]) -> dict[str, Any]:
    values = {k: v for k, v in values.items() if k != "owner_id"}
    url = f"{_endpoint()}{BASE_DB}/{table}?id=eq.{row_id}"
    r = _sync_client().patch(
        url, headers={**_auth_headers(), "Prefer": "return=representation"}, json=values,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if isinstance(data, list) and data else (data or {})


def db_delete(table: str, row_id: int | str) -> None:
    url = f"{_endpoint()}{BASE_DB}/{table}?id=eq.{row_id}"
    r = _sync_client().delete(url, headers=_auth_headers())
    r.raise_for_status()


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def storage_upload(object_path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    url = f"{_endpoint()}{BASE_STORAGE}/object/{object_path}"
    r = _sync_client().post(
        url,
        headers={**_auth_headers(), "Content-Type": content_type, "x-upsert": "true"},
        content=data,
    )
    r.raise_for_status()


def storage_signed_url(object_path: str, ttl: int = 600) -> str:
    url = f"{_endpoint()}{BASE_STORAGE}/object/sign/{object_path}"
    r = _sync_client().post(url, headers=_auth_headers(), json={"expiresIn": ttl})
    r.raise_for_status()
    return r.json().get("signedURL") or ""


# --------------------------------------------------------------------------- #
# LLM (async, streaming SSE — required by the cloud API)
# --------------------------------------------------------------------------- #
async def llm_stream(messages: list[dict[str, Any]], model: str, *,
                     temperature: float = 0.7, tools: list[dict[str, Any]] | None = None,
                     response_format: dict[str, Any] | None = None) -> dict[str, Any]:
    """Stream a chat completion and accumulate the result. Returns an assistant-message-shaped dict:
    {"role": "assistant", "content": str, "tool_calls"?: list}. Mirrors llm.chat()'s return shape.

    The cloud LLM API REQUIRES stream:true (non-streaming is rejected). A `system` message must be
    messages[0] — callers must ensure this (llm.py guards it).
    """
    url = f"{_endpoint()}{BASE_LLM}"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools
    if response_format:
        payload["response_format"] = response_format

    content = ""
    tool_calls: dict[int, dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST", url, headers=_auth_headers(), json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[len("data:"):].strip()
                if chunk == "[DONE]":
                    break
                try:
                    evt = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                choices = evt.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                if delta.get("content"):
                    content += delta["content"]
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    acc = tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        acc["name"] = fn["name"]
                    if fn.get("arguments"):
                        acc["arguments"] += fn["arguments"]

    out: dict[str, Any] = {"role": "assistant", "content": content.strip()}
    if tool_calls:
        out["tool_calls"] = [
            {"id": t["id"], "type": "function",
             "function": {"name": t["name"], "arguments": t["arguments"]}}
            for t in tool_calls.values()
        ]
    return out
