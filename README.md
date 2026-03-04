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
| 📋 **行程渲染** | 可视化每日行程卡片 |
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
    ├── index.html                # 前端页面（⚠️ 需填写 jsapi_key）
    └── static/
        ├── app.js                # 地图交互 & 聊天逻辑
        └── style.css
```

---

## 🔌 MCP 服务

Agent 内置 **MCP（Model Context Protocol）服务层**，可将所有工具节点暴露为标准 MCP 接口，支持 Claude Desktop、Cursor 等任意 MCP 兼容客户端直接调用旅行工具。

```
src/travel_agent/mcp/
├── server.py              # MCP Server，基于 SSE 传输
├── register_tools.py      # 将 core_nodes 工具批量注册到 MCP
└── hooks/
    └── tool_interceptors.py  # 拦截器：请求鉴权、日志、限流等
```

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

> ⚠️ **还需要**：打开 `web/index.html`，将 `<script src>` 标签中的 `YOUR_AMAP_JSAPI_KEY` 替换为你的 JS API Key：
> ```html
> src="https://webapi.amap.com/maps?v=2.0&key=你的jsapi_key"
> ```

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
