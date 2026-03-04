from __future__ import annotations

from typing import List, Dict, Any, Optional

import httpx
from langchain_core.tools import tool

from travel_agent.config import load_settings, default_config_path
from travel_agent.utils.logging import logger


async def _amap_place_text_search(
    keyword: str,
    api_key: str,
    base_url: str,
    city: Optional[str] = None,
    types: Optional[str] = None,
    page_size: int = 10,
) -> List[Dict[str, Any]]:
    """使用高德关键字搜索接口检索 POI。"""
    params: Dict[str, Any] = {
        "key": api_key,
        "keywords": keyword,
        "offset": page_size,
        "page": 1,
        "extensions": "all",
    }
    if city:
        params["city"] = city
    if types:
        params["types"] = types

    url = f"{base_url}/v3/place/text"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "1":
        logger.warning("Amap search error: %s", data)
        return []

    return data.get("pois", []) or []


@tool("search_poi", return_direct=False)
async def search_poi_tool(
    keyword: str,
    city: Optional[str] = None,
    category: Optional[str] = None,
    page_size: int = 10,
) -> List[Dict[str, Any]]:
    """
    搜索指定城市内的旅游相关 POI（景点 / 商场 / 餐厅等）。

    参数：
    - keyword: 关键字，例如 "博物馆"、"本帮菜"；
    - city: 城市名称或 adcode，例如 "上海"；
    - category: 高德 POI 类型代码，可选；
    - page_size: 返回条数（默认 10）。
    """
    cfg = load_settings(default_config_path())
    pois = await _amap_place_text_search(
        keyword=keyword,
        api_key=cfg.map.api_key,
        base_url=cfg.map.base_url,
        city=city,
        types=category,
        page_size=page_size,
    )
    results: List[Dict[str, Any]] = []
    for poi in pois:
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

        results.append({
            "name": poi.get("name"),
            "address": address,
            "cityname": poi.get("cityname"),
            "type": poi.get("type"),
            "location": location_str,
            "longitude": lng,
            "latitude": lat,
            "tel": tel,
            "rating": poi.get("rating", ""),
            "cost": poi.get("cost", ""),
            "photos": photo_urls,
            "id": poi.get("id"),
        })
    return results
