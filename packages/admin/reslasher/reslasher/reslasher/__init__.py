from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.reslasher")


async def setup(bot: "BallsDexBot") -> None:
    from .cog import ReSlasherCog, sync_registry
    
    cog = ReSlasherCog(bot)
    await bot.add_cog(cog)
    
    if bot.is_ready():
        await cog.apply_database_overrides()
        created = await sync_registry(bot.tree)
        log.info("ReSlasher: eagerly synced registry (%d new)", created)
        cog._patch_sync()
    
    log.info("ReSlasherCog loaded")


async def teardown(bot: "BallsDexBot") -> None:
    pass
