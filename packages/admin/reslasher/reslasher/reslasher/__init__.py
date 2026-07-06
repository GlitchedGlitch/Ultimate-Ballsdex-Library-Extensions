from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.reslasher")


async def setup(bot: "BallsDexBot") -> None:
    from .cog import ReSlasherCog, _walk_commands, sync_registry
    
    cog = ReSlasherCog(bot)
    await bot.add_cog(cog)
    
    if bot.is_ready():
        commands_list = _walk_commands(bot.tree)
        created = await sync_registry(commands_list)
        log.info("ReSlasher: eagerly synced %d commands (%d new)", len(commands_list), created)
        cog._patch_sync()
    
    log.info("ReSlasherCog loaded")


async def teardown(bot: "BallsDexBot") -> None:
    pass
