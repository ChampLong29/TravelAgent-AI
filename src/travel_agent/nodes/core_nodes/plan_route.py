"""
travel/src/travel_agent/nodes/core_nodes/plan_route.py

Plan a driving route between two points using AMap Driving API.
Returns distance, duration, and a polyline of coordinates for map rendering.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from travel_agent.config import load_settings, default_config_path
from travel_agent.utils.logging import logger


# ── helpers ──────────────────────────────────────────────────────────────

_LNGLAT_RE = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")


async def _geocode(address: str, city: str, api_key: str, base_url: str) -> Optional[str]:
    """Convert address/name to 'lng,lat' string via AMap Geocode API."""
    if _LNGLAT_RE.match(address.strip()):
        return address.strip()  # already a coordinate

    url = f"{base_url}/v3/geocode/geo"
    params = {"key": api_key, "address": address, "city": city or "", "output": "json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "1" or not data.get("geocodes"):
        logger.warning("[plan_route] geocode failed for '%s': %s", address, data)
        return None
    return data["geocodes"][0].get("location")


def _decode_polyline(polyline_str: str) -> List[List[float]]:
    """Parse AMap polyline string 'lng1,lat1;lng2,lat2;...' into [[lng,lat],...]."""
    coords: List[List[float]] = []
    if not polyline_str:
        return coords
    for pair in polyline_str.split(";"):
        parts = pair.split(",")
        if len(parts) == 2:
            try:
                coords.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return coords


# ── core call ─────────────────────────────────────────────────────────────

async def _driving_route(
    origin_lnglat: str,
    dest_lnglat: str,
    api_key: str,
    base_url: str,
) -> Dict[str, Any]:
    url = f"{base_url}/v3/direction/driving"
    params = {
        "key": api_key,
        "origin": origin_lnglat,
        "destination": dest_lnglat,
        "extensions": "all",
        "output": "json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "1":
        logger.warning("[plan_route] driving API error: %s", data)
        return {"error": data.get("info", "路线规划失败")}

    routes = data.get("route", {}).get("paths", [])
    if not routes:
        return {"error": "未找到路线"}

    path = routes[0]
    distance_m = int(path.get("distance", 0))
    duration_s = int(path.get("duration", 0))

    # collect all step polylines
    all_coords: List[List[float]] = []
    steps_summary: List[Dict[str, Any]] = []
    for step in path.get("steps", []):
        poly = _decode_polyline(step.get("polyline", ""))
        all_coords.extend(poly)
        steps_summary.append({
            "instruction": step.get("instruction", ""),
            "road": step.get("road", ""),
            "distance": step.get("distance", 0),
            "duration": step.get("duration", 0),
        })

    return {
        "origin": origin_lnglat,
        "destination": dest_lnglat,
        "distance_m": distance_m,
        "distance_km": round(distance_m / 1000, 1),
        "duration_s": duration_s,
        "duration_min": round(duration_s / 60),
        "polyline": all_coords,   # [[lng, lat], ...]  – for map rendering
        "steps": steps_summary,
    }


# ── LangChain tool ────────────────────────────────────────────────────────

@tool("plan_route", return_direct=False)
async def plan_route_tool(
    origin: str,
    destination: str,
    city: str = "",
) -> Dict[str, Any]:
    """
    规划两个地点之间的驾车路线。

    参数：
    - origin: 出发地，可以是地点名称（如 "故宫"）或经纬度（如 "116.4,39.9"）；
    - destination: 目的地，同上；
    - city: 所在城市（用于地名解析，例如 "北京"）。

    返回：
    - distance_km: 总距离（公里）
    - duration_min: 预计耗时（分钟）
    - polyline: 路线折线坐标列表，格式 [[lng, lat], ...]，可直接用于高德地图渲染
    - steps: 逐步导航指令列表
    """
    cfg = load_settings(default_config_path())
    api_key = cfg.map.api_key
    base_url = cfg.map.base_url.rstrip("/")

    origin_lnglat = await _geocode(origin, city, api_key, base_url)
    if not origin_lnglat:
        return {"error": f"无法解析出发地: {origin}"}

    dest_lnglat = await _geocode(destination, city, api_key, base_url)
    if not dest_lnglat:
        return {"error": f"无法解析目的地: {destination}"}

    return await _driving_route(origin_lnglat, dest_lnglat, api_key, base_url)
