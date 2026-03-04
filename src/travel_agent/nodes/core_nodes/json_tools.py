from __future__ import annotations

import json
from typing import Any, Dict

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from travel_agent.config import load_settings, default_config_path
from travel_agent.utils.logging import logger


@tool("validate_json", return_direct=False)
def validate_json_tool(payload: str) -> Dict[str, Any]:
    """
    检查一段字符串是否为合法 JSON。

    参数：
    - payload: 任意字符串（通常是模型输出的 JSON 文本）

    返回：
    - {
        "ok": bool,          # 是否为合法 JSON
        "error": str | null, # 若解析失败，包含错误信息
        "data": Any | null   # 解析成功后的 Python 对象
      }
    """
    try:
        data = json.loads(payload)
        return {"ok": True, "error": None, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "data": None}


@tool("fix_json", return_direct=False)
async def fix_json_tool(raw_text: str, instruction: str = "") -> Dict[str, Any]:
    """
    利用 LLM 对“接近 JSON 但不合法”的文本进行纠错，输出尽量合法的 JSON。

    典型用法：当 validate_json 返回 ok=False 时，再调用本工具尝试修复。

    参数：
    - raw_text: 原始字符串（可能包含多余说明、反引号、尾逗号等）
    - instruction: 可选的 schema/格式提示，例如：
      "应该是 {'assistant_message': str, 'draft': {...}} 结构"
    """
    try:
        data = json.loads(raw_text)
        return {"ok": True, "fixed": False, "data": data, "error": None}
    except Exception:
        pass

    cfg = load_settings(default_config_path())
    llm = ChatOpenAI(
        model=cfg.llm.model,
        base_url=cfg.llm.base_url,
        api_key=cfg.llm.api_key,
        timeout=cfg.llm.timeout,
    )

    prompt = (
        "你是一个 JSON 格式修复助手。\n"
        "任务：根据给定的原始文本，提取或修复其中的 JSON 内容，使之成为合法、可解析的 JSON。\n"
        "要求：\n"
        "1) 只输出 JSON 本身，不要包含任何额外解释。\n"
        "2) 尽量保持字段语义不变；无法确定的字段可以删除或置为 null。\n"
    )
    if instruction:
        prompt += f"\n额外格式提示：{instruction}\n"

    prompt += "\n原始内容如下（可能不合法）：\n```text\n" + raw_text + "\n```\n"
    prompt += "请输出修复后的 JSON。"

    resp = await llm.ainvoke(prompt)
    text = getattr(resp, "content", str(resp))

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        logger.warning("fix_json: 无法在模型输出中找到 JSON 子串，原始输出: %s", text)
        return {"ok": False, "fixed": False, "data": None, "error": "模型输出中未找到 JSON"}

    json_str = text[start : end + 1]
    try:
        data = json.loads(json_str)
        return {"ok": True, "fixed": True, "data": data, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("fix_json: JSON 解析失败: %s, content=%s", exc, json_str)
        return {"ok": False, "fixed": True, "data": None, "error": str(exc)}

