"""
scripts/test_memory.py

快速验证 ArtifactStore 记忆功能是否正常工作。
用法：
    cd travel/
    uv run python scripts/test_memory.py
"""
from __future__ import annotations

import asyncio
import json
import time
import sys
from pathlib import Path

# 把 travel/src 加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from travel_agent.storage.agent_memory import ArtifactStore
from travel_agent.storage.session_manager import SessionLifecycleManager

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
CACHE_DIR     = Path(__file__).resolve().parent.parent / "cache"


def sep(title: str):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


async def main():
    # ── 1. 创建 session ──────────────────────────────────────
    sep("1. 创建 Session")
    sm = SessionLifecycleManager(artifacts_root=ARTIFACTS_DIR, cache_root=CACHE_DIR)
    session_id = sm.new_session()
    print(f"  session_id = {session_id}")
    store = sm.get_store(session_id)

    # ── 2. 模拟搜索结果写入 ───────────────────────────────────
    sep("2. 写入模拟工具结果（search_poi / check_weather / search_hotel）")

    meta_poi = store.save_result(
        node_id="search_poi",
        payload=[
            {"name": "宽窄巷子", "longitude": 104.0618, "latitude": 30.6710,
             "rating": "4.8", "address": "青羊区"},
            {"name": "武侯祠", "longitude": 104.0483, "latitude": 30.6394,
             "rating": "4.9", "address": "武侯区"},
        ],
        summary="成都景点搜索结果（2条）",
    )
    print(f"  ✅ search_poi   → {meta_poi.artifact_id}")

    meta_weather = store.save_result(
        node_id="check_weather",
        payload={"city": "成都", "days": [
            {"date": "2026-03-05", "weather": "多云", "temp_low": "12", "temp_high": "18"},
            {"date": "2026-03-06", "weather": "晴", "temp_low": "10", "temp_high": "20"},
        ]},
        summary="成都未来2天天气",
    )
    print(f"  ✅ check_weather → {meta_weather.artifact_id}")

    time.sleep(0.01)  # 确保时间戳不同

    meta_hotel = store.save_result(
        node_id="search_hotel",
        payload=[
            {"name": "成都锦江宾馆", "rating": "4.7", "cost": "600",
             "address": "人民南路二段"},
        ],
        summary="成都酒店搜索结果（1条）",
    )
    print(f"  ✅ search_hotel  → {meta_hotel.artifact_id}")

    # ── 3. 按 artifact_id 精确读取 ────────────────────────────
    sep("3. 按 artifact_id 精确读取")
    _, data = store.load_result(meta_poi.artifact_id)
    pois = data["payload"]
    print(f"  search_poi payload: {[p['name'] for p in pois]}")
    assert pois[0]["name"] == "宽窄巷子", "POI 读取失败"
    print("  ✅ 精确读取 OK")

    # ── 4. 读取某 node 最新结果 ────────────────────────────────
    sep("4. 获取各 node 的最新 artifact")
    for node in ("search_poi", "check_weather", "search_hotel"):
        latest = store.get_latest_meta(node)
        print(f"  {node:20s} → latest: {latest.artifact_id}  summary: {latest.summary}")
    print("  ✅ get_latest_meta OK")

    # ── 5. context_snapshot（注入 LLM 的完整快照）────────────
    sep("5. context_snapshot（模拟注入 LLM）")
    snapshot = store.context_snapshot()
    for node_id, v in snapshot.items():
        print(f"  [{node_id}]  artifact_id={v['artifact_id']}  summary={v['summary']}")
    assert "search_poi" in snapshot
    assert "check_weather" in snapshot
    assert "search_hotel" in snapshot
    print("  ✅ context_snapshot 包含全部 3 个 node")

    # ── 6. 覆写同 node（新结果应覆盖 latest）──────────────────
    sep("6. 同一 node 多次写入，latest 应返回最新的")
    time.sleep(0.02)
    meta_poi2 = store.save_result(
        node_id="search_poi",
        payload=[{"name": "天府广场", "longitude": 104.0657, "latitude": 30.6598}],
        summary="成都景点搜索结果（更新）",
    )
    latest_poi = store.get_latest_meta("search_poi")
    print(f"  第二次 artifact_id: {meta_poi2.artifact_id}")
    print(f"  get_latest_meta  : {latest_poi.artifact_id}")
    assert latest_poi.artifact_id == meta_poi2.artifact_id, "latest 未更新为最新 artifact!"
    print("  ✅ latest 正确指向最新 artifact")

    # ── 7. 验证持久化（文件存在）────────────────────────────────
    sep("7. 验证磁盘文件持久化")
    meta_path = ARTIFACTS_DIR / session_id / "meta.json"
    poi_file  = Path(meta_poi.path)
    print(f"  meta.json 存在: {meta_path.exists()}")
    print(f"  POI json 存在 : {poi_file.exists()}")
    with meta_path.open() as f:
        all_metas = json.load(f)
    print(f"  meta.json 中共 {len(all_metas)} 条记录")
    assert meta_path.exists() and poi_file.exists()
    print("  ✅ 磁盘持久化 OK")

    # ── 8. 跨 session 隔离 ────────────────────────────────────
    sep("8. 跨 Session 隔离（不同 session_id 看不到对方的数据）")
    session_id_2 = sm.new_session()
    store2 = sm.get_store(session_id_2)
    snapshot2 = store2.context_snapshot()
    print(f"  Session 2 snapshot 条数: {len(snapshot2)}（应为 0）")
    assert len(snapshot2) == 0, "跨 session 隔离失败！"
    print("  ✅ 跨 session 隔离 OK")

    # ── 总结 ──────────────────────────────────────────────────
    sep("✅ 所有记忆功能测试通过！")
    print(f"  artifacts 目录: {ARTIFACTS_DIR / session_id}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
