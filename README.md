# 🗺️ Travel Agent — AI 旅行规划助手

基于 **LangGraph ReAct** 架构的多工具旅行规划 Agent，集成高德地图 API，支持自然语言对话式行程规划、POI 搜索、路线规划、天气查询、预算估算，并在前端实时渲染交互地图。

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
| 🧠 **会话记忆** | 多轮对话跨会话记忆，工具调用结果持久化到 artifacts |

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
│  │   │ Chat LLM │  │  (14 tools)  │  │  │
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
├── agent_fastapi.py              # FastAPI 服务入口（含 SSE 流式推送）
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
│       ├── agent.py              # Agent 构建 & 工具注册
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
│       │   ├── agent_memory.py   # 多轮对话记忆管理
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
  │     └─ tools = await client.get_tools()   ← 获取全部 14 个工具
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

1. **工具来源**：`build_agent()` 通过 `MultiServerMCPClient` 连接本地 MCP Server，调用 `await client.get_tools()` 获取全部 14 个工具的 schema，注入 ReAct agent
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

### 记忆功能实现

项目实现了两层记忆：

#### 层 1：对话上下文记忆（LangGraph 消息历史）

LangGraph ReAct agent 维护完整的 `messages` 列表，包含每轮的 `HumanMessage`、`AIMessage`、`ToolMessage`。`agent_fastapi.py` 在每次请求时将历史消息传入，LLM 可感知整个对话上下文：

```python
# agent_fastapi.py
_clean_messages_for_next_turn(messages)   # 将 list/dict content 序列化为 string
                                           # （DeepSeek API 要求 content 必须是 string）
await agent.ainvoke({"messages": messages})
```

#### 层 2：工具结果持久化（ArtifactStore）

每次工具调用结束后，结果写入本地文件，形成跨请求的持久记忆：

```
调用 search_poi("成都", "武侯祠")
        │
        ▼
ArtifactStore.save_result(
    node_id    = "search_poi",
    payload    = { POI 列表 },
    summary    = "POI 搜索: 武侯祠 @ 成都",
)
        │
        ▼
artifacts/<session_id>/search_poi/search_poi_3588b6d6.json
artifacts/<session_id>/meta.json  ← 追加索引记录
```

`context_snapshot()` 方法可将当前会话所有工具的最新结果打包为一个字典，注入到 LLM 提示词或 MCP 响应中，使 LLM 在后续轮次中感知已有数据而无需重复 API 调用。

#### 会话隔离与清理（SessionLifecycleManager）

```python
mgr = SessionLifecycleManager(
    artifacts_root = "travel_outputs/",
    cache_root     = ".storyline/.server_cache/",
    retention_days = 3,      # 3 天后自动清理
    max_sessions   = 256,    # 最多保留 256 个会话
)

store = mgr.get_store(session_id)    # 取或创建当前会话的 ArtifactStore
mgr.cleanup_expired()                # 删除过期目录（超时 or 超数量）
```

每个 WebSocket 连接对应独立 `session_id`，不同用户的 artifacts 目录完全隔离。

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
├── register_tools.py      # 注册全部 14 个工具（含之前缺失的 8 个）
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

**已注册工具（全部 14 个）**：

| 工具 | 说明 |
|------|------|
| `search_poi` | POI 搜索 |
| `search_hotel` | 酒店搜索 |
| `search_restaurant` | 餐厅搜索 |
| `check_weather` | 天气查询 |
| `plan_route` | 路线规划 |
| `plan_itinerary` | 行程草案生成 |
| `smart_plan_itinerary` | K-means 智能行程分组 |
| `format_itinerary` | LLM 行程报告生成 |
| `estimate_budget` | 预算估算 |
| `recommend_transport` | 交通建议 |
| `render_map_pois` | 地图 POI 渲染 |
| `render_map_route` | 地图路线渲染 |
| `render_itinerary` | 地图行程渲染 |
| `validate_json` / `fix_json` | JSON 校验与修复 |
| `read_artifact` | 读取历史工具结果 |

---

## 📝 Prompts 管理

所有 Prompt 以 **Markdown 文件**形式管理，支持中英文双语，运行时按 `lang` 参数动态加载，无需硬编码在代码里：

```
prompts/tasks/
├── instruction/      # Agent 全局系统提示词
├── format_itinerary/ # 行程格式化指令
├── search_hotel/     # 酒店搜索指令
├── search_restaurant/# 餐厅搜索指令
└── fix_json/         # JSON 自动修复指令
```

修改 Prompt 只需编辑对应 `.md` 文件，重启服务即可生效，无需触碰 Python 代码。

---

## 🧩 Skills 扩展

Skills 是以 **Markdown 文件**定义的可插拔能力包，放在 `.storyline/skills/` 目录下，Agent 启动时自动扫描加载，无需修改代码即可扩展新能力：

```
.storyline/skills/
├── full_trip_planner/        # 一句话生成完整多日行程
│   └── SKILL.md
├── hotel_recommender/        # 智能酒店推荐策略
│   └── SKILL.md
├── rainy_day_alternative/    # 雨天备选景点方案
│   └── SKILL.md
└── structured_planner/       # 结构化行程输出格式
    └── SKILL.md
```

**添加新 Skill 的步骤：**
1. 在 `.storyline/skills/` 下新建目录
2. 创建 `SKILL.md`，用自然语言描述能力与调用方式
3. 重启服务，Agent 自动识别并注册

---

## 🧠 Memory & Storage

Agent 具备**跨多轮对话的工具结果记忆**能力，所有工具调用结果以 JSON 文件持久化到本地，避免重复调用 API。

### ArtifactStore — 工具结果持久化

每次工具调用结束后，结果自动写入 `artifacts/` 目录：

```
artifacts/
└── <session_id>/
    ├── meta.json              # 本会话所有 artifact 的索引（node_id / 摘要 / 时间戳）
    ├── search_poi/
    │   └── search_poi_<hash>.json
    ├── check_weather/
    │   └── check_weather_<hash>.json
    └── search_hotel/
        └── search_hotel_<hash>.json
```

- 同一会话内，Agent 可直接从 `ArtifactStore` 读取已有结果，**无需重复调用高德 API**
- `meta.json` 记录每条结果的 `node_id`、`summary`、`created_at`，便于快速检索

### SessionLifecycleManager — 会话生命周期

`SessionLifecycleManager` 统一管理多用户并发场景下的会话隔离：

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
