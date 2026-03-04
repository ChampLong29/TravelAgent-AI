from __future__ import annotations

from typing import List, Dict, Any

from langchain_core.tools import tool


@tool("plan_itinerary", return_direct=False)
def plan_itinerary_tool(
    *,
    city: str,
    days: int,
    pois: List[Dict[str, Any]],
    preference: str = "",
) -> Dict[str, Any]:
    """
    基于 POI 列表生成一个结构化的多日行程草案。

    这里不直接调用 LLM，而是作为一个“结构容器”，真正的自然语言排版由 LLM 完成。
    Agent 可以多次调用该工具来调整方案。
    """
    days = max(1, days)
    # 简单均分 POI 到每天，实际项目中可以按地理位置 / 热度聚类
    per_day = max(1, len(pois) // days or 1)
    schedule: List[Dict[str, Any]] = []
    idx = 0
    for d in range(1, days + 1):
        day_pois = pois[idx : idx + per_day]
        idx += per_day
        schedule.append(
            {
                "day": d,
                "city": city,
                "theme": preference or "综合游览",
                "pois": day_pois,
            }
        )

    return {
        "city": city,
        "days": days,
        "preference": preference,
        "schedule": schedule,
    }

