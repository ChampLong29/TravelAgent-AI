import aiofiles
from pathlib import Path
from skillkit import SkillManager
from skillkit.integrations.langchain import create_langchain_tools

async def load_skills(
    skill_dir: str = ".storyline/skills"
):
    # Discover skills
    manager = SkillManager(skill_dir=skill_dir)
    await manager.adiscover()

    # Convert to LangChain tools
    tools = create_langchain_tools(manager)
    return tools
