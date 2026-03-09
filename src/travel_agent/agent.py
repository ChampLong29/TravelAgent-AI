from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from langgraph.prebuilt import create_react_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
import json as _json
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from travel_agent.config import Settings
from travel_agent.storage.memory_compressor import MemoryCompressor
from travel_agent.storage.user_profile import UserProfileStore


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
from travel_agent.utils.prompts import get_system_prompt
from travel_agent.utils.logging import logger
from travel_agent.skills.skills_io import load_skills

@dataclass
class ClientContext:
    cfg: Settings
    session_id: str
    node_manager: NodeManager
    lang: str = "zh"
    mcp_client: Any = field(default=None)          # MultiServerMCPClient，供外部关闭
    memory_compressor: Any = field(default=None)   # L1: MemoryCompressor
    user_profile: Any = field(default=None)        # L3: UserProfileStore
    _base_system_prompt: str = field(default="", repr=False)

    def build_dynamic_system_prompt(
        self,
        store=None,          # ArtifactStore | None，用于 L2 context snapshot
    ) -> str:
        """
        动态拼装 system prompt，融合三层记忆：

        ┌─────────────────────────────────────────┐
        │ 原始 system prompt（指令 + 工具说明）      │
        ├─────────────────────────────────────────┤
        │ L3：用户偏好 + 历史 session 摘要          │
        ├─────────────────────────────────────────┤
        │ L2：本 session 已收集工具结果（snapshot）  │
        └─────────────────────────────────────────┘
        """
        parts: list[str] = [self._base_system_prompt]

        # L3：用户偏好画像
        if self.user_profile is not None:
            profile_text = self.user_profile.build_profile_prompt(lang=self.lang)
            if profile_text:
                parts.append("\n\n" + profile_text)

        # L2：本 session 工具结果快照
        if store is not None:
            snapshot_text = store.build_context_prompt(lang=self.lang)
            if snapshot_text:
                parts.append("\n\n" + snapshot_text)

        return "".join(parts)


def _build_llm(cfg: Settings) -> BaseChatModel:
    # DeepSeek API 不接受 list 类型的 content，需要用子类拍平；
    # 其他兼容 OpenAI 格式的服务（智谱、通义等）直接用标准 ChatOpenAI。
    cls = DeepSeekChatOpenAI if "deepseek" in cfg.llm.base_url.lower() else ChatOpenAI
    return cls(
        model=cfg.llm.model,
        base_url=cfg.llm.base_url,
        api_key=cfg.llm.api_key,
        timeout=cfg.llm.timeout,
    )


def _collect_tools(cfg: Settings) -> List[BaseTool]:
    """
    已废弃：工具现在统一从 MCP Server 获取。
    保留此函数仅供 fallback / 测试使用。
    """
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
    return [
        search_poi_tool, plan_itinerary_tool, estimate_budget_tool,
        recommend_transport_tool, check_weather_tool, validate_json_tool, fix_json_tool,
        search_hotel_tool, search_restaurant_tool, plan_route_tool, format_itinerary_tool,
        render_map_pois_tool, render_map_route_tool, render_itinerary_tool,
        smart_plan_itinerary_tool,
    ]


async def build_agent(cfg: Settings, session_id: str, *, lang: str = "zh"):
    """
    构建旅行助手 Agent：
    - 通过 MultiServerMCPClient 连接本地 MCP Server，获取所有工具
    - 动态从 .storyline/skills 目录加载 skills
    - 使用 LangGraph create_react_agent 构建具备函数调用能力的对话 Agent
    - 初始化三层记忆组件（L1 MemoryCompressor / L3 UserProfileStore）
    """
    from pathlib import Path

    llm = _build_llm(cfg)

    # ── 连接 MCP Server，获取工具 ──────────────────────────────────────
    mcp_url = (
        f"{cfg.mcp_server.url_scheme}://{cfg.mcp_server.connect_host}"
        f":{cfg.mcp_server.port}{cfg.mcp_server.path}"
    )
    client = MultiServerMCPClient(
        connections={
            cfg.mcp_server.server_name: {
                "transport": "streamable_http",
                "url": mcp_url,
                "timeout": timedelta(seconds=cfg.mcp_server.timeout),
                "headers": {"X-Travel-Session-Id": session_id},
            }
        }
    )
    tools: List[BaseTool] = await client.get_tools()
    logger.info("[Agent] fetched %d tools from MCP Server at %s", len(tools), mcp_url)

    # ── 加载 Markdown Skills ───────────────────────────────────────────
    _travel_root = Path(__file__).resolve().parent.parent.parent  # travel/
    skill_dir = str(_travel_root / ".storyline" / "skills")
    try:
        skills_tools = await load_skills(skill_dir=skill_dir)
        tools = tools + skills_tools
        logger.info("[Agent] loaded %d skills from %s", len(skills_tools), skill_dir)
    except Exception as exc:
        logger.warning("[Agent] Skills load failed (non-fatal): %s", exc)

    system_prompt = get_system_prompt(lang=lang)
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
    )

    # ── 三层记忆：L1 MemoryCompressor ────────────────────────────────
    _outputs_root = Path(cfg.project.outputs_dir)
    session_dir = _outputs_root / session_id
    compressor = MemoryCompressor(
        llm=llm,
        session_dir=session_dir,
        lang=lang,
    )

    # ── 三层记忆：L3 UserProfileStore ────────────────────────────────
    user_profile = UserProfileStore(
        data_dir=cfg.project.data_dir,
        user_id="default",
    )

    node_manager = NodeManager(tools=tools)
    context = ClientContext(
        cfg=cfg,
        session_id=session_id,
        node_manager=node_manager,
        lang=lang,
        mcp_client=client,
        memory_compressor=compressor,
        user_profile=user_profile,
        _base_system_prompt=system_prompt,
    )

    logger.info("[Agent] built for session %s with %d tools (via MCP)", session_id, len(tools))
    return agent, context

