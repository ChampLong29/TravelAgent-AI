"""
travel/src/travel_agent/storage/user_profile.py

三层压缩记忆系统 — 第三层（L3）：跨 session 用户偏好 / 历史摘要持久化。

设计目标
--------
1. 把用户在每次会话中体现出的偏好（目的地、预算档次、出行人数、交通偏好等）
   提取并写入本地 JSON 文件，跨 session 持久保存。
2. 在新 session 开始时，将用户画像作为 system prompt 补丁注入，让 Agent 第一
   轮就"认识"这位用户。
3. 每次 session 结束（或超过阈值）时，用本次会话的 L1 摘要更新用户历史摘要。
4. 纯本地实现（JSON 文件），无需额外依赖；后续可无缝替换为向量数据库。

文件布局
--------
  <data_dir>/
    user_profiles/
      default.json          ← 单用户模式（Web 演示）
      <user_id>.json        ← 多用户模式（预留扩展）

层级关系
--------
  L1  memory_compressor.py   ← 消息滑动窗口 + LLM 摘要
  L2  agent_memory.py        ← ArtifactStore 工具结果持久化 + context_snapshot 注入
  L3  user_profile.py        ← 本文件：跨 session 用户偏好 / 历史摘要
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from travel_agent.utils.logging import logger as _base_logger
    logger = _base_logger
except Exception:
    import logging
    logger = logging.getLogger(__name__)


# ── 偏好字段定义 ──────────────────────────────────────────────────────────

_DEFAULT_PROFILE: Dict[str, Any] = {
    # 用户基本偏好
    "preferred_cities": [],          # List[str] 常去 / 喜欢的城市
    "budget_level": None,            # "economy" | "mid" | "luxury" | None
    "travel_pace": None,             # "relaxed" | "standard" | "intensive" | None
    "group_size": None,              # int | None
    "preferred_transport": [],       # List[str] "驾车" | "地铁" | "步行" 等
    "cuisine_preferences": [],       # List[str] 菜系偏好
    "poi_preferences": [],           # List[str] 景点类型偏好，如 "历史文化" "自然风光"
    # 历史摘要（最近 N 次 session 的 L1 摘要）
    "session_summaries": [],         # List[{"session_id", "summary", "created_at"}]
    "max_summaries": 5,              # 最多保留多少条历史摘要
    # 元数据
    "created_at": None,
    "updated_at": None,
}


class UserProfileStore:
    """
    管理单个用户的长期偏好档案。

    Parameters
    ----------
    data_dir:
        项目数据根目录（config.toml 中的 project.data_dir）。
    user_id:
        用户标识，默认 "default"（单用户 Web 演示模式）。
    """

    def __init__(
        self,
        data_dir: str | Path,
        user_id: str = "default",
    ) -> None:
        self.data_dir = Path(data_dir)
        self.user_id = user_id
        self._profile_dir = self.data_dir / "user_profiles"
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._profile_dir / f"{user_id}.json"
        self._cache: Optional[Dict[str, Any]] = None

    # ── 读写 ──────────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                # 补全可能缺失的字段（版本升级兼容）
                for k, v in _DEFAULT_PROFILE.items():
                    data.setdefault(k, v)
                self._cache = data
                return data
            except Exception as exc:
                logger.warning("[UserProfile] 加载失败，使用默认值: %s", exc)
        profile = dict(_DEFAULT_PROFILE)
        profile["created_at"] = time.time()
        profile["updated_at"] = time.time()
        self._cache = profile
        return profile

    def _save(self) -> None:
        if self._cache is None:
            return
        self._cache["updated_at"] = time.time()
        self._path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── 偏好更新 API ──────────────────────────────────────────────────────

    def update_preferences(self, **kwargs: Any) -> None:
        """
        更新用户偏好字段。

        可用字段：
            preferred_cities (List[str]),
            budget_level (str),
            travel_pace (str),
            group_size (int),
            preferred_transport (List[str]),
            cuisine_preferences (List[str]),
            poi_preferences (List[str])

        列表字段会自动去重合并（不覆盖），标量字段直接覆盖。

        示例::

            store.update_preferences(budget_level="mid", preferred_cities=["成都", "重庆"])
        """
        profile = self._load()
        _list_fields = {
            "preferred_cities", "preferred_transport",
            "cuisine_preferences", "poi_preferences",
        }
        for key, value in kwargs.items():
            if key not in _DEFAULT_PROFILE:
                logger.debug("[UserProfile] 忽略未知字段: %s", key)
                continue
            if key in _list_fields and isinstance(value, list):
                existing: list = profile.get(key) or []
                merged = list(dict.fromkeys(existing + value))   # 去重保序
                profile[key] = merged
            else:
                profile[key] = value
        self._save()
        logger.debug("[UserProfile] 用户 %s 偏好已更新: %s", self.user_id, list(kwargs.keys()))

    def add_session_summary(self, session_id: str, summary: str) -> None:
        """
        把本次 session 的 L1 摘要追加到用户历史摘要列表，
        并按 max_summaries 限制滚动丢弃最旧的记录。
        """
        if not summary:
            return
        profile = self._load()
        summaries: list = profile.get("session_summaries") or []
        summaries.append({
            "session_id": session_id,
            "summary": summary,
            "created_at": time.time(),
        })
        max_n = int(profile.get("max_summaries") or 5)
        if len(summaries) > max_n:
            summaries = summaries[-max_n:]
        profile["session_summaries"] = summaries
        self._save()
        logger.info("[UserProfile] 用户 %s 添加 session 摘要: %s", self.user_id, session_id)

    # ── 读取 API ──────────────────────────────────────────────────────────

    def get_profile(self) -> Dict[str, Any]:
        """返回完整用户档案（深拷贝）。"""
        import copy
        return copy.deepcopy(self._load())

    def build_profile_prompt(self, lang: str = "zh") -> str:
        """
        将用户偏好和历史摘要转换为可注入 system prompt 的文本段落。
        若无任何有效偏好，返回空字符串。
        """
        profile = self._load()

        lines: list[str] = []

        # ── 偏好部分 ──
        pref_lines: list[str] = []
        if profile.get("preferred_cities"):
            cities = "、".join(profile["preferred_cities"][:6])
            pref_lines.append(f"• 常旅游城市：{cities}")
        if profile.get("budget_level"):
            level_map = {"economy": "经济型", "mid": "中档", "luxury": "豪华型"}
            pref_lines.append(
                f"• 预算偏好：{level_map.get(profile['budget_level'], profile['budget_level'])}"
            )
        if profile.get("travel_pace"):
            pace_map = {"relaxed": "轻松休闲", "standard": "标准节奏", "intensive": "紧凑充实"}
            pref_lines.append(
                f"• 行程节奏：{pace_map.get(profile['travel_pace'], profile['travel_pace'])}"
            )
        if profile.get("group_size"):
            pref_lines.append(f"• 常见出行人数：{profile['group_size']} 人")
        if profile.get("cuisine_preferences"):
            pref_lines.append(f"• 饮食偏好：{'、'.join(profile['cuisine_preferences'][:5])}")
        if profile.get("poi_preferences"):
            pref_lines.append(f"• 景点偏好：{'、'.join(profile['poi_preferences'][:5])}")
        if profile.get("preferred_transport"):
            pref_lines.append(f"• 交通偏好：{'、'.join(profile['preferred_transport'][:4])}")

        # ── 历史摘要部分（最近 2 条）──
        summaries = (profile.get("session_summaries") or [])[-2:]
        sum_lines: list[str] = []
        for i, s in enumerate(summaries, 1):
            text = (s.get("summary") or "").strip()
            if text:
                sum_lines.append(f"  {i}. {text[:200]}")

        if not pref_lines and not sum_lines:
            return ""

        if lang == "zh":
            if pref_lines:
                lines.append("## 用户偏好（来自历史记录）")
                lines.extend(pref_lines)
            if sum_lines:
                lines.append("## 近期旅行规划历史")
                lines.extend(sum_lines)
        else:
            if pref_lines:
                lines.append("## User Preferences (from history)")
                lines.extend(pref_lines)
            if sum_lines:
                lines.append("## Recent Travel Planning History")
                lines.extend(sum_lines)

        return "\n".join(lines)

    def extract_preferences_from_messages(
        self, messages: list, lang: str = "zh"
    ) -> None:
        """
        从本次 session 的消息列表中自动提取用户偏好并更新档案。
        使用简单规则匹配，不调用 LLM（保持轻量）。

        目前提取：
        - 城市名（出现在 HumanMessage 中的常见城市）
        - 出行人数（"X 人" 模式）
        - 预算关键词（经济/豪华等）
        - 行程节奏关键词（轻松/紧凑等）
        """
        import re
        from langchain_core.messages import HumanMessage as _HM

        # 常见城市列表（可扩展）
        _cities = [
            "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "西安",
            "南京", "武汉", "厦门", "青岛", "三亚", "丽江", "大理", "桂林",
            "苏州", "无锡", "宁波", "长沙", "昆明", "贵阳", "乌鲁木齐", "拉萨",
            "哈尔滨", "沈阳", "大连", "天津", "石家庄", "郑州", "济南", "福州",
        ]
        _budget_map = {
            "经济": "economy", "便宜": "economy", "实惠": "economy",
            "豪华": "luxury", "高档": "luxury", "奢华": "luxury",
            "中档": "mid", "普通": "mid", "适中": "mid",
        }
        _pace_map = {
            "轻松": "relaxed", "休闲": "relaxed", "慢": "relaxed",
            "紧凑": "intensive", "充实": "intensive", "密集": "intensive",
            "标准": "standard", "普通": "standard",
        }

        found_cities: list[str] = []
        found_budget: Optional[str] = None
        found_pace: Optional[str] = None
        found_group: Optional[int] = None

        for m in messages:
            if not isinstance(m, _HM):
                continue
            text = str(getattr(m, "content", "") or "")

            for city in _cities:
                if city in text and city not in found_cities:
                    found_cities.append(city)

            for kw, level in _budget_map.items():
                if kw in text:
                    found_budget = level
                    break

            for kw, pace in _pace_map.items():
                if kw in text:
                    found_pace = pace
                    break

            match = re.search(r"(\d+)\s*[人名口]", text)
            if match and found_group is None:
                try:
                    n = int(match.group(1))
                    if 1 <= n <= 20:
                        found_group = n
                except ValueError:
                    pass

        updates: Dict[str, Any] = {}
        if found_cities:
            updates["preferred_cities"] = found_cities
        if found_budget:
            updates["budget_level"] = found_budget
        if found_pace:
            updates["travel_pace"] = found_pace
        if found_group:
            updates["group_size"] = found_group

        if updates:
            self.update_preferences(**updates)
            logger.info("[UserProfile] 自动提取偏好: %s", updates)
