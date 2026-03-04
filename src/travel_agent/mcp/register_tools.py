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

    # ── plan_itinerary ──────────────────────────────────────────────────
    @server.tool(
        name="plan_itinerary",
        description="基于 POI 列表生成结构化多日行程草案（简单均分版，精细规划请用 smart_plan_itinerary）。",
    )
    async def mcp_plan_itinerary(
        mcp_ctx: Context[ServerSession, object],
        city: Annotated[str, Field(description="目标城市名称")],
        days: Annotated[int, Field(description="行程天数")],
        pois: Annotated[list, Field(description="POI 列表，每项含 name/longitude/latitude 等字段")],
        preference: Annotated[str, Field(description="游览偏好描述，例如 '历史文化'")] = "",
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.plan_itinerary import plan_itinerary_tool
            result = plan_itinerary_tool.invoke({"city": city, "days": days, "pois": pois, "preference": preference})
            meta = store.save_result(node_id="plan_itinerary", payload=result, summary=f"行程草案: {city} {days}天")
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP plan_itinerary] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── smart_plan_itinerary ────────────────────────────────────────────
    @server.tool(
        name="smart_plan_itinerary",
        description="智能行程分组：K-means 地理聚类 + 节奏控制，把景点/酒店/餐厅科学分配到各天。",
    )
    async def mcp_smart_plan_itinerary(
        mcp_ctx: Context[ServerSession, object],
        spots: Annotated[list, Field(description="景点列表，每项含 name/longitude/latitude")],
        hotels: Annotated[list, Field(description="酒店列表")],
        restaurants: Annotated[list, Field(description="餐厅列表")],
        days: Annotated[int, Field(description="总天数")],
        city: Annotated[str, Field(description="城市名称")] = "",
        title: Annotated[str, Field(description="行程标题")] = "",
        weather_summary: Annotated[str, Field(description="天气概况，用于识别雨天")] = "",
        pace: Annotated[str, Field(description="节奏: relaxed/standard/intensive")] = "standard",
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.smart_plan_itinerary import smart_plan_itinerary_tool
            result = smart_plan_itinerary_tool.invoke({
                "spots": spots, "hotels": hotels, "restaurants": restaurants,
                "days": days, "city": city, "title": title,
                "weather_summary": weather_summary, "pace": pace,
            })
            meta = store.save_result(node_id="smart_plan_itinerary", payload=result, summary=f"智能行程: {city} {days}天")
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP smart_plan_itinerary] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── estimate_budget ─────────────────────────────────────────────────
    @server.tool(
        name="estimate_budget",
        description="粗略估算旅行预算，返回每日花费和总花费估算。",
    )
    async def mcp_estimate_budget(
        mcp_ctx: Context[ServerSession, object],
        days: Annotated[int, Field(description="行程天数")],
        city_level: Annotated[str, Field(description="城市等级: A（一线）/B（二线）/C（三线）")] = "A",
        hotel_level: Annotated[str, Field(description="酒店档次: budget/mid/luxury")] = "mid",
        with_flight: Annotated[bool, Field(description="是否含往返机票")] = True,
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.estimate_budget import estimate_budget_tool
            result = estimate_budget_tool.invoke({"days": days, "city_level": city_level, "hotel_level": hotel_level, "with_flight": with_flight})
            meta = store.save_result(node_id="estimate_budget", payload=result, summary=f"预算估算: {days}天 {city_level}级城市")
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP estimate_budget] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── recommend_transport ─────────────────────────────────────────────
    @server.tool(
        name="recommend_transport",
        description="根据距离和城市给出交通方式建议（步行/骑行/地铁/城际）。",
    )
    async def mcp_recommend_transport(
        mcp_ctx: Context[ServerSession, object],
        distance_km: Annotated[float, Field(description="距离（千米）")],
        city: Annotated[str, Field(description="所在城市")],
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.recommend_transport import recommend_transport_tool
            result = recommend_transport_tool.invoke({"distance_km": distance_km, "city": city})
            meta = store.save_result(node_id="recommend_transport", payload=result, summary=f"交通建议: {city} {distance_km}km")
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP recommend_transport] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── format_itinerary ────────────────────────────────────────────────
    @server.tool(
        name="format_itinerary",
        description="将已收集的旅行数据整理成结构化 Markdown 格式行程报告（调用 LLM 生成）。",
    )
    async def mcp_format_itinerary(
        mcp_ctx: Context[ServerSession, object],
        city: Annotated[str, Field(description="目标城市名称")],
        days: Annotated[int, Field(description="行程天数")],
        travelers: Annotated[int, Field(description="出行人数")] = 2,
        budget: Annotated[str, Field(description="预算描述，如 '500元/天'")] = "适中",
        raw_data: Annotated[str, Field(description="各工具返回的数据汇总（JSON 字符串或文本）")] = "",
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.format_itinerary import format_itinerary_tool
            result = await format_itinerary_tool.ainvoke({"city": city, "days": days, "travelers": travelers, "budget": budget, "raw_data": raw_data})
            meta = store.save_result(node_id="format_itinerary", payload=result, summary=f"行程报告: {city} {days}天")
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP format_itinerary] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── render_map_pois ─────────────────────────────────────────────────
    @server.tool(
        name="render_map_pois",
        description="将 POI 列表打包为前端地图可渲染的标记数据（不调用外部 API）。",
    )
    async def mcp_render_map_pois(
        mcp_ctx: Context[ServerSession, object],
        items: Annotated[list, Field(description="POI 列表，每项含 name/longitude/latitude/type")],
        title: Annotated[Optional[str], Field(description="标注组标题")] = None,
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.render_map import render_map_pois_tool
            result = render_map_pois_tool.invoke({"items": items, "title": title})
            meta = store.save_result(node_id="render_map_pois", payload=result, summary=f"地图渲染: {len(items)} 个 POI")
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP render_map_pois] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── render_map_route ────────────────────────────────────────────────
    @server.tool(
        name="render_map_route",
        description="将路线折线坐标打包为前端地图可渲染的路线数据。",
    )
    async def mcp_render_map_route(
        mcp_ctx: Context[ServerSession, object],
        polyline: Annotated[list, Field(description="折线坐标列表，每项为 [lng, lat]")],
        origin: Annotated[str, Field(description="出发地名称")] = "",
        destination: Annotated[str, Field(description="目的地名称")] = "",
        distance_km: Annotated[Optional[float], Field(description="距离（千米）")] = None,
        duration_min: Annotated[Optional[float], Field(description="时长（分钟）")] = None,
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.render_map import render_map_route_tool
            result = render_map_route_tool.invoke({"polyline": polyline, "origin": origin, "destination": destination, "distance_km": distance_km, "duration_min": duration_min})
            meta = store.save_result(node_id="render_map_route", payload=result, summary=f"路线渲染: {origin}→{destination}")
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP render_map_route] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── render_itinerary ────────────────────────────────────────────────
    @server.tool(
        name="render_itinerary",
        description="将完整行程规划打包为地图可渲染的有序景点数据，前端按天分组标注并连线。",
    )
    async def mcp_render_itinerary(
        mcp_ctx: Context[ServerSession, object],
        days: Annotated[list, Field(description="每天安排列表，每项含 day/label/spots")],
        city: Annotated[str, Field(description="城市名称")] = "",
        title: Annotated[str, Field(description="行程标题")] = "",
    ) -> dict:
        store = _get_store(mcp_ctx, cfg)
        try:
            from travel_agent.nodes.core_nodes.render_itinerary import render_itinerary_tool
            result = render_itinerary_tool.invoke({"days": days, "city": city, "title": title})
            meta = store.save_result(node_id="render_itinerary", payload=result, summary=f"行程渲染: {city}")
            return {"artifact_id": meta.artifact_id, "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP render_itinerary] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── validate_json ───────────────────────────────────────────────────
    @server.tool(
        name="validate_json",
        description="检查字符串是否为合法 JSON。",
    )
    async def mcp_validate_json(
        mcp_ctx: Context[ServerSession, object],
        payload: Annotated[str, Field(description="待检查的字符串")],
    ) -> dict:
        try:
            from travel_agent.nodes.core_nodes.json_tools import validate_json_tool
            result = validate_json_tool.invoke({"payload": payload})
            return {"artifact_id": "", "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP validate_json] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    # ── fix_json ────────────────────────────────────────────────────────
    @server.tool(
        name="fix_json",
        description="利用 LLM 对接近 JSON 但不合法的文本进行纠错。",
    )
    async def mcp_fix_json(
        mcp_ctx: Context[ServerSession, object],
        raw_text: Annotated[str, Field(description="原始字符串（可能含多余说明、尾逗号等）")],
        instruction: Annotated[str, Field(description="可选 schema 提示")] = "",
    ) -> dict:
        try:
            from travel_agent.nodes.core_nodes.json_tools import fix_json_tool
            result = await fix_json_tool.ainvoke({"raw_text": raw_text, "instruction": instruction})
            return {"artifact_id": "", "result": result, "isError": False}
        except Exception as exc:
            logger.error("[MCP fix_json] %s", traceback.format_exc())
            return {"artifact_id": "", "result": str(exc), "isError": True}

    logger.info("[MCP] registered all 14 travel tools")
