from __future__ import annotations

from typing import Dict, Any, Optional, List

import httpx
from langchain_core.tools import tool

from travel_agent.config import load_settings, default_config_path
from travel_agent.utils.logging import logger


async def _amap_geocode(city: str, api_key: str, base_url: str) -> Optional[str]:
    """根据城市名称获取 adcode。"""
    url = f"{base_url}/v3/geocode/geo"
    params = {
        "key": api_key,
        "address": city,
        "output": "json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") != "1" or not data.get("geocodes"):
        logger.warning("Amap geocode failed for city %s: %s", city, data)
        return None
    return data["geocodes"][0].get("adcode") or None


async def _amap_weather_forecast(city: str) -> Dict[str, Any]:
    """
    查询城市未来几天天气。

    为了与 travel/config.toml 配置解耦，这里在每次调用时读取一次配置，
    使用 [weather] 段落中的 base_url 与 api_key。
    """
    cfg = load_settings(default_config_path())
    api_key = cfg.weather.api_key
    base_url = cfg.weather.base_url.rstrip("/")

    adcode = await _amap_geocode(city, api_key=api_key, base_url=base_url)
    if not adcode:
        return {"error": f"无法解析城市: {city}"}

    url = f"{base_url}/v3/weather/weatherInfo"
    params = {
        "key": api_key,
        "city": adcode,
        "extensions": "all",  # 预报天气
        "output": "json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "1":
        logger.warning("Amap weather error for %s: %s", city, data)
        return {"error": data.get("info", "天气接口返回错误")}

    forecasts: List[Dict[str, Any]] = data.get("forecasts") or []
    if not forecasts:
        return {"error": "未找到天气预报数据"}

    casts = forecasts[0].get("casts") or []
    days: List[Dict[str, Any]] = []
    for cast in casts:
        days.append(
            {
                "date": cast.get("date"),
                "week": cast.get("week"),
                "day_weather": cast.get("dayweather"),
                "night_weather": cast.get("nightweather"),
                "day_temp": cast.get("daytemp"),
                "night_temp": cast.get("nighttemp"),
                "wind_direction": cast.get("daywind"),
                "wind_power": cast.get("daypower"),
            }
        )

    return {
        "city": city,
        "adcode": adcode,
        "days": days,
    }


@tool("check_weather", return_direct=False)
async def check_weather_tool(city: str) -> Dict[str, Any]:
    """
    查询指定城市未来几天的天气预报（基于高德天气接口）。

    参数：
    - city: 城市名称，如 "北京"、"上海" 等。

    返回：
    - 若成功：{"city": ..., "adcode": ..., "days": [{...}, ...]}
    - 若失败：{"error": "..."}
    """
    return await _amap_weather_forecast(city)

