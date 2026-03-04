"""
travel/src/travel_agent/nodes/core_nodes/smart_plan_itinerary.py

智能行程规划工具：
  1. 按地理距离聚类，每天的景点尽量在同一区域（减少奔波）
  2. 控制每天景点数量（考虑休息节奏）
  3. 天气感知：雨天优先安排室内景点
  4. 明确接收"本次方案"的精确 POI 列表，不依赖模糊搜索结果

调用方式：
  agent 先用 search_poi / search_hotel / search_restaurant 搜集候选，
  然后**只把当前方案需要的 POI** 传入本工具，由本工具完成科学分组后
  再调用 render_itinerary 渲染到地图。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from travel_agent.utils.logging import logger


# ─────────────────────────────────────────────────────────────────────────────
# 地理工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """计算两个经纬度之间的球面距离（km）。"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _centroid(pois: List[Dict]) -> tuple[float, float]:
    """计算一组 POI 的地理中心。"""
    lngs = [p["longitude"] for p in pois]
    lats = [p["latitude"] for p in pois]
    return sum(lngs) / len(lngs), sum(lats) / len(lats)


def _greedy_nearest(pois: List[Dict]) -> List[Dict]:
    """
    贪心最近邻排序：从第一个点开始每次选最近未访问的点，
    减少当天游览路线的总里程。
    """
    if len(pois) <= 2:
        return pois
    remaining = list(pois)
    ordered = [remaining.pop(0)]
    while remaining:
        last = ordered[-1]
        nearest_idx = min(
            range(len(remaining)),
            key=lambda i: _haversine_km(
                last["longitude"], last["latitude"],
                remaining[i]["longitude"], remaining[i]["latitude"]
            )
        )
        ordered.append(remaining.pop(nearest_idx))
    return ordered


def _cluster_by_day(
    pois: List[Dict],
    days: int,
    max_per_day: int,
    max_day_radius_km: float,
) -> List[List[Dict]]:
    """
    将 POI 按地理位置分组到各天：
    1. 先用 K-means 风格迭代找各天的中心
    2. 控制每天 ≤ max_per_day 个，超出的挪到下一天
    3. 超出半径 max_day_radius_km 的景点拆到单独一天
    """
    if not pois:
        return [[] for _ in range(days)]

    n = len(pois)
    # 若总景点 ≤ days * max_per_day，直接按距离贪心分组
    # 初始化：按经度粗排后均分做初始中心
    sorted_pois = sorted(pois, key=lambda p: p["longitude"])
    chunk = max(1, n // days)
    groups: List[List[Dict]] = []
    for i in range(days):
        start = i * chunk
        end = start + chunk if i < days - 1 else n
        groups.append(sorted_pois[start:end])

    # K-means 迭代（最多 10 轮）
    for _ in range(10):
        centers = [_centroid(g) if g else (0.0, 0.0) for g in groups]
        new_groups: List[List[Dict]] = [[] for _ in range(days)]
        for poi in sorted_pois:
            dists = [
                _haversine_km(poi["longitude"], poi["latitude"], c[0], c[1])
                for c in centers
            ]
            best = dists.index(min(dists))
            new_groups[best].append(poi)
        if new_groups == groups:
            break
        groups = new_groups

    # 溢出控制：每天超过 max_per_day 的 POI 移到最空的一天
    for i in range(days):
        while len(groups[i]) > max_per_day:
            overflow = groups[i].pop()  # 移走最远的（末尾）
            # 找最空的天
            emptiest = min(range(days), key=lambda j: len(groups[j]))
            groups[emptiest].append(overflow)

    # 每天内部贪心排序，减少路线迂回
    for i in range(days):
        groups[i] = _greedy_nearest(groups[i])

    return groups


def _is_indoor(poi: Dict) -> bool:
    """简单判断 POI 是否为室内场所（用于雨天优先排序）。"""
    name = (poi.get("name") or "").lower()
    addr = (poi.get("address") or "").lower()
    indoor_keywords = (
        "博物馆", "美术馆", "艺术馆", "影院", "电影院", "商场", "购物",
        "mall", "museum", "gallery", "室内", "展览", "展馆", "科技馆",
        "水族馆", "planetarium", "图书馆",
    )
    return any(k in name or k in addr for k in indoor_keywords)


# ─────────────────────────────────────────────────────────────────────────────
# Tool 定义
# ─────────────────────────────────────────────────────────────────────────────

@tool("smart_plan_itinerary", return_direct=False)
def smart_plan_itinerary_tool(
    spots: List[Dict[str, Any]],
    hotels: List[Dict[str, Any]],
    restaurants: List[Dict[str, Any]],
    days: int,
    city: str = "",
    title: str = "",
    weather_summary: str = "",
    pace: str = "standard",
) -> Dict[str, Any]:
    """
    智能行程分组工具：把搜集到的景点/酒店/餐厅科学地分配到各天，
    生成结构化行程供 render_itinerary 直接使用。

    **重要：只传入当前这套方案需要的地点，不要把多套备选方案的地点混在一起。**

    参数：
    - spots: 本次行程要去的景点列表，每项必须含
        { name, longitude, latitude, type?, address?, rating?, cost?, photos?, note? }
    - hotels: 备选酒店列表（同格式），会按天分配
    - restaurants: 备选餐厅列表，会按天分配早/午/晚
    - days: 总天数（整数）
    - city: 城市名称
    - title: 行程标题（可留空）
    - weather_summary: 天气概况字符串，用于识别雨天并优先安排室内景点
        例如 "第1天晴，第2天中雨，第3天多云"
    - pace: 节奏模式
        "relaxed"  = 轻松型，每天最多 2 个景点
        "standard" = 标准型，每天最多 3 个景点（默认）
        "intensive"= 紧凑型，每天最多 4 个景点

    返回：包含 days 列表的结构化行程 dict，可直接作为 render_itinerary 的 days 参数。
    """
    days = max(1, int(days))

    # 节奏 → 每天最大景点数
    pace_map = {"relaxed": 2, "standard": 3, "intensive": 4}
    max_per_day = pace_map.get(pace, 3)

    # ── 过滤无坐标的 POI ──────────────────────────────────────────────────
    def _valid(p: Any) -> Optional[Dict]:
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
            "type":      str(p.get("type") or "poi"),
            "address":   str(p.get("address") or ""),
            "tel":       str(p.get("tel") or ""),
            "rating":    str(p.get("rating") or ""),
            "cost":      str(p.get("cost") or ""),
            "photos":    list(p.get("photos") or []),
            "cuisine":   str(p.get("cuisine") or ""),
            "note":      str(p.get("note") or ""),
        }

    def _dedup(lst: List[Dict]) -> List[Dict]:
        """按名称去重，保留首次出现的项（保持顺序）。"""
        seen: set[str] = set()
        out: List[Dict] = []
        for item in lst:
            key = item["name"].strip().lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    valid_spots = _dedup([v for p in spots if (v := _valid(p))])
    valid_hotels = _dedup([v for p in hotels if (v := _valid(p))])
    valid_restaurants = _dedup([v for p in restaurants if (v := _valid(p))])

    if not valid_spots:
        logger.warning("[smart_plan_itinerary] no valid spots provided")
        return {"days": [], "city": city, "title": title}

    # ── 雨天识别：找出哪些天下雨 ──────────────────────────────────────────
    rainy_days: set[int] = set()
    if weather_summary:
        rain_keywords = ("雨", "rain", "drizzle", "shower", "storm", "thunder")
        for i in range(1, days + 1):
            # 在 "第N天" 附近找雨字
            import re
            pattern = rf"第\s*{i}\s*天[^，。\n]{{0,10}}"
            match = re.search(pattern, weather_summary)
            if match and any(k in match.group() for k in rain_keywords):
                rainy_days.add(i)

    # ── 地理聚类分组 ──────────────────────────────────────────────────────
    grouped: List[List[Dict]] = _cluster_by_day(
        valid_spots, days, max_per_day, max_day_radius_km=15.0
    )

    # ── 雨天重排：把室内景点提前到雨天 ────────────────────────────────────
    if rainy_days:
        indoor_spots = [s for s in valid_spots if _is_indoor(s)]
        for rain_day_idx in [d - 1 for d in rainy_days if 0 < d <= days]:
            # 把当天的室外景点和雨天全局室内景点互换
            day_group = grouped[rain_day_idx]
            outdoor = [s for s in day_group if not _is_indoor(s)]
            indoor_here = [s for s in day_group if _is_indoor(s)]
            # 从其他天借调室内景点
            for other_idx, other_group in enumerate(grouped):
                if other_idx == rain_day_idx:
                    continue
                for s in list(other_group):
                    if _is_indoor(s) and len(indoor_here) < max_per_day:
                        other_group.remove(s)
                        indoor_here.append(s)
                        # 把借出去的坑用一个 outdoor 回填
                        if outdoor:
                            other_group.append(outdoor.pop(0))
                        break
            grouped[rain_day_idx] = _greedy_nearest(indoor_here + outdoor[:max(0, max_per_day - len(indoor_here))])

    # ── 按天分配酒店（循环取，保证每天都有） ─────────────────────────────
    def _hotel_for_day(idx: int) -> Optional[Dict]:
        if not valid_hotels:
            return None
        return valid_hotels[idx % len(valid_hotels)]

    # ── 按天分配餐厅（每天 1~2 家） ───────────────────────────────────────
    meals_per_day = max(1, len(valid_restaurants) // days) if valid_restaurants else 0

    def _meals_for_day(idx: int) -> List[Dict]:
        if not valid_restaurants:
            return []
        start = idx * meals_per_day
        end = start + meals_per_day if idx < days - 1 else len(valid_restaurants)
        return valid_restaurants[start:end]

    # ── 组装最终结构 ──────────────────────────────────────────────────────
    # 全局景点去重：确保同一景点不会跨天出现两次
    _used_spot_names: set[str] = set()

    result_days: List[Dict] = []
    for day_idx in range(days):
        day_spots_raw = grouped[day_idx] if day_idx < len(grouped) else []
        # 跨天去重：过滤掉已被其他天使用的景点
        day_spots = []
        for s in day_spots_raw:
            skey = s["name"].strip().lower()
            if skey not in _used_spot_names:
                _used_spot_names.add(skey)
                day_spots.append(s)

        if not day_spots and day_idx >= len(grouped):
            continue

        # 计算当天景点间的最大距离，用于 note 提示
        max_dist = 0.0
        for i in range(len(day_spots) - 1):
            d = _haversine_km(
                day_spots[i]["longitude"], day_spots[i]["latitude"],
                day_spots[i+1]["longitude"], day_spots[i+1]["latitude"]
            )
            max_dist = max(max_dist, d)

        rain_note = "☔ 今日有雨，建议携带雨具" if (day_idx + 1) in rainy_days else ""

        result_days.append({
            "day":   day_idx + 1,
            "label": f"第{day_idx + 1}天",
            "spots": day_spots,
            "hotel": _hotel_for_day(day_idx),
            "meals": _meals_for_day(day_idx),
            "meta": {
                "spot_count":    len(day_spots),
                "max_dist_km":   round(max_dist, 1),
                "is_rainy":      (day_idx + 1) in rainy_days,
                "rain_note":     rain_note,
                "pace":          pace,
            },
        })

    total_spots = sum(len(d["spots"]) for d in result_days)
    logger.info(
        "[smart_plan_itinerary] city=%s days=%d total_spots=%d pace=%s rainy_days=%s",
        city, days, total_spots, pace, rainy_days,
    )

    return {
        "city":  city,
        "title": title or f"{city} {days}日行程",
        "days":  result_days,
    }
