from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - 兼容低版本
    import tomli as tomllib

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


def _resolve_relative_path(v: Path, info: ValidationInfo) -> Path:
    """
    相对路径统一以 config.toml 所在目录为基准，而不是当前工作目录。
    """
    ctx = info.context or {}
    base = ctx.get("config_dir")
    if not base:
        return v
    base = Path(base).expanduser()
    v2 = v.expanduser()
    if v2.is_absolute():
        return v2
    return (base / v2).resolve()


def _resolve_paths_recursively(value: Any, info: ValidationInfo) -> Any:
    if value is None:
        return None
    if isinstance(value, Path):
        return _resolve_relative_path(value, info)
    if isinstance(value, list):
        return [_resolve_paths_recursively(v, info) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_paths_recursively(v, info) for k, v in value.items()}
    return value


class ConfigBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _resolve_all_path_fields(cls, v: Any, info: ValidationInfo) -> Any:
        return _resolve_paths_recursively(v, info)


class DeveloperConfig(ConfigBaseModel):
    developer_mode: bool = False
    default_llm: str = "deepseek-chat"


class ProjectConfig(ConfigBaseModel):
    data_dir: Path = Field(..., description="用户上传的旅行数据（偏好、收藏）存放目录")
    outputs_dir: Path = Field(..., description="生成行程方案、导出文件存放目录")


class LLMConfig(ConfigBaseModel):
    model: str
    base_url: str
    api_key: str
    timeout: float = 30.0


class MapConfig(ConfigBaseModel):
    provider: str = "amap"
    api_key: str = Field(..., description="高德地图 Web 服务 Key（后端 REST 调用）")
    jsapi_key: Optional[str] = Field(None, description="高德 Web端 JS API Key（前端地图 SDK）")
    base_url: str = "https://restapi.amap.com"


class WeatherConfig(ConfigBaseModel):
    provider: str = "amap"
    base_url: str = "https://restapi.amap.com"
    api_key: str = Field(..., description="高德天气查询 Key（可与地图共用）")


class McpServerConfig(ConfigBaseModel):
    server_name: str = "travel"
    server_cache_dir: Path = Path(".travel/.server_cache")
    server_transport: str = "streamable-http"
    url_scheme: str = "http"
    connect_host: str = "127.0.0.1"
    port: int = 8002
    path: str = "/mcp"
    json_response: bool = True
    stateless_http: bool = False
    timeout: int = 300


class Settings(ConfigBaseModel):
    developer: DeveloperConfig
    project: ProjectConfig
    llm: LLMConfig
    map: MapConfig
    weather: WeatherConfig
    mcp_server: McpServerConfig = Field(default_factory=McpServerConfig)


def load_settings(config_path: str | Path) -> Settings:
    p = Path(config_path).expanduser().resolve()
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return Settings.model_validate(data, context={"config_dir": p.parent})


def default_config_path() -> str:
    """
    允许通过环境变量 TRAVEL_AGENT_CONFIG 覆盖默认配置文件路径。
    默认路径相对于本文件位置计算，与启动时的工作目录无关。
    config.py 位于 travel/src/travel_agent/config.py
    config.toml 位于 travel/config.toml
    """
    import os
    from pathlib import Path

    env_val = os.getenv("TRAVEL_AGENT_CONFIG")
    if env_val:
        return env_val
    # 锚定到文件位置：config.py → travel/src/travel_agent/ → travel/src/ → travel/
    return str(Path(__file__).resolve().parent.parent.parent / "config.toml")

