from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from .cog import ReSlasherCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.reslasher")


async def setup(bot: "BallsDexBot") -> None:
    await bot.add_cog(ReSlasherCog(bot))
    log.info("ReSlasherCog loaded")


async def teardown(bot: "BallsDexBot") -> None:
    pass
