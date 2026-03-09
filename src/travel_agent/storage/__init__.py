"""travel_agent.storage – 三层压缩记忆系统。

L1: MemoryCompressor  – 消息滑动窗口 + LLM 摘要压缩
L2: ArtifactStore     – 工具执行结果持久化 + context_snapshot 注入
L3: UserProfileStore  – 跨 session 用户偏好 / 历史摘要持久化
"""
from travel_agent.storage.agent_memory import ArtifactMeta, ArtifactStore
from travel_agent.storage.session_manager import SessionLifecycleManager
from travel_agent.storage.memory_compressor import MemoryCompressor
from travel_agent.storage.user_profile import UserProfileStore

__all__ = [
    "ArtifactMeta",
    "ArtifactStore",
    "SessionLifecycleManager",
    "MemoryCompressor",
    "UserProfileStore",
]
