"""
travel/src/travel_agent/storage/memory_compressor.py

三层压缩记忆系统 — 第一层（L1）：In-Context 消息滑动窗口 + LLM 摘要压缩。

设计目标
--------
1. 维持 messages 列表不超过 ``max_messages`` 条（或 ``max_tokens`` 个 token 估算值）。
2. 当消息数超出阈值时，把最早的一批消息（保留最近 ``keep_recent`` 条）用 LLM
   压缩成一条 SystemMessage 摘要，替换进消息列表的头部。
3. 压缩结果同时持久化到磁盘（ ``<session_dir>/summary.json`` ），下次重建时可恢复。
4. 对上层调用透明：只需调用 ``maybe_compress(messages)`` 即可，超限才压缩。

层级关系
--------
  L1  memory_compressor.py   ← 本文件（消息滑动窗口 + LLM 摘要）
  L2  agent_memory.py        ← ArtifactStore 工具结果持久化 + context_snapshot 注入
  L3  user_profile.py        ← 跨 session 用户偏好 / 历史摘要持久化
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

try:
    from travel_agent.utils.logging import logger as _base_logger
    logger = _base_logger
except Exception:
    import logging
    logger = logging.getLogger(__name__)


# ── token 估算（避免引入 tiktoken 依赖）────────────────────────────────────
def _estimate_tokens(messages: List[BaseMessage]) -> int:
    """粗略估算消息列表 token 数（中文字符 ≈ 1.5 token，英文 ≈ 0.25 token）。"""
    total = 0
    for m in messages:
        content = getattr(m, "content", "") or ""
        if isinstance(content, list):
            content = " ".join(
                (c.get("text") or "") if isinstance(c, dict) else str(c)
                for c in content
            )
        for ch in str(content):
            if "\u4e00" <= ch <= "\u9fff":
                total += 2        # 中文字符约 1.5 token，保守取 2
            else:
                total += 1
    return total // 4             # 粗略 /4 换算 token


# ─────────────────────────────────────────────────────────────────────────────
# MemoryCompressor
# ─────────────────────────────────────────────────────────────────────────────

class MemoryCompressor:
    """
    L1 消息压缩器。

    Parameters
    ----------
    llm:
        用于生成摘要的 LLM 实例（与 Agent 共用同一个即可）。
    session_dir:
        该 session 的工作目录（用于持久化 summary.json）。
    max_messages:
        消息列表超过此数量时触发压缩。默认 40 条。
    keep_recent:
        压缩时保留最近 N 条消息不参与摘要（保证短期上下文完整）。默认 10 条。
    max_tokens_estimate:
        估算 token 数超过此值时也触发压缩（双重保险）。默认 6000。
    lang:
        摘要语言，"zh" 或 "en"。
    """

    def __init__(
        self,
        llm: BaseChatModel,
        session_dir: str | Path,
        max_messages: int = 40,
        keep_recent: int = 10,
        max_tokens_estimate: int = 6000,
        lang: str = "zh",
    ) -> None:
        self.llm = llm
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.max_messages = max_messages
        self.keep_recent = keep_recent
        self.max_tokens_estimate = max_tokens_estimate
        self.lang = lang
        self._summary_path = self.session_dir / "summary.json"

    # ── 内部辅助 ──────────────────────────────────────────────────────────

    def _should_compress(self, messages: List[BaseMessage]) -> bool:
        """判断是否需要压缩。"""
        if len(messages) > self.max_messages:
            return True
        if _estimate_tokens(messages) > self.max_tokens_estimate:
            return True
        return False

    def _split_messages(
        self, messages: List[BaseMessage]
    ) -> tuple[list[BaseMessage], list[BaseMessage]]:
        """
        把消息分为「待压缩部分」和「保留部分」。
        SystemMessage 始终保留在头部，不参与压缩。

        Returns
        -------
        (to_compress, to_keep)
            to_compress: 需要被摸要的消息（不含 SystemMessage）
            to_keep: 保留的最近 N 条消息（不含 SystemMessage）
        """
        # 分离开头的 SystemMessage（system prompt 和历史摘要）
        non_sys: list[BaseMessage] = [
            m for m in messages if not isinstance(m, SystemMessage)
        ]

        # non_sys 按 keep_recent 分割
        if len(non_sys) <= self.keep_recent:
            return [], non_sys   # 无需压缩
        to_compress = non_sys[: len(non_sys) - self.keep_recent]
        to_keep = non_sys[len(non_sys) - self.keep_recent :]
        return to_compress, to_keep

    def _build_compress_prompt(self, to_compress: List[BaseMessage]) -> str:
        """把待压缩消息序列化为文本，供 LLM 生成摘要。"""
        lines: list[str] = []
        for m in to_compress:
            if isinstance(m, SystemMessage):
                continue   # 不把 system prompt 本身送进摘要
            role = (
                "用户" if isinstance(m, HumanMessage)
                else "助手" if isinstance(m, AIMessage)
                else "工具结果"
            )
            content = getattr(m, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(
                    (c.get("text") or "") if isinstance(c, dict) else str(c)
                    for c in content
                )
            # 工具调用信息
            tool_calls = getattr(m, "tool_calls", None) or []
            if tool_calls:
                tc_desc = ", ".join(
                    f"{tc.get('name','?')}({json.dumps(tc.get('args',{}), ensure_ascii=False)[:80]})"
                    for tc in tool_calls
                )
                content = f"[调用工具: {tc_desc}]\n{content}"
            lines.append(f"[{role}]: {content[:300]}")   # 截断超长内容

        conversation_text = "\n".join(lines)

        if self.lang == "zh":
            return (
                "请将以下旅行规划对话历史压缩为简洁摘要（不超过 300 字），"
                "保留用户的核心需求（目的地、天数、人数、预算、偏好）、"
                "已确认的景点/酒店/餐厅信息和关键决策，去除冗余的工具调用细节。\n\n"
                f"对话历史：\n{conversation_text}\n\n"
                "请输出摘要（不要加任何前缀，直接输出摘要内容）："
            )
        return (
            "Summarize the following travel planning conversation in no more than 200 words. "
            "Keep user's core requirements (destination, days, budget, preferences), "
            "confirmed POIs/hotels/restaurants, and key decisions. "
            "Omit verbose tool call details.\n\n"
            f"Conversation:\n{conversation_text}\n\n"
            "Summary (output directly, no prefix):"
        )

    async def _call_llm_summary(self, prompt: str) -> str:
        """调用 LLM 生成摘要，失败时返回空字符串。"""
        try:
            resp = await self.llm.ainvoke([HumanMessage(content=prompt)])
            content = getattr(resp, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(
                    (c.get("text") or "") if isinstance(c, dict) else str(c)
                    for c in content
                )
            return str(content).strip()
        except Exception as exc:
            logger.warning("[MemoryCompressor] LLM 摘要调用失败: %s", exc)
            return ""

    def _persist_summary(self, summary_text: str, compressed_count: int) -> None:
        """把摘要持久化到磁盘，供下次重建或 L3 使用。"""
        record = {
            "summary": summary_text,
            "compressed_count": compressed_count,
            "updated_at": time.time(),
        }
        self._summary_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_persisted_summary(self) -> Optional[str]:
        """从磁盘加载上次持久化的摘要（session 重连时使用）。"""
        if not self._summary_path.exists():
            return None
        try:
            data = json.loads(self._summary_path.read_text(encoding="utf-8"))
            return data.get("summary") or None
        except Exception:
            return None

    # ── 公开 API ───────────────────────────────────────────────────────────

    async def maybe_compress(
        self, messages: List[BaseMessage]
    ) -> List[BaseMessage]:
        """
        检查消息列表是否超出阈值，若超出则异步压缩并返回压缩后的列表；
        否则原样返回。

        设计原则：原始 system prompt（第一条 SystemMessage）始终保留。
        压缩摘要作为第二条 SystemMessage 插入，替代上一次的摘要内容。

        Parameters
        ----------
        messages:
            当前完整消息列表（应只包含对话消息，不含动态 system prompt）。

        Returns
        -------
        List[BaseMessage]
            压缩后（或未经修改的）消息列表。
        """
        if not self._should_compress(messages):
            return messages

        to_compress, to_keep = self._split_messages(messages)
        if not to_compress:
            return messages

        logger.info(
            "[MemoryCompressor] 触发压缩：共 %d 条消息，压缩 %d 条，保留 %d 条",
            len(messages),
            len(to_compress),
            len(to_keep),
        )

        prompt = self._build_compress_prompt(to_compress)
        summary_text = await self._call_llm_summary(prompt)

        # 提取原始 system prompt（列表里第一条非摘要的 SystemMessage）
        original_sys: list[BaseMessage] = []
        for m in messages:
            if isinstance(m, SystemMessage):
                # 跳过上一次压缩生成的摘要 SystemMessage
                content = str(getattr(m, "content", "") or "")
                if "【历史对话摘要】" in content or "[Conversation Summary]" in content:
                    continue
                original_sys.append(m)
            # 只取头部 sys，遇到非 sys 就停
            elif original_sys or not isinstance(m, SystemMessage):
                break

        if not summary_text:
            # LLM 失败时降级为截断：直接丢弃最早的消息
            logger.warning("[MemoryCompressor] 摘要失败，降级为截断策略")
            return original_sys + to_keep

        # 构建摘要 SystemMessage
        if self.lang == "zh":
            summary_msg = SystemMessage(
                content=f"【历史对话摘要】以下是本次会话的早期对话摘要，供参考：\n{summary_text}"
            )
        else:
            summary_msg = SystemMessage(
                content=f"[Conversation Summary] Earlier context:\n{summary_text}"
            )

        # 持久化摘要
        self._persist_summary(summary_text, len(to_compress))

        result = original_sys + [summary_msg] + to_keep
        logger.info(
            "[MemoryCompressor] 压缩完成：%d → %d 条消息",
            len(messages),
            len(result),
        )
        return result

    def sync_compress_fallback(
        self, messages: List[BaseMessage]
    ) -> List[BaseMessage]:
        """
        同步降级压缩（不调用 LLM，仅做截断）。
        用于无法 await 的场景（例如同步代码路径）。
        """
        if not self._should_compress(messages):
            return messages
        sys_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        non_sys = [m for m in messages if not isinstance(m, SystemMessage)]
        kept = non_sys[-self.keep_recent :]
        logger.info(
            "[MemoryCompressor] 同步截断: %d → %d 条", len(messages), len(sys_msgs) + len(kept)
        )
        return sys_msgs + kept
