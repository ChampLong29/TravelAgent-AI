"""
travel/src/travel_agent/nodes/core_nodes/search_restaurant.py

Search restaurants via AMap POI API (types=050000).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from travel_agent.config import load_settings, default_config_path
from travel_agent.utils.logging import logger

# AMap POI type code for restaurants
_RESTAURANT_TYPES = "050000"  # 餐饮服务


async def _search_restaurants(
    city: str,
    keyword: str,
    api_key: str,
    base_url: str,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "key": api_key,
        "keywords": keyword or "餐厅",
        "city": city,
        "types": _RESTAURANT_TYPES,
        "offset": max_results,
        "page": 1,
        "extensions": "all",
        "output": "json",
    }
    url = f"{base_url}/v3/place/text"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "1":
        logger.warning("[search_restaurant] AMap error: %s", data)
        return []
    return data.get("pois", []) or []


def _parse_restaurant(poi: Dict[str, Any]) -> Dict[str, Any]:
    address = poi.get("address", "")
    if isinstance(address, list):
        address = address[0] if address else ""
    tel = poi.get("tel", "")
    if isinstance(tel, list):
        tel = tel[0] if tel else ""

    location_str = poi.get("location", "")
    lng, lat = None, None
    if location_str and "," in location_str:
        try:
            lng, lat = (float(v) for v in location_str.split(",", 1))
        except ValueError:
            pass

    biz = poi.get("biz_ext") or {}
    raw_photos = poi.get("photos") or []
    if isinstance(raw_photos, dict):
        raw_photos = raw_photos.get("photo") or []
    photo_urls = [
        ph.get("url") for ph in raw_photos[:3]
        if isinstance(ph, dict) and ph.get("url", "").startswith("http")
    ]
    return {
        "name": poi.get("name"),
        "address": address,
        "cityname": poi.get("cityname"),
        "type": poi.get("type"),
        "location": location_str,
        "longitude": lng,
        "latitude": lat,
        "tel": tel,
        "rating": biz.get("rating", poi.get("rating", "")),
        "cost": biz.get("cost", poi.get("cost", "")),
        "cuisine": biz.get("tag", ""),
        "photos": photo_urls,
        "id": poi.get("id"),
    }


@tool("search_restaurant", return_direct=False)
async def search_restaurant_tool(
    city: str,
    keyword: str = "",
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    搜索指定城市的餐厅。

    参数：
    - city: 城市名称，例如 "成都"；
    - keyword: 关键词，如 "川菜"、"火锅"、"米其林"（可为空）；
    - max_results: 返回条数（默认 5）。
    """
    cfg = load_settings(default_config_path())
    pois = await _search_restaurants(
        city=city,
        keyword=keyword,
        api_key=cfg.map.api_key,
        base_url=cfg.map.base_url,
        max_results=max_results,
    )
    return [_parse_restaurant(p) for p in pois]
