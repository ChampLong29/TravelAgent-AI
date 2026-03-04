from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from langgraph.prebuilt import create_react_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
import json as _json
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, HumanMessage

from travel_agent.config import Settings


def _flatten_content(content) -> str:
    """把 list/dict 类型的 message content 拍平为字符串，DeepSeek 只接受 string。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text") or _json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return _json.dumps(content, ensure_ascii=False)


class DeepSeekChatOpenAI(ChatOpenAI):
    """
    ChatOpenAI 的子类，在发送请求前将所有消息的 content 强制转为 string，
    解决 DeepSeek API 不接受 list 类型 content 的问题。
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        fixed = []
        for msg in payload.get("messages", []):
            content = msg.get("content")
            if content is not None and not isinstance(content, str):
                msg = dict(msg)
                msg["content"] = _flatten_content(content)
            fixed.append(msg)
        payload["messages"] = fixed
        return payload


from travel_agent.nodes.node_manager import NodeManager
from travel_agent.nodes.core_nodes.search_poi import search_poi_tool
from travel_agent.nodes.core_nodes.plan_itinerary import plan_itinerary_tool
from travel_agent.nodes.core_nodes.estimate_budget import estimate_budget_tool
from travel_agent.nodes.core_nodes.recommend_transport import recommend_transport_tool
from travel_agent.nodes.core_nodes.check_weather import check_weather_tool
from travel_agent.nodes.core_nodes.json_tools import validate_json_tool, fix_json_tool
from travel_agent.nodes.core_nodes.search_hotel import search_hotel_tool
from travel_agent.nodes.core_nodes.search_restaurant import search_restaurant_tool
from travel_agent.nodes.core_nodes.plan_route import plan_route_tool
from travel_agent.nodes.core_nodes.format_itinerary import format_itinerary_tool
from travel_agent.nodes.core_nodes.render_map import render_map_pois_tool, render_map_route_tool
from travel_agent.nodes.core_nodes.render_itinerary import render_itinerary_tool
from travel_agent.nodes.core_nodes.smart_plan_itinerary import smart_plan_itinerary_tool
from travel_agent.utils.prompts import get_system_prompt
from travel_agent.utils.logging import logger
from travel_agent.skills.skills_io import load_skills

@dataclass
class ClientContext:
    cfg: Settings
    session_id: str
    node_manager: NodeManager
    lang: str = "zh"


def _build_llm(cfg: Settings) -> BaseChatModel:
    return DeepSeekChatOpenAI(
        model=cfg.llm.model,
        base_url=cfg.llm.base_url,
        api_key=cfg.llm.api_key,
        timeout=cfg.llm.timeout,
    )


def _collect_tools(cfg: Settings) -> List[BaseTool]:
    """
    在这里集中管理所有工具，后续你可以很方便地增加新的节点。
    """
    tools: List[BaseTool] = [
        search_poi_tool,
        plan_itinerary_tool,
        estimate_budget_tool,
        recommend_transport_tool,
        check_weather_tool,
        validate_json_tool,
        fix_json_tool,
        # ── 新增工具 ────────────────────────────────────
        search_hotel_tool,
        search_restaurant_tool,
        plan_route_tool,
        format_itinerary_tool,
        # ── 地图渲染工具 ───────────────────────────────
        render_map_pois_tool,
        render_map_route_tool,
        render_itinerary_tool,
        # ── 智能行程规划 ───────────────────────────────
        smart_plan_itinerary_tool,
    ]
    return tools


async def build_agent(cfg: Settings, session_id: str, *, lang: str = "zh"):
    """
    构建旅行助手 Agent：
    - 初始化 LLM
    - 注册所有工具节点
    - 动态从 .storyline/skills 目录加载 skills
    - 使用 LangChain 的 create_tool_calling_agent 构建一个具备函数调用能力的对话 Agent
    """
    llm = _build_llm(cfg)
    tools = _collect_tools(cfg)

    # Load MD skills — resolve .storyline/skills relative to this file (travel/src/travel_agent/)
    import os
    from pathlib import Path
    _this_dir = Path(__file__).resolve().parent  # travel/src/travel_agent
    _travel_root = _this_dir.parent.parent       # travel/
    skill_dir = str(_travel_root / '.storyline' / 'skills')

    try:
        skills_tools = await load_skills(skill_dir=skill_dir)
        tools.extend(skills_tools)
        logger.info("Loaded %d skills from %s", len(skills_tools), skill_dir)
    except Exception as exc:
        logger.warning("Skills load failed (non-fatal): %s", exc)

    system_prompt = get_system_prompt(lang=lang)
    # create_react_agent wraps LLM + tools in a LangGraph ReAct loop
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
    )

    node_manager = NodeManager(tools=tools)
    context = ClientContext(cfg=cfg, session_id=session_id, node_manager=node_manager, lang=lang)

    logger.info("Travel agent built for session %s with %d tools", session_id, len(tools))
    return agent, context

