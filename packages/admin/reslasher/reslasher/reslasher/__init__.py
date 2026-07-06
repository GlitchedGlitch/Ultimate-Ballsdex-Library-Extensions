from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.reslasher")


async def setup(bot: "BallsDexBot") -> None:
    from .cog import ReSlasherCog, _collect_leaf_commands, sync_registry
    
    cog = ReSlasherCog(bot)
    await bot.add_cog(cog)
    
    if bot.is_ready():
        leaf_commands = _collect_leaf_commands(bot)
        created = await sync_registry(leaf_commands)
        log.info("ReSlasher: eagerly synced %d commands (%d new)", len(leaf_commands), created)
    
    log.info("ReSlasherCog loaded")


async def teardown(bot: "BallsDexBot") -> None:
    pass
