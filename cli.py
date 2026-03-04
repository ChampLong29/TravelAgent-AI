import asyncio
import os
import sys
import time
import uuid

from langchain_core.messages import HumanMessage

ROOT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from travel_agent.agent import build_agent  # noqa: E402
from travel_agent.config import load_settings  # noqa: E402
from travel_agent.utils.logging import logger  # noqa: E402

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")


async def main():
    session_id = f"travel_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    cfg = load_settings(CONFIG_PATH)

    agent, context = await build_agent(cfg=cfg, session_id=session_id, lang="zh")

    print("智能旅行助手 v0.1")
    print("请输入你的旅行需求，输入 /exit 退出。")

    messages = []

    while True:
        try:
            user_input = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见～")
            break

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            print("\n再见～")
            break

        messages.append(HumanMessage(content=user_input))

        try:
            result = await agent.ainvoke({"messages": messages}, config={" configurable": {"session_id": session_id}})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent 调用失败: %s", exc)
            print("助手：出错了，请检查后端日志。")
            continue

        messages = result["messages"]
        final_text = None
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                break
            # 最后一条非 HumanMessage 视为模型输出
            final_text = getattr(m, "content", None)
            if final_text:
                break

        print(f"\n助手：{final_text or '(没有生成回复)'}\n")


if __name__ == "__main__":
    asyncio.run(main())

