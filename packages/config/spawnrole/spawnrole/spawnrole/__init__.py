from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from .cog import SpawnRoleCog
from . import spawn_patch

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.spawnrole")


async def setup(bot: "BallsDexBot") -> None:
    spawn_patch.apply()
    cog = SpawnRoleCog(bot)
    await bot.add_cog(cog)
    log.info("SpawnRoleCog loaded")


async def teardown(bot: "BallsDexBot") -> None:
    spawn_patch.revert()
    cog = bot.cogs.get("SpawnRoleCog")
    if cog is not None and hasattr(cog, "_detach"):
        cog._detach()
      
