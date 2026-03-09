# 🗺️ Travel Agent — AI 旅行规划助手

基于 **LangGraph ReAct** 架构的多工具旅行规划 Agent，集成高德地图 API，支持自然语言对话式行程规划、POI 搜索、路线规划、天气查询、预算估算，并在前端实时渲染交互地图。新增**三层压缩记忆系统**，实现消息滑动窗口压缩、工具结果上下文注入与跨会话用户偏好持久化。

> 本项目的整体架构（Agent 编排、工具节点体系、配置中心、Skills 扩展机制等）基于 [FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) 开源框架搭建，并在此基础上针对旅行场景进行了定制开发。

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🔍 **POI 搜索** | 基于高德地图搜索景点、餐厅、酒店 |
| 🏨 **酒店推荐** | 按区域、价位、评分筛选住宿选项 |
| 🍜 **餐厅搜索** | 按菜系、位置搜索周边餐厅 |
| 🧭 **智能行程规划** | K-means 地理聚类 + 节奏控制，自动按天分组 |
| 🗓️ **行程格式化** | 生成结构化每日行程，支持雨天备选方案 |
| 🛣️ **路线规划** | 步行 / 驾车 / 公交路线，含时间与距离 |
| 🚆 **交通建议** | 城市间交通方式推荐 |
| ☁️ **天气查询** | 接入高德天气 API，支持预测 |
| 💰 **预算估算** | 按人数、天数、消费习惯估算旅行花费 |
| 🗺️ **地图渲染** | 前端实时渲染 POI 标记 + 路线轨迹 |
| 📋 **行程渲染** | 可视化每日行程卡片（景点 / 住宿 / 餐厅分 Tab） |
| 📥 **导出 PDF** | 一键将行程攻略导出为 PDF（浏览器原生打印，无需额外依赖） |
| 💬 **对话历史** | localStorage 持久化聊天记录 |
| 🔌 **MCP 服务** | 将 Agent 工具通过 MCP 协议暴露，可供外部 LLM 客户端调用 |
| 🧩 **Skills 扩展** | Markdown 格式的可插拔 Skill，无需改代码即可扩展 Agent 能力 |
| 🧠 **三层压缩记忆** | L1 消息滑动窗口+LLM摘要压缩 / L2 工具结果 snapshot 注入 / L3 跨 session 用户偏好持久化 |

---

## 📸 效果展示

<p align="center">
  <img src="pic/screenshot_1.png" width="80%" alt="对话界面与地图渲染" />
  <br><em>对话界面与高德地图实时渲染</em>
</p>

<p align="center">
  <img src="pic/screenshot_2.png" width="80%" alt="行程规划结果" />
  <br><em>餐厅展示</em>
</p>

<p align="center">
  <img src="pic/screenshot_3.png" width="80%" alt="路线规划与 POI 标记" />
  <br><em>住宿展示</em>
</p>

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────┐
│         浏览器  (index.html / app.js)    │
│  ┌──────────────┐  ┌───────────────────┐│
│  │  对话界面     │  │  高德 JS API 地图  ││
│  └──────┬───────┘  └─────────┬─────────┘│
└─────────│───────────────────│──────────┘
          │ HTTP SSE / REST    │ AMap JS SDK
┌─────────▼────────────────────────────────┐
│           FastAPI  (agent_fastapi.py)    │
│  ┌────────────────────────────────────┐  │
│  │   LangGraph ReAct Agent           │  │
│  │   ┌──────────┐  ┌──────────────┐  │  │
│  │   │ DeepSeek │  │  Tool Nodes  │  │  │
│  │   │ Chat LLM │  │  (16 tools)  │  │  │
│  │   └──────────┘  └──────┬───────┘  │  │
│  └───────────────────────│───────────┘  │
└────────────────────────── │──────────────┘
                            │ REST
              ┌─────────────▼─────────────┐
              │    高德地图 REST API        │
              │  POI / 路线 / 天气 / Geocode│
              └───────────────────────────┘
```

- **后端**：Python 3.11 · FastAPI · LangGraph · LangChain
- **LLM**：DeepSeek Chat（通过 OpenAI 兼容接口）
- **地图**：高德地图 Web 服务 API（后端）+ JS API v2（前端）
- **包管理**：[uv](https://docs.astral.sh/uv/)

---

## 📦 目录结构

```
travel/
├── agent_fastapi.py              # FastAPI 服务入口（含 WebSocket 推送 + 三层记忆调度）
├── cli.py                        # 命令行交互入口
├── build_env.sh                  # 一键创建 uv 虚拟环境脚本
├── config.toml                   # ⚠️ 含 API Key，已加入 .gitignore，请勿提交
├── config.toml.example           # 配置模板，复制此文件并填写 Key
├── requirements.txt              # 依赖列表
│
├── prompts/                      # 所有 Prompt 模板（Markdown 格式，支持多语言）
│   └── tasks/
│       ├── instruction/          # Agent 系统提示词（zh / en）
│       ├── format_itinerary/     # 行程格式化 Prompt
│       ├── search_hotel/         # 酒店搜索 Prompt
│       ├── search_restaurant/    # 餐厅搜索 Prompt
│       └── fix_json/             # JSON 修复 Prompt
│
├── scripts/                      # 实用工具脚本
│   ├── build_city_adcode.py      # 构建城市 adcode 映射表
│   ├── validate_api_keys.py      # 验证所有 API Key 是否有效
│   └── test_memory.py            # 会话记忆功能测试
│
├── .storyline/                   # Skills 目录（可热加载，无需改代码）
│   └── skills/
│       ├── full_trip_planner/    # 完整旅行规划 Skill
│       │   └── SKILL.md
│       ├── hotel_recommender/    # 酒店推荐 Skill
│       │   └── SKILL.md
│       ├── rainy_day_alternative/# 雨天备选方案 Skill
│       │   └── SKILL.md
│       └── structured_planner/   # 结构化行程 Skill
│           └── SKILL.md
│
├── src/
│   └── travel_agent/
│       ├── agent.py              # Agent 构建 & 工具注册 & ClientContext（含三层记忆）
│       ├── config.py             # Pydantic 配置加载
│       ├── mcp/                  # MCP 服务层（将工具暴露给外部客户端）
│       │   ├── server.py         # MCP Server 启动入口
│       │   ├── register_tools.py # 工具注册到 MCP
│       │   └── hooks/
│       │       └── tool_interceptors.py  # 工具调用拦截器
│       ├── nodes/
│       │   ├── node_manager.py   # 节点生命周期管理
│       │   └── core_nodes/       # 14 个工具节点
│       │       ├── search_poi.py
│       │       ├── plan_itinerary.py
│       │       ├── smart_plan_itinerary.py
│       │       ├── plan_route.py
│       │       ├── search_hotel.py
│       │       ├── search_restaurant.py
│       │       ├── check_weather.py
│       │       ├── estimate_budget.py
│       │       ├── recommend_transport.py
│       │       ├── format_itinerary.py
│       │       ├── render_map.py
│       │       ├── render_itinerary.py
│       │       └── json_tools.py
│       ├── skills/
│       │   └── skills_io.py      # Skills 加载 & 热插拔逻辑
│       ├── storage/
│       │   ├── agent_memory.py   # L2：工具结果持久化 + context_snapshot 注入
│       │   ├── memory_compressor.py  # L1：消息滑动窗口 + LLM 摘要压缩
│       │   ├── user_profile.py   # L3：跨 session 用户偏好 / 历史摘要持久化
│       │   └── session_manager.py# 会话隔离 & 生命周期
│       └── utils/
│           ├── prompts.py        # Prompt 加载工具
│           └── logging.py
│
├── pic/                          # README 效果截图
└── web/
    ├── index.html                # 前端页面（高德 JSAPI Key 由后端动态注入）
    └── static/
        ├── app.js                # 地图交互 & 聊天逻辑
        └── style.css
```

---

## 🔄 工作流程与模块详解

### 整体请求流程

```
uv run uvicorn agent_fastapi:app
        │
        ├─ FastAPI lifespan 启动
        │   └─ asyncio.create_task(_run_mcp_server)
        │       └─ MCP Server 在后台启动（端口 8002）
        │
        ▼
WebSocket 连接，生成 session_id（UUID）
        ▼
build_agent()
  ├─ 1. 初始化 DeepSeekChatOpenAI（LLM）
  ├─ 2. MultiServerMCPClient 连接 MCP Server(:8002)
  │     └─ 请求头携带 X-Travel-Session-Id
  │     └─ tools = await client.get_tools()   ← 获取全部 16 个工具
  ├─ 3. load_skills()  ← 扫描 .storyline/skills/
  └─ 4. create_react_agent(llm, tools + skills, system_prompt)
        ▼
LangGraph ReAct 循环
  ┌─────────────────────────────────────────────┐
  │  LLM 推理 → 决定调用工具 → 通过 MCP Client 调用        │
  │  → MCP Server 执行 core_node 函数                      │
  │  → ArtifactStore.save_result() 持久化结果             │
  │  → 工具结果注入消息历史 → LLM 继续推理 → …           │
  └─────────────────────────────────────────────┘
        ▼
流式推送 token 到前端（SSE）→ 地图渲染 / 行程卡片
```

---

### 工具选择机制（LLM 自主决策）

本项目**不使用硬编码的 if-else 调度**，工具调用完全由 DeepSeek LLM 在 ReAct 循环中自主决定：

1. **工具来源**：`build_agent()` 通过 `MultiServerMCPClient` 连接本地 MCP Server，调用 `await client.get_tools()` 获取全部 16 个工具的 schema，注入 ReAct agent
2. **LLM 决策**：系统提示词（`prompts/tasks/instruction/zh/system.md`）告知 LLM 当前可用工具及调用规范
3. **ReAct 循环**：LLM 在每一步推理后输出 `tool_call`，LangGraph 通过 MCP Client 将调用转发给 MCP Server，Server 执行 core_node 函数、持久化结果并返回

```
用户：「帮我规划成都3天行程」
  → LLM: 调用 check_weather（先确认天气）
      → MCP Server 执行 check_weather_tool → ArtifactStore 持久化
  → LLM: 调用 search_poi（搜景点）
      → MCP Server 执行 search_poi_tool → ArtifactStore 持久化
  → LLM: 调用 smart_plan_itinerary（K-means 聚类按天分组）
  → LLM: 调用 render_map_pois（渲染地图标记）
  → LLM: 调用 render_itinerary（渲染行程卡片）
  → LLM: 输出最终文字说明
```

---

### Skills 加载与选择机制

Skills 是比工具更高层的**复合能力描述**，以 Markdown 文件定义，通过 `skillkit` 库加载：

```python
# agent.py
# 1. 从 MCP Server 获取 core_nodes 工具
client = MultiServerMCPClient(connections={...})
tools = await client.get_tools()              # 14 个 core_nodes

# 2. 扫描 .storyline/skills/ 加载 Skill 工具
skills_tools = await load_skills(skill_dir)   # Markdown 定义的 Skills

tools = tools + skills_tools                  # 合并注册给 LLM
```

- **发现时机**：每次 `build_agent()` 调用时扫描，**热插拔**：新增 `SKILL.md` 重启后自动生效，无需改代码
- **选择时机**：与 core_nodes 完全相同，由 LLM 根据描述自主决定调用哪个 Skill
- **Skill vs Tool**：core_nodes 是单一原子操作（搜索、查天气…），Skill 是一段自然语言描述的**工作流策略**（如「先查天气 → 再聚类 → 再格式化」），LLM 调用 Skill 后会按其描述编排多步工具调用

---

### Prompts 管理机制

```
prompts/tasks/<task>/<lang>/system.md   ← 系统提示词
prompts/tasks/<task>/<lang>/user.md     ← 用户侧模板（可选）
```

`PromptBuilder` 在运行时从文件加载 Markdown，支持 `{{variable}}` 占位符替换：

```python
builder.render(task="format_itinerary", role="system", lang="zh", days=3, city="成都")
```

- **按需缓存**：首次加载后缓存在内存，避免重复 IO
- **修改零成本**：直接编辑 `.md` 文件，重启服务即生效，不触碰 Python 代码

---

### 三层压缩记忆系统

项目实现了完整的**三层压缩记忆架构**，解决了长对话 token 膨胀、工具数据重复查询、跨会话用户偏好遗忘三大问题：

```
每轮对话
    │
    ▼
┌──────────────────────────────────────────────┐
│ L1  MemoryCompressor（memory_compressor.py） │
│  ─ 检查 messages 是否超出阈值                 │
│    （默认 40 条 或 6000 token 估算）          │
│  ─ 超出时调用 LLM 将早期消息压缩为一条摘要     │
│    SystemMessage，替换进 messages 头部        │
│  ─ LLM 失败时降级为截断策略（保留最近 10 条） │
│  ─ 摘要持久化到 <session_dir>/summary.json   │
└─────────────────────┬────────────────────────┘
                      │ 压缩后的纯对话历史
                      ▼
┌──────────────────────────────────────────────┐
│ L2  ArtifactStore.build_context_prompt()     │
│    （agent_memory.py）                        │
│  ─ 读取本 session 所有工具执行结果快照         │
│  ─ 排除纯渲染类工具（render_map 等）          │
│  ─ 每条 payload 截断至 600 字符              │
│  ─ 格式化为 Markdown，注入动态 system prompt  │
└─────────────────────┬────────────────────────┘
                      │ 含工具数据的 system prompt
                      ▼
┌──────────────────────────────────────────────┐
│ L3  UserProfileStore（user_profile.py）      │
│  ─ 跨 session 持久化用户偏好                  │
│    （城市 / 预算 / 节奏 / 人数 / 菜系偏好）   │
│  ─ 每轮结束后规则提取 HumanMessage 中的偏好   │
│  ─ session 断开时将 L1 摘要归档进用户历史     │
│  ─ 新 session 将偏好 + 近 2 条历史注入        │
│    system prompt 头部                         │
│  ─ 存储于 <data_dir>/user_profiles/          │
└──────────────────────────────────────────────┘
```

**关键设计**：`messages`（纯对话历史）与发给 `ainvoke` 的 `_invoke_input`（含动态 system prompt 的副本）严格分离，每轮从 `raw_messages` 回收时过滤动态 SystemMessage，避免动态 prompt 污染历史记录、导致 L1 摘要无限叠加。

#### L1 可调参数（`build_agent` 中修改）

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `max_messages` | `40` | 消息条数超出阈值时触发压缩 |
| `keep_recent` | `10` | 压缩时保留最近 N 条不参与摘要 |
| `max_tokens_estimate` | `6000` | token 估算值超出时也触发压缩 |

#### L2：工具结果持久化（ArtifactStore）

每次工具调用结束后，结果自动写入 `artifacts/` 目录，供下一轮对话直接引用：

```
artifacts/
└── <session_id>/
    ├── meta.json              # 本会话所有 artifact 的索引
    ├── search_poi/
    │   └── search_poi_<hash>.json
    ├── check_weather/
    │   └── check_weather_<hash>.json
    └── search_hotel/
        └── search_hotel_<hash>.json
```

`build_context_prompt()` 读取每个节点的最新结果，格式化后注入 system prompt，让 LLM 在后续轮次直接感知已收集的数据，无需重复调用 API。

#### L3：跨 session 用户画像

```
<data_dir>/user_profiles/default.json

{
  "preferred_cities": ["成都", "重庆"],
  "budget_level": "mid",
  "travel_pace": "relaxed",
  "group_size": 2,
  "cuisine_preferences": ["川菜", "火锅"],
  "session_summaries": [
    { "session_id": "...", "summary": "用户规划了成都3天行程...", "created_at": ... }
  ]
}
```

#### 会话隔离与清理（SessionLifecycleManager）

```python
mgr = SessionLifecycleManager(
    artifacts_root = "travel_outputs/",
    cache_root     = ".travel/.server_cache/",
    retention_days = 3,      # 3 天后自动清理
    max_sessions   = 256,    # 最多保留 256 个会话
)
```

每个 WebSocket 连接对应独立 `session_id`，不同用户数据完全隔离。

---

### MCP 服务层

MCP 服务在本项目中承担**双重角色**：

**① Agent 内部工具调用的统一通道**（与原项目架构对齐）

所有工具调用都经过 MCP Server，而不是由 Agent 直接 import core_nodes：

```
LangGraph ReAct
      │  tool_call
      ▼
MultiServerMCPClient（langchain-mcp-adapters）
      │  HTTP streamable-http + X-Travel-Session-Id
      ▼
FastMCP Server（端口 8002，由 FastAPI lifespan 在后台启动）
      │
      ├─ 从请求头提取 session_id
      ├─ 从 lifespan context 获取对应 ArtifactStore
      ├─ 调用 core_node 函数（search_poi_tool 等）
      ├─ ArtifactStore.save_result() 持久化
      └─ 返回结果给 Agent
```

**② 对外暴露工具给第三方 LLM 客户端**

Claude Desktop、Cursor 等 MCP 兼容客户端可直接连接 `http://127.0.0.1:8002/mcp`，使用所有旅行工具，无需额外开发。

```
src/travel_agent/mcp/
├── server.py              # FastMCP Server，lifespan 管理 SessionLifecycleManager
├── register_tools.py      # 注册全部 16 个工具（4 类：数据获取/行程规划/地图渲染/工具辅助）
└── hooks/
    └── tool_interceptors.py  # before/after 钩子：耗时统计、可扩展鉴权限流
```

---

## 🔌 MCP 服务

Agent 内置 **MCP（Model Context Protocol）服务层**，在本项目中承担双重职责：

**1. Agent 内部工具调用通道**：Agent 通过 `MultiServerMCPClient` 连接本地 MCP Server 获取工具，所有工具调用均经过 MCP 层，ArtifactStore 持久化统一在此完成。

**2. 对外暴露工具**：支持 Claude Desktop、Cursor 等 MCP 兼容客户端直接连接 `http://127.0.0.1:8002/mcp` 使用全部旅行工具。

**启动方式**：无需手动启动，`uvicorn agent_fastapi:app` 时由 FastAPI `lifespan` 自动在后台拉起 MCP Server：

```python
# agent_fastapi.py
@asynccontextmanager
async def lifespan(app):
    asyncio.create_task(_run_mcp_server(cfg))  # 后台启动 MCP Server（端口 8002）
    await asyncio.sleep(1.5)                   # 等待绑定完成
    yield
    # shutdown 时自动取消 task

app = FastAPI(lifespan=lifespan)
```

### 已注册工具（全部 16 个）

工具注册文件：`src/travel_agent/mcp/register_tools.py`，工具节点实现：`src/travel_agent/nodes/core_nodes/`

#### 🔍 数据获取类

| 工具名 | 功能 | 关键参数 |
|--------|------|---------|
| `search_poi` | 按关键词搜索城市内景点、酒店、餐厅等 POI，结果含坐标、评分、地址 | `city`、`keyword`、`types`（POI 类型）、`max_results`（默认 10） |
| `check_weather` | 查询城市实时天气或未来 3 天预报 | `city`、`forecast`（`true` 返回预报，`false` 返回实时） |
| `search_hotel` | 专用酒店搜索，支持价位档次筛选 | `city`、`keyword`、`budget_level`（`economy` / `mid` / `luxury`）、`max_results` |
| `search_restaurant` | 专用餐厅搜索，支持菜系关键词 | `city`、`keyword`（如"火锅"、"日料"）、`max_results` |

#### 🗓️ 行程规划类

| 工具名 | 功能 | 关键参数 |
|--------|------|---------|
| `plan_itinerary` | 简单均分版行程草案：将 POI 平均分配到各天 | `city`、`days`、`pois`（POI 列表）、`preference` |
| `smart_plan_itinerary` | **核心规划工具**：K-means 地理聚类 + 节奏控制，智能将景点/餐厅/酒店按天分组，同一天内行程地理位置相近 | `spots`、`hotels`、`restaurants`、`days`、`city`、`title`、`weather_summary`、`pace`（`relaxed` / `standard` / `intensive`） |
| `format_itinerary` | 调用 LLM 将规划结果转化为结构化 Markdown 每日行程报告，含时间段安排和贴心提示 | `city`、`days`、`travelers`、`budget`、`raw_data` |
| `estimate_budget` | 粗略估算旅行总花费（住宿/餐饮/门票/交通四项分类） | `days`、`city_level`（`A`/`B`/`C` 线城市）、`hotel_level`、`with_flight` |

#### 🗺️ 地图渲染类

| 工具名 | 功能 | 关键参数 |
|--------|------|---------|
| `render_map_pois` | 将 POI 列表打包为前端高德地图可渲染的标记点数据 | `items`（POI 列表）、`title`（图层标题） |
| `render_map_route` | 将驾车/步行路线折线编码打包为前端地图渲染数据 | `polyline`（编码折线）、`origin`、`destination`、`distance_km`、`duration_min` |
| `render_itinerary` | 将完整多日行程打包为地图有序标注数据（每天不同颜色标记） | `days`（分天 POI 列表）、`city`、`title` |

#### 🛣️ 路线与交通类

| 工具名 | 功能 | 关键参数 |
|--------|------|---------|
| `plan_route` | 调用高德路线规划 API，返回驾车距离、时长与折线坐标 | `origin`（起点名称）、`destination`（终点名称）、`city` |
| `recommend_transport` | 根据距离建议合适的交通方式（步行 / 骑行 / 地铁 / 打车 / 城际） | `distance_km`、`city` |

#### 🔧 工具辅助类

| 工具名 | 功能 | 关键参数 |
|--------|------|---------|
| `read_artifact` | 读取当前会话历史工具调用结果（避免重复调用 API） | `artifact_id` |
| `validate_json` | 检查字符串是否为合法 JSON，返回校验结果 | `payload` |
| `fix_json` | 调用 LLM 自动修复非法 JSON（处理 LLM 输出时的格式错误） | `raw_text`、`instruction`（可选修复要求） |

---

## 📝 Prompts 管理

所有 Prompt 以 **Markdown 文件**形式管理，支持中英文双语，运行时按 `lang` 参数动态加载，无需硬编码在代码里：

```
prompts/tasks/
├── instruction/       # Agent 全局系统提示词（规定工具调用顺序、多方案规则、地图渲染规范）
├── format_itinerary/  # 行程格式化：指导 LLM 生成结构化 Markdown 每日行程
├── search_hotel/      # 酒店搜索策略：价位档次判断、关键词构造规则
├── search_restaurant/ # 餐厅搜索策略：菜系识别、位置关联规则
└── fix_json/          # JSON 修复：非法 JSON 的 LLM 纠错指令
```

每个目录下含 `zh/system.md`（中文）和 `en/system.md`（英文），部分含 `user.md` 用户侧模板。

**`instruction/zh/system.md` 关键规范（Agent 全局行为约束）：**

系统提示词规定了 LLM 在规划旅行时的**标准 7 步工具调用顺序**：

```
1. search_poi          → 搜索景点（6~10 个候选）
2. check_weather       → 查询目的地天气
3. search_hotel        → 搜索酒店（3~5 家）
4. search_restaurant   → 搜索餐厅（4~6 家）
5. smart_plan_itinerary → K-means 聚类，将所有 POI 按天分组
6. render_itinerary    → 将分组结果渲染到前端地图
7. format_itinerary    → 生成 Markdown 格式行程报告
```

还规定了**多方案并列规则**（如同时给出轻松版和精华版行程）、**render 工具必须在 format 之前调用** 等约束，确保地图渲染和报告生成的顺序正确。

修改 Prompt 只需编辑对应 `.md` 文件，重启服务即可生效，无需触碰 Python 代码。

---

## 🧩 Skills 扩展

Skills 是以 **Markdown 文件**定义的可插拔能力包，放在 `.storyline/skills/` 目录下，Agent 启动时自动扫描加载，无需修改代码即可扩展新能力：

```
.storyline/skills/
├── full_trip_planner/        # 端到端完整旅行规划（5 步工作流）
│   └── SKILL.md
├── hotel_recommender/        # 智能酒店推荐（4 步工作流）
│   └── SKILL.md
├── rainy_day_alternative/    # 雨天备选室内行程（4 步工作流）
│   └── SKILL.md
└── structured_planner/       # 结构化 JSON 行程输出（3 步工作流）
    └── SKILL.md
```

### Skill 详细说明

#### `full_trip_planner` — 端到端旅行规划

> 触发场景：用户说"帮我规划 X 天行程"、"安排一次旅行"等完整规划请求

**5 步工作流：**

```
Step 1 需求确认   → 确认城市、天数、人数、偏好（美食/文化/自然）
Step 2 数据收集   → search_poi + check_weather + search_hotel + search_restaurant 并行采集
Step 3 智能分组   → smart_plan_itinerary（K-means 聚类按天分配，节奏控制）
Step 4 地图渲染   → render_itinerary（前端地图有序标注，每天不同颜色）
Step 5 生成报告   → format_itinerary（Markdown 每日行程 + 住宿/餐厅汇总表）
```

#### `hotel_recommender` — 智能酒店推荐

> 触发场景：用户问"推荐酒店"、"找个住的地方"等住宿相关请求

**4 步工作流：**

```
Step 1 收集需求   → 确认城市、入住时段、价位偏好
Step 2 搜索酒店   → search_hotel（含 budget_level 筛选）
Step 3 展示结果   → render_map_pois（在地图上标记酒店位置）
Step 4 用户反馈   → 收集意见，按需调整搜索关键词重试
```

#### `rainy_day_alternative` — 雨天备选室内行程

> 触发场景：用户询问"下雨怎么办"、"有没有室内景点"或天气预报含雨

**4 步工作流：**

```
Step 1 确认天气   → check_weather（验证是否确实有雨）
Step 2 梳理户外   → 从已有行程中标记受影响的户外景点
Step 3 搜室内资源 → search_poi（关键词：博物馆、商场、室内乐园、温泉）
Step 4 对比方案   → 并列输出原方案 vs 雨天备选方案，供用户选择
```

#### `structured_planner` — 结构化 JSON 行程输出

> 触发场景：用户需要机器可读的行程数据，或其他系统需要集成行程信息

**3 步工作流：**

```
Step 1 信息整合   → plan_itinerary（汇总已搜集的 POI 数据）
Step 2 JSON 转换  → 按预定 schema 输出 JSON（含每日时间段、POI 坐标、费用估算）
Step 3 格式校验   → validate_json + fix_json（确保输出合法，自动修复格式错误）
```

**添加新 Skill 的步骤：**
1. 在 `.storyline/skills/` 下新建目录（如 `budget_optimizer/`）
2. 创建 `SKILL.md`，用自然语言描述触发场景、工作流步骤、调用的工具链
3. 重启服务，Agent 自动识别并注册，无需修改任何 Python 代码

---

## 🛠️ 工具脚本（scripts/）

`scripts/` 目录提供三个独立运行的辅助脚本，用于环境验证、数据准备和功能调试：

### `validate_api_keys.py` — API Key 有效性验证

在首次配置或更换 Key 后，运行此脚本一键验证所有 API Key 是否能正常调用：

```bash
cd travel/
uv run python scripts/validate_api_keys.py [--config config.toml]
```

验证内容：
- **高德地图 Key**（`map.api_key`）：发起一次 POI 搜索请求（搜索"天安门"）
- **高德天气 Key**（`weather.api_key`）：发起一次天气查询请求（查询北京）
- **LLM API Key**（`llm.api_key`）：发起一次最小推理请求（`max_tokens=1`）

通过 ✅ / ❌ 符号直观展示每项结果，出错时附带具体的 HTTP 状态码和错误信息。

---

### `build_city_adcode.py` — 城市行政区编码数据库

批量调用高德地理编码 API，将预设的 38 个热门旅游城市解析为行政区编码（adcode）、省份、坐标等，并保存到 `resource/city_adcode.json`：

```bash
cd travel/
uv run python scripts/build_city_adcode.py [--config config.toml] [--output resource/city_adcode.json]
```

预置城市涵盖：北京、上海、成都、重庆、杭州、三亚、丽江、拉萨、桂林、敦煌等 38 个热门目的地。生成的 JSON 可供工具节点在 API 调用时精确匹配行政区，避免歧义城市名称问题。

---

### `test_memory.py` — 会话记忆功能测试

验证 `ArtifactStore` 和 `SessionLifecycleManager` 的完整功能链路：

```bash
cd travel/
uv run python scripts/test_memory.py
```

测试覆盖 8 个场景：

| 测试项 | 验证内容 |
|--------|---------|
| 创建 Session | `SessionLifecycleManager.new_session()` 返回合法 UUID |
| 写入工具结果 | `save_result()` 为 search_poi / check_weather / search_hotel 各写入一条 |
| 精确读取 | 按 `artifact_id` 读取，内容与写入一致 |
| 最新结果查询 | `get_latest_meta(node_id)` 返回每个节点最新的 artifact |
| context_snapshot | 打包全部节点最新结果为字典，模拟注入 LLM 上下文 |
| 覆写更新 | 同一节点二次写入后，`get_latest_meta` 正确返回最新 artifact |
| 磁盘持久化 | 验证 `meta.json` 和各 POI JSON 文件确实写入磁盘 |
| 跨 Session 隔离 | 新建第二个 Session，其 snapshot 为空，不受第一个 Session 污染 |

---

## 🧠 Memory & Storage

Agent 实现了**三层压缩记忆系统**，完整覆盖短期压缩、中期工具感知和长期偏好持久化三个维度。

### L1：消息滑动窗口压缩（MemoryCompressor）

`src/travel_agent/storage/memory_compressor.py`

长对话时，messages 列表超出阈值后自动调用 LLM 生成摘要，将早期对话压缩为一条 SystemMessage 保留在上下文头部，近期消息完整保留：

```
压缩前：[SysMsg] [Human] [AI] [Tool] × N 轮 ...（超出 40 条）
                              ↓ LLM 摘要
压缩后：[SysMsg] [摘要SysMsg] [最近 10 条消息]
```

摘要同步持久化到 `<session_dir>/summary.json`，LLM 故障时自动降级为截断策略。

### L2：工具结果 Snapshot 注入（ArtifactStore）

`src/travel_agent/storage/agent_memory.py`

每次工具调用后，结果写入本地 JSON 文件。新增 `build_context_prompt()` 方法，在每轮对话开始前读取本 session 所有工具的最新结果，格式化后注入动态 system prompt：

```
artifacts/
└── <session_id>/
    ├── meta.json
    ├── search_poi/search_poi_<hash>.json
    ├── check_weather/check_weather_<hash>.json
    └── search_hotel/search_hotel_<hash>.json
```

LLM 在每轮开始时即可感知"本次已查过成都天气、已搜过 8 个景点"，无需重复调用 API。

### L3：跨 Session 用户偏好（UserProfileStore）

`src/travel_agent/storage/user_profile.py`

自动从对话中提取用户偏好（城市、预算、节奏、人数、菜系等），持久化到本地 JSON，每次新 session 开始时自动注入 system prompt：

```json
{
  "preferred_cities": ["成都", "重庆"],
  "budget_level": "mid",
  "travel_pace": "relaxed",
  "group_size": 2,
  "cuisine_preferences": ["川菜", "火锅"],
  "session_summaries": [...]
}
```

### SessionLifecycleManager — 会话生命周期

`src/travel_agent/storage/session_manager.py`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `retention_days` | 3 | 超过此天数的历史会话自动清理 |
| `max_sessions` | 256 | 最多保留会话数，超出时删除最旧的 |
| `enable_cleanup` | True | 是否启用自动过期清理 |

每个 HTTP 连接对应独立的 `session_id`（UUID），会话间数据完全隔离。

---

## 🚀 快速开始

### 前置条件

- Python **3.11+**
- [uv](https://docs.astral.sh/uv/) 包管理器（`pip install uv` 或 `brew install uv`）
- [DeepSeek 平台](https://platform.deepseek.com/) API Key
- [高德开放平台](https://lbs.amap.com/) 应用（需创建两种 Key，见下文）

---

### 1. 申请 API Key

**DeepSeek**：前往 [platform.deepseek.com](https://platform.deepseek.com/) → API Keys → 创建。

**高德地图**（需两个不同类型的 Key）：

1. 登录 [高德开放平台控制台](https://console.amap.com/dev/key/app)
2. 创建应用，添加 **Web服务** 类型 Key → 用于后端 REST 接口（POI 搜索 / 路线规划 / 天气）
3. 在同一应用下添加 **Web端（JS API）** 类型 Key → 用于前端地图渲染

---

### 2. 配置文件

```bash
cp config.toml.example config.toml
```

编辑 `config.toml`，填入你的 Key：

```toml
[llm]
api_key = "sk-xxxxxxxxxxxxxxxxxxxx"   # DeepSeek API Key

[map]
api_key = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # 高德 Web服务 Key
jsapi_key = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # 高德 JS API Key

[weather]
api_key = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # 同 map.api_key（共用 Web服务 Key）
```

> 💡 `jsapi_key` 会由后端在返回页面时自动注入，无需手动修改 `web/index.html`。

---

### 3. 安装依赖

```bash
uv venv .venv
uv pip install -r requirements.txt
```

---

### 4. 启动服务

```bash
uv run uvicorn agent_fastapi:app --host 127.0.0.1 --port 8000 --reload
```

打开浏览器访问 **[http://localhost:8000](http://localhost:8000)**，即可开始对话规划行程。

---

## 💡 使用示例

```
帮我规划一个成都 3 天 2 晚的旅行，预算 2000 元，喜欢美食和历史文化
```

```
从宽窄巷子到武侯祠怎么走？步行需要多久？
```

```
帮我查查明天成都的天气，顺便推荐几家附近的特色火锅
```

---

## ⚙️ CLI 模式

不启动 Web 服务时，也可以直接命令行对话：

```bash
uv run python cli.py
```

---

## 📝 License

MIT License
