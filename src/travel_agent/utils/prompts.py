from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

# ─────────────────────────────────────────────
# 路径：travel/prompts/tasks/
# ─────────────────────────────────────────────
_TRAVEL_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # travel/
PROMPTS_DIR = _TRAVEL_ROOT / "prompts" / "tasks"


class PromptBuilder:
    """从 prompts/tasks/<task>/<lang>/<role>.md 文件加载并渲染模板。"""

    def __init__(self, prompts_dir: Path = PROMPTS_DIR):
        self.prompts_dir = prompts_dir
        self._cache: Dict[str, str] = {}

    def _load_template(self, task: str, role: str, lang: str) -> str:
        cache_key = f"{task}:{role}:{lang}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        path = self.prompts_dir / task / lang / f"{role}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")
        content = path.read_text(encoding="utf-8")
        self._cache[cache_key] = content
        return content

    def render(self, task: str, role: str, lang: str = "zh", **variables: Any) -> str:
        """渲染单个模板，用 {{variable}} 占位符替换。"""
        template = self._load_template(task, role, lang)
        return re.sub(
            r"\{\{(.*?)\}\}",
            lambda m: str(variables.get(m.group(1).strip(), f"{{{{{m.group(1)}}}}}")),
            template,
        )

    def build(self, task: str, lang: str = "zh", **user_vars: Any) -> Dict[str, str]:
        """构建完整 prompt pair {system, user}。user.md 不存在时只返回 system。"""
        result: Dict[str, str] = {"system": self.render(task, "system", lang)}
        try:
            result["user"] = self.render(task, "user", lang, **user_vars)
        except FileNotFoundError:
            pass
        return result


# ─── 全局单例 ───────────────────────────────
_builder = PromptBuilder()


def get_prompt(name: str, lang: str = "zh", **kwargs: Any) -> str:
    """
    获取并渲染单个 prompt。

    Args:
        name: "task.role" 格式，例如 "format_itinerary.system"
        lang: 语言代码，默认 "zh"
        **kwargs: 模板变量
    """
    parts = name.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid prompt name: '{name}', expected 'task.role'")
    task, role = parts
    return _builder.render(task, role, lang, **kwargs)


def build_prompts(task: str, lang: str = "zh", **user_vars: Any) -> Dict[str, str]:
    """构建完整 prompt pair。"""
    return _builder.build(task, lang, **user_vars)


def get_system_prompt(lang: str = "zh") -> str:
    """
    获取 Agent 总系统提示词（instruction/system.md）。
    文件不存在时回落到内置默认值。
    """
    try:
        return _builder.render("instruction", "system", lang)
    except FileNotFoundError:
        pass

    # ─── 内置回落值 ───
    if lang == "en":
        return (
            "You are an intelligent travel planning assistant. "
            "Help users design itineraries, suggest POIs, estimate budgets, "
            "and give weather-aware travel advice. Always use tools instead of "
            "inventing information. Ask clarifying questions when needed."
        )
    return (
        "你是一个智能旅行规划助手，负责根据用户的偏好与约束，"
        "设计多日行程、推荐景点/餐厅/酒店，合理安排每天节奏，"
        "并结合天气与交通情况给出实用建议。\n"
        "必须先调用工具获取真实数据，不得凭空编造地点信息。"
        "当用户信息不充分时，先主动追问。"
    )
