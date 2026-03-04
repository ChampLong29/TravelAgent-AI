"""
travel_agent 包

整体结构参考 FireRed-OpenStoryline：
- config.py: 负责加载 config.toml 并提供 Settings 模型
- agent.py: 组装 LLM + 工具节点，构造旅行助手 Agent
- nodes/: 旅行领域的功能节点（POI 搜索、行程规划等）
- utils/: 公共工具与 Prompt 管理
"""

