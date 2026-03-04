"""
travel/src/travel_agent/mcp/server.py

Travel-agent MCP server built with FastMCP.
Each request carries an ``X-Travel-Session-Id`` header so that the
lifespan-context SessionLifecycleManager can provide a per-session
ArtifactStore to every tool.

Usage (standalone)::

    python -m travel_agent.mcp.server

Or call ``create_server(cfg)`` from agent_fastapi.py / cli.py and run it
inside an asyncio-compatible thread.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from travel_agent.config import Settings, load_settings, default_config_path
from travel_agent.mcp import register_tools
from travel_agent.storage.session_manager import SessionLifecycleManager

try:
    from travel_agent.utils.logging import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


def create_server(cfg: Settings) -> FastMCP:
    """
    Build and return a configured :class:`FastMCP` instance.

    The server is **not** started here — call ``server.run(...)``
    or mount it into an existing ASGI app.
    """

    @asynccontextmanager
    async def session_lifespan(server: FastMCP) -> AsyncIterator[SessionLifecycleManager]:
        logger.info("[MCP] starting session lifecycle manager …")
        mgr = SessionLifecycleManager(
            artifacts_root=cfg.project.outputs_dir,
            cache_root=cfg.mcp_server.server_cache_dir,
            enable_cleanup=True,
        )
        try:
            yield mgr
        finally:
            logger.info("[MCP] cleaning up expired sessions …")
            mgr.cleanup_expired(current_session_id=None)

    server = FastMCP(
        name=cfg.mcp_server.server_name,
        stateless_http=cfg.mcp_server.stateless_http,
        json_response=cfg.mcp_server.json_response,
        lifespan=session_lifespan,
    )

    register_tools.register(server, cfg)
    logger.info("[MCP] server '%s' created with %d tool(s)", cfg.mcp_server.server_name, len(server._tool_manager._tools))
    return server


def main() -> None:
    cfg = load_settings(default_config_path())
    server = create_server(cfg)
    server.settings.host = cfg.mcp_server.connect_host
    server.settings.port = cfg.mcp_server.port
    server.run(transport=cfg.mcp_server.server_transport)


if __name__ == "__main__":
    main()
