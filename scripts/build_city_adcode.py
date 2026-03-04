#!/usr/bin/env python3
"""
travel/scripts/build_city_adcode.py

Offline script: geocode a list of common Chinese cities via AMap API
and save the results to resource/city_adcode.json.

Usage:
    cd travel/
    python scripts/build_city_adcode.py [--config config.toml] [--output resource/city_adcode.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

# ── default city list ──────────────────────────────────────────────────────
DEFAULT_CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "南京",
    "西安", "武汉", "长沙", "厦门", "青岛", "大连", "苏州", "天津",
    "哈尔滨", "沈阳", "济南", "郑州", "合肥", "福州", "昆明", "贵阳",
    "南宁", "乌鲁木齐", "兰州", "银川", "西宁", "呼和浩特", "海口",
    "三亚", "桂林", "丽江", "拉萨", "张家界", "黄山", "九寨沟", "敦煌",
]


async def geocode_city(city: str, api_key: str, base_url: str) -> dict | None:
    url = f"{base_url}/v3/geocode/geo"
    params = {"key": api_key, "address": city, "output": "json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") == "1" and data.get("geocodes"):
            g = data["geocodes"][0]
            loc = g.get("location", "")
            lng, lat = (None, None)
            if loc and "," in loc:
                try:
                    lng, lat = (float(v) for v in loc.split(",", 1))
                except ValueError:
                    pass
            return {
                "name": city,
                "adcode": g.get("adcode"),
                "province": g.get("province"),
                "citycode": g.get("citycode"),
                "location": loc,
                "longitude": lng,
                "latitude": lat,
            }
    except Exception as exc:
        print(f"  [WARN] {city}: {exc}", file=sys.stderr)
    return None


async def main(config_path: str, output_path: str) -> None:
    # Load config
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from travel_agent.config import load_settings
        cfg = load_settings(config_path)
        api_key = cfg.map.api_key
        base_url = cfg.map.base_url.rstrip("/")
    except Exception as exc:
        print(f"[ERROR] Failed to load config: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Geocoding {len(DEFAULT_CITIES)} cities …")
    results = {}
    for city in DEFAULT_CITIES:
        record = await geocode_city(city, api_key, base_url)
        if record:
            results[city] = record
            print(f"  ✓ {city} → adcode={record['adcode']}")
        else:
            print(f"  ✗ {city} (skipped)")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[INFO] Saved {len(results)} records → {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build city → adcode mapping JSON")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent.parent / "config.toml"),
        help="Path to config.toml",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "resource" / "city_adcode.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()
    asyncio.run(main(args.config, args.output))
