from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from .cog import CollectorCog
from .admin import collector as collector_admin_group

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")


async def setup(bot: "BallsDexBot") -> None:
    await bot.add_cog(CollectorCog(bot))
    log.info("CollectorCog loaded")

    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        admin_cog.admin.add_command(collector_admin_group)
        log.info("Attached /admin collector to Admin cog")
    else:
        log.warning(
            "Admin cog not found — /admin collector commands will not be registered. "
            "Ensure the admin package loads before collector."
        )


async def teardown(bot: "BallsDexBot") -> None:
    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        admin_cog.admin.remove_command("collector")
