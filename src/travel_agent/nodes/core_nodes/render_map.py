"""
travel/src/travel_agent/nodes/core_nodes/render_map.py

A "render-only" tool that formats POI or route data into a structured JSON
block that the frontend can parse to place markers / polylines on the map.

The tool does NOT make any external API calls; it just validates and packages
the data.  The backend (agent_fastapi.py) will detect the tool's output and
append it verbatim to the assistant reply so the frontend can process it.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from travel_agent.utils.logging import logger


def _normalize_marker_type(raw: str) -> str:
    """把高德原始 POI 类型字符串或用户传入的 type 归一化为前端认识的值。"""
    t = (raw or "").lower()
    if any(k in t for k in ("住宿", "酒店", "宾馆", "旅馆", "民宿", "hotel")):
        return "hotel"
    if any(k in t for k in ("餐饮", "美食", "饭店", "餐厅", "小吃", "restaurant", "food")):
        return "restaurant"
    if t in ("route", "路线"):
        return "route"
    return "poi"


@tool("render_map_pois", return_direct=False)
def render_map_pois_tool(
    items: List[Dict[str, Any]],
    title: Optional[str] = None,
) -> str:
    """
    将一组 POI 数据打包为前端可渲染的地图标记数据。

    请在向用户展示景点、酒店、餐厅等地点列表 **之后** 调用此工具，
    以便在地图上显示对应的标记点。

    参数：
    - items: POI 列表，每项需包含：
        - name (str): 地点名称
        - longitude (str|float): 经度（GCJ-02，高德坐标系）
        - latitude (str|float): 纬度
        - type (str, 可选): 地点类型，可选值 poi/hotel/restaurant/route，默认 poi
        - address (str, 可选): 地址描述
        - tel (str, 可选): 电话
        - rating (str, 可选): 评分
    - title: 标注组的标题说明（可选）

    返回：前端 JSON 数据块字符串（内部使用，无需展示给用户）。
    """
    validated: List[Dict[str, Any]] = []
    for item in items:
        try:
            lng = float(item.get("longitude") or item.get("lng") or 0)
            lat = float(item.get("latitude") or item.get("lat") or 0)
        except (TypeError, ValueError):
            continue
        if lng == 0 or lat == 0:
            continue
        validated.append({
            "name":      str(item.get("name") or "地点"),
            "longitude": lng,
            "latitude":  lat,
            "type":      _normalize_marker_type(str(item.get("type") or "poi")),
            "address":   str(item.get("address") or item.get("vicinity") or ""),
            "tel":       str(item.get("tel") or ""),
            "rating":    str(item.get("rating") or (item.get("biz_ext") or {}).get("rating", "") if isinstance(item.get("biz_ext"), dict) else str(item.get("rating") or "")),
            "cost":      str((item.get("biz_ext") or {}).get("cost", "") if isinstance(item.get("biz_ext"), dict) else ""),
        })

    if not validated:
        logger.warning("[render_map_pois] no valid items to render")
        return json.dumps({"__type": "pois", "items": []}, ensure_ascii=False)

    logger.info("[render_map_pois] rendering %d POIs", len(validated))
    result = {"__type": "pois", "items": validated}
    if title:
        result["title"] = title  # type: ignore[assignment]
    return json.dumps(result, ensure_ascii=False)


@tool("render_map_route", return_direct=False)
def render_map_route_tool(
    polyline: List[List[float]],
    origin_name: Optional[str] = None,
    destination_name: Optional[str] = None,
    distance_km: Optional[float] = None,
    duration_min: Optional[float] = None,
) -> str:
    """
    将一条路线的折线坐标打包为前端可渲染的地图路线数据。

    请在向用户展示路线规划结果 **之后** 调用此工具，以便在地图上绘制路线。

    参数：
    - polyline: 坐标列表，每项为 [经度, 纬度]（GCJ-02），例如 [[104.06, 30.66], ...]
    - origin_name: 出发地名称（可选）
    - destination_name: 目的地名称（可选）
    - distance_km: 总距离（公里，可选）
    - duration_min: 预计时长（分钟，可选）

    返回：前端 JSON 数据块字符串（内部使用，无需展示给用户）。
    """
    if not polyline or len(polyline) < 2:
        logger.warning("[render_map_route] polyline too short")
        return json.dumps({"__type": "route", "polyline": []}, ensure_ascii=False)

    result: Dict[str, Any] = {
        "__type": "route",
        "polyline": polyline,
    }
    if origin_name:
        result["origin"] = origin_name
    if destination_name:
        result["destination"] = destination_name
    if distance_km is not None:
        result["distance_km"] = distance_km
    if duration_min is not None:
        result["duration_min"] = duration_min

    logger.info(
        "[render_map_route] rendering route with %d points, %s→%s",
        len(polyline), origin_name, destination_name,
    )
    return json.dumps(result, ensure_ascii=False)
