"""Consume the agent's SSE stream from POST /chat/stream.

Wire format (from agents/src/server.py):
    data: {"type": "tool_call",   "data": {"name": ..., "args": {...}}}
    data: {"type": "tool_result", "data": {"content": "..."}}
    data: {"type": "thinking",    "data": {"content": "..."}}
    data: {"type": "response",    "data": "<final string>"}
    data: {"type": "error",       "data": {"message": "..."}}
    data: {"type": "done",        "data": {}}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

import httpx

from .types import AgentEvent

logger = logging.getLogger(__name__)

EmitFn = Callable[[AgentEvent], Awaitable[None]] | Callable[[AgentEvent], None]


async def stream_prompt(
    base_url: str,
    message: str,
    thread_id: str | None,
    emit: EmitFn,
    *,
    timeout: float = 300.0,
) -> str | None:
    """POST a prompt and stream events. Returns the thread_id from response headers.

    Errors (network, HTTP) are surfaced as AgentEvent(type="error") and re-raised so
    the caller can decide whether to reconnect. The "done" sentinel is also emitted.
    """
    url = f"{base_url.rstrip('/')}/chat/stream"
    payload: dict = {"message": message}
    if thread_id:
        payload["thread_id"] = thread_id

    await _maybe_await(emit(AgentEvent(type="connect", data={"url": url})))

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:500]
                    msg = f"HTTP {resp.status_code}: {body}"
                    await _maybe_await(emit(AgentEvent(type="error", data={"message": msg})))
                    return None

                returned_thread = resp.headers.get("x-thread-id") or thread_id
                async for raw in _iter_sse_data(resp):
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        logger.warning("bad SSE payload: %r (%s)", raw[:120], exc)
                        continue
                    etype = evt.get("type", "error")
                    edata = evt.get("data")
                    await _maybe_await(emit(AgentEvent(type=etype, data=edata)))
                    if etype == "done":
                        break
                return returned_thread
    except httpx.HTTPError as exc:
        await _maybe_await(emit(AgentEvent(type="error", data={"message": f"network: {exc}"})))
        return None
    finally:
        await _maybe_await(emit(AgentEvent(type="disconnect", data={})))


async def _iter_sse_data(resp: httpx.Response):
    """Yield the JSON payloads after each `data: ...` line in an SSE stream."""
    buffer = ""
    async for chunk in resp.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            event_block, buffer = buffer.split("\n\n", 1)
            for line in event_block.splitlines():
                if line.startswith("data:"):
                    yield line[5:].lstrip()


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        await value
