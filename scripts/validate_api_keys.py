#!/usr/bin/env python3
"""
travel/scripts/validate_api_keys.py

Offline validation script: tests all API keys in config.toml to ensure
they are working before starting the travel agent.

Usage:
    cd travel/
    python scripts/validate_api_keys.py [--config config.toml]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "


async def _test_amap_key(api_key: str, base_url: str) -> tuple[bool, str]:
    """Test AMap key by geocoding a known city."""
    import httpx
    url = f"{base_url}/v3/geocode/geo"
    params = {"key": api_key, "address": "北京", "output": "json"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
        status = data.get("status")
        info = data.get("info", "")
        if status == "1":
            return True, "OK"
        return False, f"status={status}, info={info}"
    except Exception as exc:
        return False, str(exc)


async def _test_llm_key(model: str, base_url: str, api_key: str) -> tuple[bool, str]:
    """Test LLM key with a minimal chat request."""
    import httpx
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=body, headers=headers)
        if resp.status_code == 200:
            return True, "OK"
        return False, f"HTTP {resp.status_code}: {resp.text[:120]}"
    except Exception as exc:
        return False, str(exc)


async def main(config_path: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    try:
        from travel_agent.config import load_settings
        cfg = load_settings(config_path)
    except Exception as exc:
        print(f"{FAIL} Failed to load config: {exc}")
        sys.exit(1)

    print(f"Config: {config_path}\n")
    all_passed = True

    # ── AMap Map key ─────────────────────────────────────────────────────
    print("Testing AMap (Map) key …")
    ok, msg = await _test_amap_key(cfg.map.api_key, cfg.map.base_url)
    sym = PASS if ok else FAIL
    print(f"  {sym} Map key: {msg}")
    if not ok:
        all_passed = False

    # ── AMap Weather key ─────────────────────────────────────────────────
    if cfg.weather.api_key != cfg.map.api_key:
        print("Testing AMap (Weather) key …")
        ok, msg = await _test_amap_key(cfg.weather.api_key, cfg.weather.base_url)
        sym = PASS if ok else FAIL
        print(f"  {sym} Weather key: {msg}")
        if not ok:
            all_passed = False
    else:
        print(f"  {PASS} Weather key: same as Map key (skipped)")

    # ── LLM key ──────────────────────────────────────────────────────────
    print("Testing LLM key …")
    ok, msg = await _test_llm_key(cfg.llm.model, cfg.llm.base_url, cfg.llm.api_key)
    sym = PASS if ok else FAIL
    print(f"  {sym} LLM ({cfg.llm.model}): {msg}")
    if not ok:
        all_passed = False

    print()
    if all_passed:
        print(f"{PASS} All API keys are valid.")
    else:
        print(f"{FAIL} Some API keys failed. Please check your config.toml.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate all API keys in config.toml")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent.parent / "config.toml"),
        help="Path to config.toml",
    )
    args = parser.parse_args()
    asyncio.run(main(args.config))
