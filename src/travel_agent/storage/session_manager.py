"""
travel/src/travel_agent/storage/session_manager.py

Session lifecycle management: creates ArtifactStore instances per session,
cleans up expired sessions, and handles server-cache directories.
"""
from __future__ import annotations

import shutil
import time
import threading
import uuid
from pathlib import Path
from typing import Callable, Dict, Optional

from travel_agent.storage.agent_memory import ArtifactStore

try:
    from travel_agent.utils.logging import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


class SessionLifecycleManager:
    """
    Manages per-session :class:`ArtifactStore` instances and cleans up
    stale sessions automatically.

    Args:
        artifacts_root: Root directory under which per-session sub-dirs are created.
        cache_root:      Root directory for server-side cache files.
        retention_days:  Sessions older than this are eligible for cleanup.
        max_sessions:    Max number of retained sessions (oldest removed first).
        enable_cleanup:  If ``True``, run cleanup on :meth:`cleanup_expired`.
    """

    def __init__(
        self,
        artifacts_root: str | Path,
        cache_root: str | Path,
        retention_days: int = 3,
        max_sessions: int = 256,
        enable_cleanup: bool = True,
    ) -> None:
        self.artifacts_root = Path(artifacts_root)
        self.cache_root = Path(cache_root)
        self.retention_days = retention_days
        self.max_sessions = max_sessions
        self.enable_cleanup = enable_cleanup

        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)

        self._stores: Dict[str, ArtifactStore] = {}
        self._lock = threading.Lock()

    # ── session factory ───────────────────────────────────────

    def new_session(self) -> str:
        """Generate a fresh session ID."""
        return uuid.uuid4().hex

    def get_store(self, session_id: str) -> ArtifactStore:
        """Return (or create) an :class:`ArtifactStore` for *session_id*."""
        with self._lock:
            if session_id not in self._stores:
                self._stores[session_id] = ArtifactStore(
                    artifacts_dir=self.artifacts_root,
                    session_id=session_id,
                )
                logger.debug("[SessionMgr] created store for session %s", session_id)
            return self._stores[session_id]

    def release_session(self, session_id: str) -> None:
        """Remove the in-memory store reference (does NOT delete files)."""
        with self._lock:
            self._stores.pop(session_id, None)
        logger.debug("[SessionMgr] released session %s", session_id)

    # ── cleanup ───────────────────────────────────────────────

    def _safe_rmtree(self, path: Path) -> None:
        import os, stat as _stat
        def _on_error(func, p, exc):
            if not os.access(p, os.W_OK):
                os.chmod(p, _stat.S_IWUSR)
                func(p)
        if path.is_dir():
            shutil.rmtree(path, onerror=_on_error)
        else:
            path.unlink(missing_ok=True)

    def cleanup_expired(self, current_session_id: Optional[str] = None) -> None:
        """
        Remove session directories that exceed *retention_days* or push total
        above *max_sessions* (oldest-first).

        Args:
            current_session_id: If provided, this session is never deleted.
        """
        if not self.enable_cleanup:
            return
        cutoff = time.time() - self.retention_days * 86_400

        try:
            all_dirs = [
                p for p in self.artifacts_root.iterdir()
                if p.is_dir() and p.name != current_session_id
            ]
        except FileNotFoundError:
            return

        expired = [p for p in all_dirs if p.stat().st_mtime < cutoff]
        for p in expired:
            logger.info("[SessionMgr] removing expired session dir: %s", p.name)
            self._safe_rmtree(p)
            with self._lock:
                self._stores.pop(p.name, None)

        remaining = [p for p in all_dirs if p not in expired]
        if len(remaining) > self.max_sessions:
            oldest = sorted(remaining, key=lambda p: p.stat().st_mtime)
            excess = oldest[: len(remaining) - self.max_sessions]
            for p in excess:
                logger.info("[SessionMgr] removing excess session dir: %s", p.name)
                self._safe_rmtree(p)
                with self._lock:
                    self._stores.pop(p.name, None)
