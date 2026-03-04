from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import json
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from travel_agent.agent import build_agent  # noqa: E402
from travel_agent.config import load_settings  # noqa: E402
from travel_agent.utils.logging import logger  # noqa: E402

# 永远使用本文件所在目录（travel/）下的 config.toml，与启动目录无关
CONFIG_PATH = os.path.join(ROOT_DIR, "config.toml")


def _normalize_content(content) -> str:
    """将 list/dict 类型的 message content 序列化为字符串（DeepSeek 只接受 string）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text") or json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return json.dumps(content, ensure_ascii=False)


def _clean_messages_for_next_turn(messages: list) -> list:
    """
    保留完整消息历史（Human / AI / Tool），仅将 content 中的 list/dict
    序列化为字符串，避免 DeepSeek 400 错误，同时不破坏上下文记忆。
    """
    from langchain_core.messages import AIMessage as _AI, ToolMessage as _Tool, HumanMessage as _Human

    cleaned = []
    for m in messages:
        content = _normalize_content(getattr(m, "content", "") or "")
        if isinstance(m, _Human):
            cleaned.append(_Human(content=content))
        elif isinstance(m, _AI):
            # 保留 tool_calls 字段，只修复 content 类型
            extra = {}
            if getattr(m, "tool_calls", None):
                extra["tool_calls"] = m.tool_calls
            if getattr(m, "additional_kwargs", None):
                extra["additional_kwargs"] = m.additional_kwargs
            cleaned.append(_AI(content=content, **extra))
        elif isinstance(m, _Tool):
            cleaned.append(_Tool(content=content, tool_call_id=m.tool_call_id))
        else:
            cleaned.append(m)
    return cleaned


WEB_DIR = os.path.join(ROOT_DIR, "web")
STATIC_DIR = os.path.join(WEB_DIR, "static")
INDEX_HTML = os.path.join(WEB_DIR, "index.html")

# 超时配置（秒）
AGENT_TIMEOUT = 120
MAX_RETRIES = 2


def _extract_weather_block(messages: list) -> Optional[str]:
    """从 ToolMessage 中提取天气数据，返回前端可解析的 JSON 块字符串。"""
    for m in reversed(messages):
        if not isinstance(m, ToolMessage):
            continue
        raw = getattr(m, "content", "") or ""
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        # check_weather 返回格式: {city, adcode, days: [...]}
        if isinstance(payload, dict) and "days" in payload and "city" in payload:
            block = {
                "__type": "weather",
                "city": payload.get("city", ""),
                "days": payload.get("days", []),
            }
            return "\n```json\n" + json.dumps(block, ensure_ascii=False) + "\n```"
    return None


def _amap_type_to_marker_type(amap_type: str) -> str:
    """把高德原始 POI 类型字符串映射为前端 marker type。"""
    if not amap_type:
        return "poi"
    t = amap_type.lower()
    if any(k in t for k in ("住宿", "酒店", "宾馆", "旅馆", "民宿", "hostel", "hotel")):
        return "hotel"
    if any(k in t for k in ("餐饮", "美食", "饭店", "餐厅", "小吃", "food", "restaurant")):
        return "restaurant"
    return "poi"


# 工具名 → marker type 映射（用于酒店/餐厅工具识别）
_TOOL_TYPE_MAP: dict[str, str] = {
    "search_hotel":      "hotel",
    "search_restaurant": "restaurant",
    "search_poi":        "poi",
}


def _extract_map_blocks(messages: list) -> str:
    """
    自动扫描本轮所有 ToolMessage，从工具输出中提取地图数据，
    生成前端可解析的 ```json 块。

    行程显示策略：
    - 优先使用 smart_plan_itinerary / render_itinerary 的结构化输出
    - 若两者均未调用（简单搜索场景），才把 search_* 结果展示为候选 pois
    - 绝不把多套备选方案的搜索结果合并成一个行程（防止"三天/四天/五天"混用）
    """
    # 建立 tool_call_id → tool_name 索引
    call_id_to_name: dict[str, str] = {}
    for m in messages:
        if not isinstance(m, AIMessage):
            continue
        for tc in getattr(m, "tool_calls", []) or []:
            cid = tc.get("id") or ""
            name = tc.get("name") or ""
            if cid and name:
                call_id_to_name[cid] = name

    blocks: list[str] = []
    has_itinerary_block: bool = False   # 是否已有结构化行程块
    itinerary_days: int = 0             # format_itinerary 记录的天数（0=未调用）
    itinerary_city: str = ""

    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        raw = getattr(m, "content", "") or ""
        if not raw:
            continue

        tool_name = call_id_to_name.get(getattr(m, "tool_call_id", "") or "", "")

        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue

        # ── 已有 __type 标记的工具输出（render_map_pois/route/itinerary） ──
        if isinstance(payload, dict) and payload.get("__type") in ("pois", "route", "itinerary"):
            blocks.append("\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```")
            if payload.get("__type") == "itinerary":
                has_itinerary_block = True
            continue

        # ── smart_plan_itinerary → 生成 itinerary 块 ─────────────────────
        if tool_name == "smart_plan_itinerary" and isinstance(payload, dict):
            days_data = payload.get("days")
            if days_data:
                itinerary_block = {
                    "__type": "itinerary",
                    "city":   payload.get("city", ""),
                    "title":  payload.get("title", ""),
                    "days":   days_data,
                }
                blocks.append("\n```json\n" + json.dumps(itinerary_block, ensure_ascii=False) + "\n```")
                has_itinerary_block = True
            continue

        # ── search_poi / search_hotel / search_restaurant → pois 块 ────────
        if tool_name in _TOOL_TYPE_MAP and isinstance(payload, list) and payload:
            default_type = _TOOL_TYPE_MAP[tool_name]
            items: list[dict] = []
            for item in payload[:5]:
                if not isinstance(item, dict):
                    continue
                try:
                    lng = float(item.get("longitude") or 0)
                    lat = float(item.get("latitude") or 0)
                except (TypeError, ValueError):
                    continue
                if not lng or not lat:
                    continue
                marker_type = _amap_type_to_marker_type(str(item.get("type") or ""))
                if marker_type == "poi" and default_type != "poi":
                    marker_type = default_type
                raw_photos = item.get("photos") or []
                if isinstance(raw_photos, dict):
                    raw_photos = raw_photos.get("photo") or []
                photos: list[str] = []
                for ph in raw_photos[:3]:
                    url = ph.get("url") if isinstance(ph, dict) else str(ph)
                    if url and url.startswith("http"):
                        photos.append(url)
                items.append({
                    "name":      str(item.get("name") or "地点"),
                    "longitude": lng,
                    "latitude":  lat,
                    "type":      marker_type,
                    "address":   str(item.get("address") or ""),
                    "tel":       str(item.get("tel") or ""),
                    "rating":    str(item.get("rating") or ""),
                    "cost":      str(item.get("cost") or ""),
                    "cuisine":   str(item.get("cuisine") or ""),
                    "photos":    photos,
                })
            if items:
                blocks.append("\n```json\n" + json.dumps(
                    {"__type": "pois", "items": items}, ensure_ascii=False
                ) + "\n```")
            continue

        # ── plan_route → route 块 ──────────────────────────────────────────
        if tool_name == "plan_route" and isinstance(payload, dict):
            polyline = payload.get("polyline")
            if polyline and len(polyline) >= 2:
                blocks.append("\n```json\n" + json.dumps({
                    "__type":       "route",
                    "polyline":     polyline,
                    "origin":       payload.get("origin", ""),
                    "destination":  payload.get("destination", ""),
                    "distance_km":  payload.get("distance_km"),
                    "duration_min": payload.get("duration_min"),
                }, ensure_ascii=False) + "\n```")
            continue

        # ── format_itinerary → 仅记录天数/城市 ───────────────────────────
        if tool_name == "format_itinerary" and isinstance(payload, dict):
            itinerary_days = int(payload.get("days") or 0)
            itinerary_city = str(payload.get("city") or "")
            continue

    return "".join(blocks)


app = FastAPI(title="Travel Smart Assistant")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/apple-touch-icon.png", include_in_schema=False)
async def apple_touch_icon() -> Response:
    return Response(status_code=204)


@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
async def apple_touch_icon_precomposed() -> Response:
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return Path(INDEX_HTML).read_text(encoding="utf-8")


@app.websocket("/ws/chat")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    session_id = f"travel_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    cfg = load_settings(CONFIG_PATH)
    try:
        agent, context = await build_agent(cfg=cfg, session_id=session_id, lang="zh")
    except Exception as exc:
        logger.exception("build_agent 失败: %s", exc)
        await ws.send_text(f"后端初始化失败：{exc}")
        await ws.close()
        return

    messages = []

    try:
        while True:
            data = await ws.receive_text()
            if not data:
                continue
            if data.strip() in ("/exit", "/quit"):
                await ws.close()
                break

            messages.append(HumanMessage(content=data))

            # ── 超时 + 重试 ────────────────────────────────────────────────────
            result: Optional[Dict[str, Any]] = None
            last_exc: Optional[Exception] = None

            for attempt in range(1, MAX_RETRIES + 2):  # 最多尝试 MAX_RETRIES+1 次
                try:
                    result = await asyncio.wait_for(
                        agent.ainvoke({"messages": messages}),
                        timeout=AGENT_TIMEOUT,
                    )
                    last_exc = None
                    break
                except asyncio.TimeoutError:
                    last_exc = asyncio.TimeoutError(
                        f"请求超时（>{AGENT_TIMEOUT}s）"
                    )
                    logger.warning(
                        "[session=%s] Agent 超时，第 %d 次尝试", session_id, attempt
                    )
                    if attempt <= MAX_RETRIES:
                        await ws.send_text(
                            f"❗ 请求超时，正在进行第 {attempt} 次重试…"
                        )
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.exception(
                        "[session=%s] Agent 调用失败（第 %d 次）: %s",
                        session_id,
                        attempt,
                        exc,
                    )
                    if attempt <= MAX_RETRIES:
                        await ws.send_text(
                            f"❗ 发生错误，正在进行第 {attempt} 次重试…"
                        )

            if result is None:
                err_msg = str(last_exc) if last_exc else "未知错误"
                await ws.send_text(
                    f"❌ 抱歉，尝试 {MAX_RETRIES + 1} 次后仍无法完成请求。\n原因：{err_msg}"
                )
                # 移除未得到回复的 Human 消息，避免下轮展开历史混乱
                messages = messages[:-1]
                continue

            # ── 提取最终回复文本 ──────────────────────────────────────────────
            raw_messages = result["messages"]
            final_text = None
            for m in reversed(raw_messages):
                if isinstance(m, HumanMessage):
                    break
                content = getattr(m, "content", None)
                if content and not isinstance(m, ToolMessage):
                    final_text = _normalize_content(content)
                    if final_text:
                        break

            # ── 追加地图 / 天气 JSON 块 ───────────────────────────────────────
            map_blocks   = _extract_map_blocks(raw_messages)
            weather_block = _extract_weather_block(raw_messages)

            # 清理消息历史，避免 DeepSeek 400 错误
            messages = _clean_messages_for_next_turn(raw_messages)

            reply = final_text or "(没有生成回复)"
            if map_blocks:
                reply = reply + "\n" + map_blocks
            if weather_block:
                reply = reply + "\n" + weather_block

            await ws.send_text(reply)
    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开：%s", session_id)


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), city: str = Form("")):
    """
    示例上传接口：你可以把用户偏好 / 历史行程等 JSON 文件传进来，放在 data_dir 下，后续在 Agent 里读取。
    """
    cfg = load_settings(CONFIG_PATH)
    data_dir = cfg.project.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    dest = data_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    return {"filename": file.filename, "city": city}


