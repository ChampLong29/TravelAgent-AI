"""
travel/src/travel_agent/mcp/hooks/tool_interceptors.py

Before/after hooks for MCP tool calls:
- Inject session_id and ArtifactStore before a tool executes.
- Save tool results and append context after a tool returns.

These are intended as middleware helpers, not as FastMCP middleware
(which is not yet part of the public FastMCP API).
"""
from __future__ import annotations

import time
from typing import Any, Callable, Awaitable

from travel_agent.storage.agent_memory import ArtifactStore

try:
    from travel_agent.utils.logging import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


async def before_tool_call(
    tool_name: str,
    session_id: str,
    store: ArtifactStore,
    **kwargs: Any,
) -> dict:
    """
    Called immediately before a tool function is invoked.

    Returns a context dict that is passed to ``after_tool_call``.
    """
    logger.debug("[Hook:before] tool=%s session=%s", tool_name, session_id)
    return {"tool_name": tool_name, "session_id": session_id, "start_ts": time.time()}


async def after_tool_call(
    result: Any,
    ctx: dict,
    store: ArtifactStore,
) -> Any:
    """
    Called after a tool function returns.

    - If the tool result is a dict with ``isError=False`` and a ``result`` key,
      it's already been saved by register_tools; this hook can add extra
      cross-tool context (e.g. inject artifacts into the session context).
    - Returns the (potentially modified) result.
    """
    elapsed = time.time() - ctx.get("start_ts", time.time())
    logger.debug(
        "[Hook:after] tool=%s session=%s elapsed=%.2fs",
        ctx.get("tool_name"),
        ctx.get("session_id"),
        elapsed,
    )
    return result


def wrap_tool(
    tool_fn: Callable[..., Awaitable[Any]],
    tool_name: str,
    session_id: str,
    store: ArtifactStore,
) -> Callable[..., Awaitable[Any]]:
    """
    Wrap an async tool function with before/after hooks.

    Usage::

        wrapped = wrap_tool(my_tool_fn, "search_poi", session_id, store)
        result = await wrapped(**kwargs)
    """
    async def _wrapped(**kwargs: Any) -> Any:
        ctx = await before_tool_call(
            tool_name=tool_name,
            session_id=session_id,
            store=store,
            **kwargs,
        )
        result = await tool_fn(**kwargs)
        return await after_tool_call(result, ctx, store)

    _wrapped.__name__ = tool_fn.__name__
    _wrapped.__doc__ = tool_fn.__doc__
    return _wrapped
