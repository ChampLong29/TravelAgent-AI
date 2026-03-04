"""
travel/src/travel_agent/nodes/core_nodes/render_itinerary.py

将行程规划结果打包为前端可渲染的有序景点数据。
前端收到后会在地图上：
  1. 按日期分组，每日用不同颜色的编号标记（①②③…）
  2. 每日景点之间用直线连线，展示游览顺序
  3. 右侧展示卡片列表，酒店/餐厅/景点分区显示
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from travel_agent.utils.logging import logger


@tool("render_itinerary", return_direct=False)
def render_itinerary_tool(
    days: List[Dict[str, Any]],
    city: str = "",
    title: str = "",
) -> str:
    """
    将完整行程规划打包为地图可渲染的有序景点数据。

    **请在生成行程报告之后调用此工具**，把每天的景点、酒店、餐厅坐标传入，
    前端会自动在地图上按顺序标注编号并绘制游览路线连线。

    参数：
    - days: 每天的安排，每项格式：
        {
          "day": 1,           // 第几天（整数）
          "label": "第一天",  // 日期标签
          "spots": [          // 当天景点列表，按游览顺序排列
            {
              "name": "宽窄巷子",
              "longitude": 104.0553,
              "latitude": 30.6625,
              "type": "poi",          // poi/hotel/restaurant
              "address": "青羊区",
              "tel": "",
              "rating": "4.8",
              "cost": "",
              "photos": [],
              "note": "上午游览，约2小时"  // 可选备注
            }
          ],
          "hotel": {          // 当晚住宿（可选）
            "name": "成都香格里拉",
            "longitude": 104.07,
            "latitude": 30.66,
            "address": "...",
            "rating": "4.9",
            "cost": "800"
          },
          "meals": [          // 当天餐厅推荐（可选）
            {"name": "陈麻婆豆腐", "longitude": ..., "latitude": ...,
             "cuisine": "川菜", "rating": "4.5", "cost": "50"}
          ]
        }
    - city: 城市名称
    - title: 行程标题（可选）

    返回：前端 JSON 数据块字符串（内部使用）。
    """
    validated_days: List[Dict[str, Any]] = []

    for d in days:
        if not isinstance(d, dict):
            continue
        day_num = int(d.get("day") or len(validated_days) + 1)
        label = str(d.get("label") or f"第{day_num}天")

        spots: List[Dict[str, Any]] = []
        for s in (d.get("spots") or []):
            if not isinstance(s, dict):
                continue
            try:
                lng = float(s.get("longitude") or 0)
                lat = float(s.get("latitude") or 0)
            except (TypeError, ValueError):
                continue
            if not lng or not lat:
                continue
            spots.append({
                "name":      str(s.get("name") or ""),
                "longitude": lng,
                "latitude":  lat,
                "type":      str(s.get("type") or "poi"),
                "address":   str(s.get("address") or ""),
                "tel":       str(s.get("tel") or ""),
                "rating":    str(s.get("rating") or ""),
                "cost":      str(s.get("cost") or ""),
                "photos":    list(s.get("photos") or []),
                "note":      str(s.get("note") or ""),
            })

        def _parse_poi(p: Any, default_type: str = "poi") -> Optional[Dict]:
            if not isinstance(p, dict):
                return None
            try:
                lng = float(p.get("longitude") or 0)
                lat = float(p.get("latitude") or 0)
            except (TypeError, ValueError):
                return None
            if not lng or not lat:
                return None
            return {
                "name":      str(p.get("name") or ""),
                "longitude": lng,
                "latitude":  lat,
                "type":      str(p.get("type") or default_type),
                "address":   str(p.get("address") or ""),
                "tel":       str(p.get("tel") or ""),
                "rating":    str(p.get("rating") or ""),
                "cost":      str(p.get("cost") or ""),
                "photos":    list(p.get("photos") or []),
                "cuisine":   str(p.get("cuisine") or ""),
                "note":      str(p.get("note") or ""),
            }

        hotel = _parse_poi(d.get("hotel"), "hotel")
        meals = [_parse_poi(m, "restaurant") for m in (d.get("meals") or [])]
        meals = [m for m in meals if m]

        validated_days.append({
            "day":   day_num,
            "label": label,
            "spots": spots,
            "hotel": hotel,
            "meals": meals,
        })

    if not validated_days:
        logger.warning("[render_itinerary] no valid days")
        return json.dumps({"__type": "itinerary", "days": []}, ensure_ascii=False)

    logger.info("[render_itinerary] %d days, city=%s", len(validated_days), city)
    return json.dumps({
        "__type": "itinerary",
        "city":   city,
        "title":  title,
        "days":   validated_days,
    }, ensure_ascii=False)
