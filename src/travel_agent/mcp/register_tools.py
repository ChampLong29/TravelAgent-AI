"""
travel/src/travel_agent/mcp/register_tools.py

Registers all travel-agent tools with the FastMCP server.

Each tool is a thin async wrapper that:
1. Extracts ``X-Travel-Session-Id`` from the request headers.
2. Gets (or creates) a per-session :class:`ArtifactStore` from the lifespan context.
3. Calls the underlying core-node function with cfg + store injected.
4. Persists the result and returns it to the client.
"""
from __future__ import annotations

import traceback
from typing import Annotated, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from pydantic import Field

from travel_agent.config import Settings
from travel_agent.storage.agent_memory import ArtifactStore

try:
    from travel_agent.utils.logging import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)

# ── lazy imports so missing optional deps don't break the import chain ──

def _get_session_id(ctx: Context) -> str:
    """Extract session id from request headers, fallback to 'default'."""
    try:
        return ctx.request_context.request.headers.get("X-Travel-Session-Id", "default")
    except Exception:
        return "default"


def _get_store(ctx: Context, cfg: Settings) -> ArtifactStore:
    """Get per-session ArtifactStore from the lifespan context."""
    session_id = _get_session_id(ctx)
    mgr = ctx.request_context.lifespan_context          # SessionLifecycleManager
    return mgr.get_store(session_id)


# ────────────────────────────────────────────────────────────────────────
# Tool registration
# ────────────────────────────────────────────────────────────────────────

def register(server: FastMCP, cfg: Settings) -> None:
    """Register all travel tools on *server*."""

    # ── search_poi ──────────────────────────────────────────────────────
    @server.tool(
        name="search_poi",
        description="搜索城市内的景点、酒店、餐厅等地点（POI），返回名称、地址、经纬度等信息。",
    )
    async def mcp_search_poi(
        mcp_ctx: Context[ServerSession, object],
        city: Annotated[str, Field(description="目标城市名称，例如 '北京'")],
        keyword: Annotated[str, Field(description="搜索关键词，例如 '故宫'")],
        types: Annotated[Optional[str], Field(description="POI 类型编码，例如 '110202'（景点）")] = None,
        max_results: Annotated[int, Field(description="返回结果数量，默认 5")] = 5,
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.search_poi import search_poi_tool
            result = await search_poi_tool(city=city, keyword=keyword, types=types, max_results=max_results)
            meta = store.save_result(
                node_id="search_poi",
                payload=result,
                summary=f"POI 搜索: {keyword} @ {city}",
            )
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("[MCP search_poi] %s\n%s", exc, tb)
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── check_weather ───────────────────────────────────────────────────
    @server.tool(
        name="check_weather",
        description="查询指定城市的实时天气或未来 3 天天气预报。",
    )
    async def mcp_check_weather(
        mcp_ctx: Context[ServerSession, object],
        city: Annotated[str, Field(description="城市名称，例如 '上海'")],
        forecast: Annotated[bool, Field(description="True 返回 3 天预报，False 返回实时天气")] = True,
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.check_weather import check_weather_tool
            result = await check_weather_tool(city=city, forecast=forecast)
            meta = store.save_result(
                node_id="check_weather",
                payload=result,
                summary=f"天气查询: {city}",
            )
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("[MCP check_weather] %s\n%s", exc, tb)
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── search_hotel ────────────────────────────────────────────────────
    @server.tool(
        name="search_hotel",
        description="搜索指定城市的酒店，支持按价格档次和关键词筛选。",
    )
    async def mcp_search_hotel(
        mcp_ctx: Context[ServerSession, object],
        city: Annotated[str, Field(description="城市名称")],
        keyword: Annotated[str, Field(description="关键词，例如 '五星级' 或 '快捷酒店'")] = "",
        budget_level: Annotated[str, Field(description="价格档次: economy/mid/luxury")] = "mid",
        max_results: Annotated[int, Field(description="返回结果数量，默认 5")] = 5,
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.search_hotel import search_hotel_tool
            result = await search_hotel_tool(city=city, keyword=keyword, budget_level=budget_level, max_results=max_results)
            meta = store.save_result(
                node_id="search_hotel",
                payload=result,
                summary=f"酒店搜索: {city} ({budget_level})",
            )
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("[MCP search_hotel] %s\n%s", exc, tb)
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── search_restaurant ───────────────────────────────────────────────
    @server.tool(
        name="search_restaurant",
        description="搜索指定城市的餐厅，支持按菜系和关键词筛选。",
    )
    async def mcp_search_restaurant(
        mcp_ctx: Context[ServerSession, object],
        city: Annotated[str, Field(description="城市名称")],
        keyword: Annotated[str, Field(description="关键词，例如 '川菜' 或 '火锅'")] = "",
        max_results: Annotated[int, Field(description="返回结果数量，默认 5")] = 5,
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.search_restaurant import search_restaurant_tool
            result = await search_restaurant_tool(city=city, keyword=keyword, max_results=max_results)
            meta = store.save_result(
                node_id="search_restaurant",
                payload=result,
                summary=f"餐厅搜索: {keyword} @ {city}",
            )
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("[MCP search_restaurant] %s\n%s", exc, tb)
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── plan_route ──────────────────────────────────────────────────────
    @server.tool(
        name="plan_route",
        description="规划两点之间的驾车路线，返回距离、时长和折线坐标。",
    )
    async def mcp_plan_route(
        mcp_ctx: Context[ServerSession, object],
        origin: Annotated[str, Field(description="出发地名称或经纬度 '116.4,39.9'")],
        destination: Annotated[str, Field(description="目的地名称或经纬度")],
        city: Annotated[str, Field(description="所在城市，用于地名解析")] = "",
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.plan_route import plan_route_tool
            result = await plan_route_tool(origin=origin, destination=destination, city=city)
            meta = store.save_result(
                node_id="plan_route",
                payload=result,
                summary=f"路线规划: {origin} → {destination}",
            )
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("[MCP plan_route] %s\n%s", exc, tb)
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── read_artifact ───────────────────────────────────────────────────
    @server.tool(
        name="read_artifact",
        description="通过 artifact_id 读取之前工具调用的持久化结果。",
    )
    async def mcp_read_artifact(
        mcp_ctx: Context[ServerSession, object],
        artifact_id: Annotated[str, Field(description="要读取的 artifact_id")],
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        meta, data = store.load_result(artifact_id)
        if meta is None:
            return {"artifact_id": artifact_id, "result": data, "isError": True}
        return {"artifact_id": artifact_id, "result": data, "isError": False}

    logger.info("[MCP] registered travel tools: search_poi, check_weather, search_hotel, search_restaurant, plan_route, read_artifact")
