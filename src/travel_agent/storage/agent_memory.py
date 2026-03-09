"""
travel/src/travel_agent/storage/agent_memory.py

Session-scoped artifact storage for the travel agent.
Each session stores tool outputs (POI lists, weather, routes, etc.)
as JSON files under artifacts/<session_id>/<node_id>/<artifact_id>.json.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from travel_agent.utils.logging import logger  # noqa

try:
    from travel_agent.utils.logging import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────

@dataclass
class ArtifactMeta:
    session_id: str
    artifact_id: str
    node_id: str       # tool / node name, e.g. "search_poi"
    path: str          # absolute path to the JSON file
    summary: Optional[str]
    created_at: float


# ─────────────────────────────────────────────────────────────
# ArtifactStore
# ─────────────────────────────────────────────────────────────

class ArtifactStore:
    """
    Stores and retrieves tool-execution results for a single session.

    Directory layout::

        artifacts/
          <session_id>/
            meta.json          ← list of ArtifactMeta records
            search_poi/
              search_poi_<ts>.json
            check_weather/
              check_weather_<ts>.json
            ...
    """

    def __init__(self, artifacts_dir: str | Path, session_id: str) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.session_id = session_id
        self.blobs_dir = self.artifacts_dir / session_id
        self.meta_path = self.blobs_dir / "meta.json"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        if not self.meta_path.exists() or self.meta_path.stat().st_size == 0:
            self._save_meta_list([])

    # ── meta helpers ──────────────────────────────────────────

    def _load_meta_list(self) -> List[ArtifactMeta]:
        if not self.meta_path.exists():
            return []
        with self.meta_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [ArtifactMeta(**item) for item in data]

    def _save_meta_list(self, metas: List[ArtifactMeta]) -> None:
        with self.meta_path.open("w", encoding="utf-8") as fh:
            json.dump([asdict(m) for m in metas], fh, ensure_ascii=False, indent=2)

    def _append_meta(self, meta: ArtifactMeta) -> None:
        metas = self._load_meta_list()
        metas.append(meta)
        self._save_meta_list(metas)

    # ── public API ────────────────────────────────────────────

    def generate_artifact_id(self, node_id: str) -> str:
        return f"{node_id}_{uuid.uuid4().hex[:8]}"

    def save_result(
        self,
        node_id: str,
        payload: Any,
        summary: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> ArtifactMeta:
        """
        Persist a tool-execution result.

        Args:
            node_id:     Name of the tool/node (e.g. ``"search_poi"``).
            payload:     The raw result data (must be JSON-serialisable).
            summary:     One-line human-readable description of the result.
            artifact_id: Provide a custom ID, or let the store generate one.

        Returns:
            :class:`ArtifactMeta` with path and metadata.
        """
        if artifact_id is None:
            artifact_id = self.generate_artifact_id(node_id)

        store_dir = self.blobs_dir / node_id
        store_dir.mkdir(parents=True, exist_ok=True)
        file_path = store_dir / f"{artifact_id}.json"

        record = {
            "session_id": self.session_id,
            "artifact_id": artifact_id,
            "node_id": node_id,
            "created_at": time.time(),
            "summary": summary,
            "payload": payload,
        }
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)

        meta = ArtifactMeta(
            session_id=self.session_id,
            artifact_id=artifact_id,
            node_id=node_id,
            path=str(file_path),
            summary=summary,
            created_at=record["created_at"],
        )
        self._append_meta(meta)
        logger.debug("[ArtifactStore] saved %s → %s", artifact_id, file_path)
        return meta

    def load_result(self, artifact_id: str) -> Tuple[Optional[ArtifactMeta], Any]:
        """Load a previously saved result by artifact_id."""
        metas = self._load_meta_list()
        meta = next((m for m in metas if m.artifact_id == artifact_id), None)
        if meta is None:
            return None, f"artifact '{artifact_id}' not found"
        with open(meta.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return meta, data

    def get_latest_meta(self, node_id: str) -> Optional[ArtifactMeta]:
        """Return the most-recent artifact for the given node."""
        metas = self._load_meta_list()
        candidates = [m for m in metas if m.node_id == node_id]
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.created_at)

    def get_all_meta(self, node_id: Optional[str] = None) -> List[ArtifactMeta]:
        """Return all stored artifacts, optionally filtered by node_id."""
        metas = self._load_meta_list()
        if node_id:
            metas = [m for m in metas if m.node_id == node_id]
        return sorted(metas, key=lambda m: m.created_at)

    def context_snapshot(self) -> Dict[str, Any]:
        """
        Build a compact context dict of the latest result per node.
        Useful for injecting into LLM system prompts.
        """
        metas = self._load_meta_list()
        latest: Dict[str, ArtifactMeta] = {}
        for m in metas:
            if m.node_id not in latest or m.created_at > latest[m.node_id].created_at:
                latest[m.node_id] = m

        snapshot: Dict[str, Any] = {}
        for node_id, meta in latest.items():
            try:
                _, data = self.load_result(meta.artifact_id)
                snapshot[node_id] = {
                    "artifact_id": meta.artifact_id,
                    "summary": meta.summary,
                    "payload": data.get("payload") if isinstance(data, dict) else data,
                }
            except Exception as exc:
                logger.warning("[ArtifactStore] failed to load %s: %s", meta.artifact_id, exc)
        return snapshot

    def build_context_prompt(self, lang: str = "zh") -> str:
        """
        三层记忆 L2：将本 session 已收集的工具结果快照转换为可注入
        system prompt 的文本段落。

        只展示对规划决策有价值的节点（排除纯渲染类工具），
        payload 超长时截断，避免撑爆 context window。

        Parameters
        ----------
        lang:
            输出语言，"zh" 或 "en"。

        Returns
        -------
        str
            可直接拼入 system prompt 的文本，若无已收集数据则返回空字符串。
        """
        # 渲染类工具的结果不需要注入（前端消费，LLM 无需重读）
        _SKIP_NODES = {
            "render_map_pois", "render_map_route", "render_itinerary",
            "validate_json", "fix_json",
        }
        # 每个节点 payload 最大字符数（防止过长）
        _MAX_PAYLOAD_CHARS = 600

        snapshot = self.context_snapshot()
        if not snapshot:
            return ""

        lines: list[str] = []
        for node_id, info in snapshot.items():
            if node_id in _SKIP_NODES:
                continue
            summary = info.get("summary") or ""
            payload = info.get("payload")
            artifact_id = info.get("artifact_id", "")

            # 序列化 payload
            if payload is None:
                payload_str = ""
            elif isinstance(payload, str):
                payload_str = payload
            else:
                try:
                    payload_str = json.dumps(payload, ensure_ascii=False)
                except Exception:
                    payload_str = str(payload)

            if len(payload_str) > _MAX_PAYLOAD_CHARS:
                payload_str = payload_str[:_MAX_PAYLOAD_CHARS] + "…（已截断）"

            if lang == "zh":
                lines.append(
                    f"- **{node_id}**（artifact_id: `{artifact_id}`）\n"
                    f"  摘要: {summary}\n"
                    f"  数据: {payload_str}"
                )
            else:
                lines.append(
                    f"- **{node_id}** (artifact_id: `{artifact_id}`)\n"
                    f"  Summary: {summary}\n"
                    f"  Data: {payload_str}"
                )

        if not lines:
            return ""

        header = (
            "## 本次会话已收集的旅行数据（工具执行结果）\n"
            "以下数据已通过工具调用获取，规划时请直接引用，无需重复查询：\n"
            if lang == "zh"
            else "## Travel data collected in this session\n"
                 "The following data has been retrieved via tools. "
                 "Use it directly without re-querying:\n"
        )
        return header + "\n".join(lines)
