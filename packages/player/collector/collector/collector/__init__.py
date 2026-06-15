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
        try:
            existing = admin_cog.admin.app_command.get_command("collector")
            if existing is not None:
                admin_cog.admin.app_command.remove_command("collector")
            admin_cog.admin.app_command.add_command(
                collector_admin_group.app_command
            )
            log.info("Attached /admin collector to Admin cog")
        except Exception:
            log.warning("Failed to attach /admin collector", exc_info=True)
    else:
        log.warning(
            "Admin cog not found — /admin collector commands will not be registered."
        )


async def teardown(bot: "BallsDexBot") -> None:
    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            admin_cog.admin.app_command.remove_command("collector")
        except Exception:
            pass
