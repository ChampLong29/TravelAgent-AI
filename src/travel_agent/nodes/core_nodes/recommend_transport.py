from __future__ import annotations

from typing import Dict, Any

from langchain_core.tools import tool


@tool("recommend_transport", return_direct=False)
def recommend_transport_tool(
    *,
    distance_km: float,
    city: str,
) -> Dict[str, Any]:
    """
    根据城市和距离给出一个非常粗略的交通建议，供 LLM 进一步润色说明。
    """
    mode = "walk"
    if distance_km > 1.5:
        mode = "bike_or_bus"
    if distance_km > 5:
        mode = "metro_or_taxi"
    if distance_km > 30:
        mode = "intercity_train_or_flight"

    return {
        "city": city,
        "distance_km": distance_km,
        "suggested_mode": mode,
    }

