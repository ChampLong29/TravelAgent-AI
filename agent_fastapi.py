from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
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
        # langchain-mcp-adapters 把 MCP 响应转为 content blocks 列表：[{"type": "text", "text": "..."}]
        if isinstance(raw, list):
            raw = next((b["text"] for b in raw if isinstance(b, dict) and b.get("type") == "text"), "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        # 解包 MCP 包装格式 {artifact_id, result, isError}
        if isinstance(payload, dict) and "result" in payload and "artifact_id" in payload:
            payload = payload["result"]
        # render_itinerary / render_map_pois 等工具返回 JSON 字符串，需再次解析
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                continue
        # 天气数据：有 days 列表且每项含 date/weather 字段（区别于行程的 spots 字段）
        if isinstance(payload, dict) and "days" in payload and "city" in payload:
            # 排除行程数据（__type=itinerary 或 days 里含 spots/label 字段）
            days_list = payload.get("days") or []
            is_weather = (
                payload.get("__type") == "weather"
                or (
                    isinstance(days_list, list)
                    and days_list
                    and isinstance(days_list[0], dict)
                    and ("date" in days_list[0] or "weather" in days_list[0])
                    and "spots" not in days_list[0]
                )
            )
            if not is_weather:
                continue
            block = {
                "__type": "weather",
                "city": payload.get("city", ""),
                "days": days_list,
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
    # 去重：记录已输出的 itinerary 城市+天数 / pois 名称集合，避免同一轮重复渲染
    _seen_itinerary_keys: set[str] = set()   # "city:days"
    _seen_pois_keys: set[str] = set()        # frozenset of poi names

    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        raw = getattr(m, "content", "") or ""
        if not raw:
            continue
        # langchain-mcp-adapters 把 MCP 响应转为 content blocks 列表：[{"type": "text", "text": "..."}]
        if isinstance(raw, list):
            raw = next((b["text"] for b in raw if isinstance(b, dict) and b.get("type") == "text"), "")

        tool_name = call_id_to_name.get(getattr(m, "tool_call_id", "") or "", "")

        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue

        # 解包 MCP 包装格式 {artifact_id, result, isError}
        if isinstance(payload, dict) and "result" in payload and "artifact_id" in payload:
            if payload.get("isError"):
                continue
            payload = payload["result"]
        # render_itinerary / render_map_pois / render_map_route 返回 JSON 字符串，需再次解析
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                continue

        # ── 已有 __type 标记的工具输出（render_map_pois/route/itinerary） ──
        if isinstance(payload, dict) and payload.get("__type") in ("pois", "route", "itinerary"):
            block_type = payload.get("__type")
            if block_type == "itinerary":
                # 去重：相同城市+天数只保留最新版本（移除旧块，追加新块）
                ikey = f"{payload.get('city','')}:{len(payload.get('days') or [])}"
                if ikey in _seen_itinerary_keys:
                    # 删除旧的同 key 行程块
                    blocks = [b for b in blocks if not (
                        '"__type": "itinerary"' in b
                        and f'"city": "{payload.get("city","")}"' in b
                    )]
                _seen_itinerary_keys.add(ikey)
                has_itinerary_block = True
            elif block_type == "pois":
                # 去重：完全相同的 POI 名称集合跳过
                names_key = str(sorted(i.get("name","") for i in (payload.get("items") or [])))
                if names_key in _seen_pois_keys:
                    continue
                _seen_pois_keys.add(names_key)
            blocks.append("\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```")
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
                # 去重：若后续 render_itinerary 也输出了相同城市的行程，优先用后者
                ikey = f"{payload.get('city','')}:{len(days_data)}"
                if ikey not in _seen_itinerary_keys:
                    blocks.append("\n```json\n" + json.dumps(itinerary_block, ensure_ascii=False) + "\n```")
                    _seen_itinerary_keys.add(ikey)
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
                # 同一 pois 块内去重（同名取第一条）
                _seen_in_block: set[str] = set()
                deduped_items: list[dict] = []
                for _it in items:
                    _k = _it["name"].strip().lower()
                    if _k not in _seen_in_block:
                        _seen_in_block.add(_k)
                        deduped_items.append(_it)
                blocks.append("\n```json\n" + json.dumps(
                    {"__type": "pois", "items": deduped_items}, ensure_ascii=False
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

    # ── 兜底：LLM 做了搜索但没调 smart_plan_itinerary/render_itinerary 时 ──────
    # 收集本轮所有搜索结果，自动合成一个 itinerary 块（GLM 等弱工具调用模型的兜底）
    if not has_itinerary_block:
        # 重新扫一遍，收集所有 search_* 的有效 POI
        _fallback_spots: list[dict] = []
        _fallback_hotels: list[dict] = []
        _fallback_restaurants: list[dict] = []
        _fallback_city: str = ""
        _fallback_days: int = 0

        for m in messages:
            if not isinstance(m, ToolMessage):
                continue
            raw2 = getattr(m, "content", "") or ""
            if isinstance(raw2, list):
                raw2 = next((b["text"] for b in raw2 if isinstance(b, dict) and b.get("type") == "text"), "")
            tname = call_id_to_name.get(getattr(m, "tool_call_id", "") or "", "")
            if tname not in _TOOL_TYPE_MAP:
                continue
            try:
                p2 = json.loads(raw2) if isinstance(raw2, str) else raw2
                if isinstance(p2, dict) and "result" in p2 and "artifact_id" in p2:
                    if p2.get("isError"):
                        continue
                    p2 = p2["result"]
                if isinstance(p2, str):
                    p2 = json.loads(p2)
            except Exception:
                continue
            if not isinstance(p2, list):
                continue
            for item in p2:
                if not isinstance(item, dict):
                    continue
                try:
                    lng = float(item.get("longitude") or 0)
                    lat = float(item.get("latitude") or 0)
                except (TypeError, ValueError):
                    continue
                if not lng or not lat:
                    continue
                poi = {
                    "name":      str(item.get("name") or "地点"),
                    "longitude": lng,
                    "latitude":  lat,
                    "type":      tname.replace("search_", "").replace("poi", "poi"),
                    "address":   str(item.get("address") or ""),
                    "tel":       str(item.get("tel") or ""),
                    "rating":    str(item.get("rating") or ""),
                    "cost":      str(item.get("cost") or ""),
                    "photos":    [],
                    "note":      "",
                }
                if tname == "search_hotel":
                    _fallback_hotels.append(poi)
                elif tname == "search_restaurant":
                    _fallback_restaurants.append(poi)
                else:
                    _fallback_spots.append(poi)

            # 从 AIMessage tool_call 的 args 中尝试提取 city/days
            for ai_m in messages:
                if not isinstance(ai_m, AIMessage):
                    continue
                for tc in getattr(ai_m, "tool_calls", []) or []:
                    args = tc.get("args") or {}
                    if args.get("city") and not _fallback_city:
                        _fallback_city = str(args["city"])
                    if args.get("days") and not _fallback_days:
                        try:
                            _fallback_days = int(args["days"])
                        except (TypeError, ValueError):
                            pass

        # 有景点数据时自动规划
        if _fallback_spots:
            from travel_agent.nodes.core_nodes.smart_plan_itinerary import smart_plan_itinerary_tool as _spit
            _days = _fallback_days or max(1, (len(_fallback_spots) + 2) // 3)
            try:
                _fb_result = _spit.invoke({
                    "spots": _fallback_spots,
                    "hotels": _fallback_hotels,
                    "restaurants": _fallback_restaurants,
                    "days": _days,
                    "city": _fallback_city,
                    "title": f"{_fallback_city} {_days}日行程" if _fallback_city else "",
                    "pace": "standard",
                })
                if _fb_result.get("days"):
                    _fb_block = {
                        "__type": "itinerary",
                        "city":   _fb_result.get("city", _fallback_city),
                        "title":  _fb_result.get("title", ""),
                        "days":   _fb_result["days"],
                    }
                    blocks.append("\n```json\n" + json.dumps(_fb_block, ensure_ascii=False) + "\n```")
                    logger.info(
                        "[_extract_map_blocks] fallback itinerary generated: city=%s days=%d spots=%d",
                        _fallback_city, _days, len(_fallback_spots),
                    )
            except Exception as _fb_exc:
                logger.warning("[_extract_map_blocks] fallback itinerary failed: %s", _fb_exc)

    return "".join(blocks)


# ── MCP Server 后台任务 ────────────────────────────────────────────────────
_mcp_server_task: Optional[asyncio.Task] = None


async def _run_mcp_server(cfg) -> None:
    """在后台 asyncio task 中启动 MCP Server（streamable-http 模式）。"""
    from travel_agent.mcp.server import create_server
    import uvicorn

    mcp_server = create_server(cfg)
    # FastMCP.streamable_http_app() 返回 Starlette ASGI app，挂载到独立 uvicorn 实例
    mcp_asgi = mcp_server.streamable_http_app()
    uv_cfg = uvicorn.Config(
        app=mcp_asgi,
        host=cfg.mcp_server.connect_host,
        port=cfg.mcp_server.port,
        log_level="warning",
    )
    server = uvicorn.Server(uv_cfg)
    logger.info(
        "[MCP] Server starting on %s:%s%s",
        cfg.mcp_server.connect_host,
        cfg.mcp_server.port,
        cfg.mcp_server.path,
    )
    await server.serve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时拉起 MCP Server；关闭时取消 task。"""
    cfg = load_settings(CONFIG_PATH)
    global _mcp_server_task
    _mcp_server_task = asyncio.create_task(_run_mcp_server(cfg))
    # 等待一小段时间让 MCP Server 完成绑定，再接受 WebSocket 连接
    await asyncio.sleep(1.5)
    logger.info("[FastAPI] MCP Server task started")
    try:
        yield
    finally:
        if _mcp_server_task and not _mcp_server_task.done():
            _mcp_server_task.cancel()
            try:
                await _mcp_server_task
            except asyncio.CancelledError:
                pass
        logger.info("[FastAPI] MCP Server task stopped")


app = FastAPI(title="Travel Smart Assistant", lifespan=lifespan)


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
    cfg = load_settings(CONFIG_PATH)
    jsapi_key = cfg.map.jsapi_key
    html = Path(INDEX_HTML).read_text(encoding="utf-8")
    # 将占位 script 标签替换为含真实 key 的高德 JS API 加载标签
    html = html.replace(
        '<script type="text/javascript" id="amap-loader"></script>',
        f'<script type="text/javascript" src="https://webapi.amap.com/maps?v=2.0&key={jsapi_key}"></script>',
    )
    return html


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
            map_blocks    = _extract_map_blocks(raw_messages)
            weather_block = _extract_weather_block(raw_messages)

            # 调试日志：记录本轮工具调用名称和地图块类型
            _tool_names = []
            for _m in raw_messages:
                for _tc in getattr(_m, "tool_calls", []) or []:
                    if _tc.get("name"):
                        _tool_names.append(_tc["name"])
            import re as _re
            _block_types = _re.findall(r'"__type":\s*"([^"]+)"', map_blocks)
            logger.info(
                "[session=%s] tools=%s  map_blocks=%s  weather=%s",
                session_id, _tool_names, _block_types, bool(weather_block),
            )

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


# ── 导出 PDF ────────────────────────────────────────────────────────────────
from fastapi import Body
from fastapi.responses import StreamingResponse
import io


def _build_itinerary_html(data: dict) -> str:
    """把行程 JSON 渲染成带样式的 HTML 字符串（用于 PDF 转换）。"""
    DAY_COLORS = ["#4f46e5", "#0891b2", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0284c7"]
    itinerary = data.get("itinerary") or {}
    hotels     = data.get("hotel", [])
    restaurants = data.get("restaurant", [])

    city  = itinerary.get("city", "")
    title = itinerary.get("title", "") or (f"{city}旅行攻略" if city else "旅行攻略")
    days  = itinerary.get("days", [])

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ── HTML head + CSS ─────────────────────────────────────────────────────
    css = """
    @page { size: A4; margin: 20mm 18mm; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
           font-size: 11pt; color: #1e293b; line-height: 1.6; }
    h1 { font-size: 22pt; font-weight: 700; color: #1e293b;
         border-bottom: 3px solid #4f46e5; padding-bottom: 8px; margin-bottom: 6px; }
    .subtitle { font-size: 10pt; color: #64748b; margin-bottom: 20px; }
    .section-title { font-size: 13pt; font-weight: 600; color: #334155;
                     margin: 22px 0 10px; padding-bottom: 4px;
                     border-bottom: 1px solid #e2e8f0; }
    .day-block { margin-bottom: 18px; page-break-inside: avoid; }
    .day-label { font-size: 12pt; font-weight: 700; padding: 4px 10px;
                 border-radius: 4px; color: #fff; display: inline-block;
                 margin-bottom: 8px; }
    .spot-row { display: flex; align-items: flex-start; gap: 8px;
                margin-bottom: 7px; padding: 7px 10px;
                background: #f8fafc; border-radius: 6px; }
    .spot-num { width: 22px; height: 22px; border-radius: 50%; color: #fff;
                font-size: 9pt; font-weight: 700; flex-shrink: 0;
                display: flex; align-items: center; justify-content: center; }
    .spot-name { font-weight: 600; font-size: 10.5pt; }
    .spot-meta { font-size: 9pt; color: #64748b; margin-top: 1px; }
    .spot-note { font-size: 9pt; color: #7c3aed; margin-top: 2px; font-style: italic; }
    .sub-label { font-size: 10pt; font-weight: 600; color: #475569;
                 margin: 8px 0 4px; }
    .poi-row { display: flex; align-items: flex-start; gap: 8px;
               margin-bottom: 5px; padding: 6px 10px;
               background: #f0fdf4; border-radius: 6px; }
    .poi-row.hotel { background: #eff6ff; }
    .poi-row.rest  { background: #f0fdf4; }
    .poi-name { font-weight: 600; font-size: 10.5pt; }
    .poi-meta { font-size: 9pt; color: #64748b; }
    table.summary { width: 100%; border-collapse: collapse; margin-top: 8px;
                    font-size: 10pt; }
    table.summary th { background: #f1f5f9; padding: 6px 10px;
                       text-align: left; font-weight: 600; border: 1px solid #e2e8f0; }
    table.summary td { padding: 6px 10px; border: 1px solid #e2e8f0; vertical-align: top; }
    .footer { margin-top: 28px; font-size: 9pt; color: #94a3b8;
              border-top: 1px solid #e2e8f0; padding-top: 8px; text-align: right; }
    """

    parts = [f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">',
             f'<style>{css}</style></head><body>']

    # ── 标题 ──
    import datetime
    today = datetime.date.today().strftime("%Y年%m月%d日")
    parts.append(f'<h1>{esc(title)}</h1>')
    parts.append(f'<div class="subtitle">生成日期：{today}</div>')

    # ── 每日行程 ──
    if days:
        parts.append('<div class="section-title">📅 每日行程</div>')
        for di, day in enumerate(days):
            color = DAY_COLORS[di % len(DAY_COLORS)]
            parts.append('<div class="day-block">')
            parts.append(f'<div class="day-label" style="background:{color}">{esc(day.get("label","第"+str(di+1)+"天"))}</div>')
            for si, spot in enumerate(day.get("spots") or []):
                name = esc(spot.get("name", ""))
                addr = esc(spot.get("address", ""))
                note = esc(spot.get("note", ""))
                meta_parts = []
                if spot.get("rating"): meta_parts.append(f'⭐{spot["rating"]}')
                if addr: meta_parts.append(f'📍{addr}')
                parts.append(
                    f'<div class="spot-row">'
                    f'<div class="spot-num" style="background:{color}">{si+1}</div>'
                    f'<div><div class="spot-name">{name}</div>'
                    f'{"<div class=spot-meta>" + " · ".join(meta_parts) + "</div>" if meta_parts else ""}'
                    f'{"<div class=spot-note>💡 " + note + "</div>" if note else ""}'
                    f'</div></div>'
                )
            if day.get("hotel"):
                h = day["hotel"]
                parts.append(f'<div class="sub-label">🏨 住宿</div>')
                parts.append(
                    f'<div class="poi-row hotel">'
                    f'<div><div class="poi-name">{esc(h.get("name",""))}</div>'
                    f'<div class="poi-meta">{"⭐"+str(h["rating"]) if h.get("rating") else ""}'
                    f'{"  📍"+esc(h.get("address","")) if h.get("address") else ""}</div></div></div>'
                )
            if day.get("meals"):
                parts.append(f'<div class="sub-label">🍜 餐厅</div>')
                for m in day["meals"]:
                    parts.append(
                        f'<div class="poi-row rest">'
                        f'<div><div class="poi-name">{esc(m.get("name",""))}</div>'
                        f'<div class="poi-meta">{"🍽️"+esc(m.get("cuisine","")) if m.get("cuisine") else ""}'
                        f'{"  ⭐"+str(m["rating"]) if m.get("rating") else ""}'
                        f'{"  💰¥"+str(m.get("cost","")) if m.get("cost") else ""}'
                        f'{"  📍"+esc(m.get("address","")) if m.get("address") else ""}</div></div></div>'
                    )
            parts.append('</div>')  # day-block

    # ── 住宿汇总 ──
    if hotels:
        parts.append('<div class="section-title">🏨 住宿推荐</div>')
        parts.append('<table class="summary"><tr><th>酒店名称</th><th>评分</th><th>地址</th></tr>')
        for h in hotels:
            parts.append(
                f'<tr><td>{esc(h.get("name",""))}</td>'
                f'<td>{"⭐"+str(h["rating"]) if h.get("rating") else "-"}</td>'
                f'<td>{esc(h.get("address",""))}</td></tr>'
            )
        parts.append('</table>')

    # ── 餐厅汇总 ──
    if restaurants:
        parts.append('<div class="section-title">🍜 餐厅推荐</div>')
        parts.append('<table class="summary"><tr><th>餐厅名称</th><th>菜系</th><th>人均</th><th>评分</th><th>地址</th></tr>')
        for r in restaurants:
            parts.append(
                f'<tr><td>{esc(r.get("name",""))}</td>'
                f'<td>{esc(r.get("cuisine",""))}</td>'
                f'<td>{"¥"+str(r.get("cost","")) if r.get("cost") else "-"}</td>'
                f'<td>{"⭐"+str(r["rating"]) if r.get("rating") else "-"}</td>'
                f'<td>{esc(r.get("address",""))}</td></tr>'
            )
        parts.append('</table>')

    parts.append(f'<div class="footer">由智能旅行助手生成 · {today}</div>')
    # 打开页面后自动弹出打印对话框（用户可选"另存为 PDF"）
    parts.append('<script>window.onload=function(){window.print();}</script>')
    parts.append('</body></html>')
    return "".join(parts)


@app.post("/api/export-pdf")
async def export_pdf(payload: dict = Body(...)):
    """
    接收行程 JSON，返回可直接用浏览器打印为 PDF 的 HTML 页面。

    请求体格式：
    {
      "itinerary": { "city": "北京", "title": "...", "days": [...] },
      "hotel":     [...],
      "restaurant": [...]
    }
    """
    try:
        html_str = _build_itinerary_html(payload)
        city = (payload.get("itinerary") or {}).get("city", "旅行")
        filename = f"{city}旅行攻略.pdf"
        return StreamingResponse(
            io.BytesIO(html_str.encode("utf-8")),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'inline; filename*=UTF-8\'\'{filename}'},
        )
    except Exception as exc:
        logger.exception("[export-pdf] 失败: %s", exc)
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


