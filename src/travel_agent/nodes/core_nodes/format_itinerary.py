"""
travel/src/travel_agent/nodes/core_nodes/format_itinerary.py

Format collected travel data into a structured Markdown itinerary report.
Calls the LLM with the format_itinerary prompt template.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from langchain_core.tools import tool

from travel_agent.config import load_settings, default_config_path
from travel_agent.utils.prompts import build_prompts
from travel_agent.utils.logging import logger


async def _call_llm(system_prompt: str, user_prompt: str, cfg) -> str:
    """Call the configured LLM and return the text response."""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatOpenAI(
        model=cfg.llm.model,
        base_url=cfg.llm.base_url,
        api_key=cfg.llm.api_key,
        timeout=cfg.llm.timeout,
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    response = await llm.ainvoke(messages)
    return response.content if hasattr(response, "content") else str(response)


@tool("format_itinerary", return_direct=False)
async def format_itinerary_tool(
    city: str,
    days: int,
    travelers: int = 2,
    budget: str = "适中",
    raw_data: str = "",
) -> Dict[str, Any]:
    """
    将已收集的旅行数据（景点、酒店、餐厅、天气、路线等）整理成
    结构化的 Markdown 格式行程报告。

    参数：
    - city: 目标城市名称；
    - days: 行程天数；
    - travelers: 出行人数（默认 2 人）；
    - budget: 预算描述，如 "500元/天" 或 "适中"；
    - raw_data: 之前各工具返回的数据汇总（JSON 字符串或文本描述）。

    返回：
    - markdown: 完整的 Markdown 行程报告文本
    - city / days / travelers / budget: 原始参数回传
    """
    cfg = load_settings(default_config_path())

    try:
        prompts = build_prompts(
            "format_itinerary",
            lang="zh",
            city=city,
            days=str(days),
            travelers=str(travelers),
            budget=budget,
            raw_data=raw_data or "（未提供详细数据，请根据城市常识生成示例行程）",
        )
    except FileNotFoundError as exc:
        logger.warning("[format_itinerary] prompt template missing: %s", exc)
        prompts = {
            "system": "你是一位专业旅行文案编辑，请将以下数据整理成美观的 Markdown 行程报告。",
            "user": f"城市: {city}，天数: {days}天，人数: {travelers}人，预算: {budget}\n\n数据:\n{raw_data}",
        }

    try:
        markdown = await _call_llm(prompts["system"], prompts.get("user", ""), cfg)
    except Exception as exc:
        logger.error("[format_itinerary] LLM call failed: %s", exc)
        markdown = f"# {city} {days} 日行程\n\n> 行程生成失败，请稍后重试。\n\n错误信息: {exc}"

    return {
        "markdown": markdown,
        "city": city,
        "days": days,
        "travelers": travelers,
        "budget": budget,
    }
