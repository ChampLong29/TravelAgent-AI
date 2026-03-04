"""
travel/src/travel_agent/nodes/core_nodes/search_hotel.py

Search hotels via AMap POI API (types=100204).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from travel_agent.config import load_settings, default_config_path
from travel_agent.utils.logging import logger

# AMap POI type codes for accommodation
_HOTEL_TYPES = "100204"  # 住宿服务
_BUDGET_KEYWORDS = {
    "economy": "经济型 快捷酒店",
    "mid": "商务酒店",
    "luxury": "五星级酒店 豪华酒店",
}


async def _search_hotels(
    city: str,
    keyword: str,
    api_key: str,
    base_url: str,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "key": api_key,
        "keywords": keyword or "酒店",
        "city": city,
        "types": _HOTEL_TYPES,
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
        logger.warning("[search_hotel] AMap error: %s", data)
        return []
    return data.get("pois", []) or []


def _parse_hotel(poi: Dict[str, Any]) -> Dict[str, Any]:
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
        "rating": poi.get("biz_ext", {}).get("rating", poi.get("rating", "")),
        "cost": poi.get("biz_ext", {}).get("cost", poi.get("cost", "")),
        "photos": photo_urls,
        "id": poi.get("id"),
    }


@tool("search_hotel", return_direct=False)
async def search_hotel_tool(
    city: str,
    keyword: str = "",
    budget_level: str = "mid",
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    搜索指定城市的酒店。

    参数：
    - city: 城市名称，例如 "成都"；
    - keyword: 附加关键词，如 "地铁旁"、"商圈"（可为空）；
    - budget_level: 价格档次，"economy"（经济）/"mid"（商务）/"luxury"（豪华）；
    - max_results: 返回条数（默认 5）。
    """
    cfg = load_settings(default_config_path())
    level_kw = _BUDGET_KEYWORDS.get(budget_level, "")
    full_keyword = " ".join(filter(None, [level_kw, keyword]))
    pois = await _search_hotels(
        city=city,
        keyword=full_keyword,
        api_key=cfg.map.api_key,
        base_url=cfg.map.base_url,
        max_results=max_results,
    )
    return [_parse_hotel(p) for p in pois]
