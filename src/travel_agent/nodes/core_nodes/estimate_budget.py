from __future__ import annotations

from typing import Dict, Any

from langchain_core.tools import tool


@tool("estimate_budget", return_direct=False)
def estimate_budget_tool(
    *,
    days: int,
    city_level: str = "A",
    hotel_level: str = "mid",
    with_flight: bool = True,
) -> Dict[str, Any]:
    """
    粗略估算旅行预算，主要用于给 LLM 一个结构化基线，然后由 LLM 解释细节。
    """
    days = max(1, days)
    city_factor = {"A": 1.0, "B": 0.8, "C": 0.6}.get(city_level, 1.0)
    hotel_factor = {"budget": 0.6, "mid": 1.0, "luxury": 1.8}.get(hotel_level, 1.0)

    base_daily = 600  # 人民币，含餐饮 + 交通 + 门票
    hotel_daily = 400

    daily_cost = (base_daily + hotel_daily * hotel_factor) * city_factor
    flight_round_trip = 1500 if with_flight else 0

    total = daily_cost * days + flight_round_trip

    return {
        "days": days,
        "city_level": city_level,
        "hotel_level": hotel_level,
        "with_flight": with_flight,
        "daily_cost_estimate": round(daily_cost, 2),
        "total_estimate": round(total, 2),
        "currency": "CNY",
    }

