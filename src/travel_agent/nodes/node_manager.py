from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from langchain_core.tools import BaseTool


@dataclass
class NodeManager:
    """
    负责管理所有可用的工具节点，提供按名称查询等能力。
    """

    tools: List[BaseTool] = field(default_factory=list)

    def as_dict(self) -> Dict[str, BaseTool]:
        return {t.name: t for t in self.tools}

