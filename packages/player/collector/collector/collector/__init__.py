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
            existing_prefix = admin_cog.admin.all_commands.get("collector")
            if existing_prefix is not None:
                admin_cog.admin.remove_command("collector")
            admin_cog.admin.add_command(collector_admin_group)
            log.info("Registered c.admin collector prefix command")

            existing_slash = admin_cog.admin.app_command.get_command("collector")
            if existing_slash is not None:
                admin_cog.admin.app_command.remove_command("collector")
            admin_cog.admin.app_command.add_command(
                collector_admin_group.app_command
            )
            log.info("Registered /admin collector slash command")

        except Exception:
            log.warning("Failed to attach collector admin commands", exc_info=True)
    else:
        log.warning(
            "Admin cog not found — c.admin collector commands will not be registered."
        )


async def teardown(bot: "BallsDexBot") -> None:
    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            admin_cog.admin.remove_command("collector")
            admin_cog.admin.app_command.remove_command("collector")
            log.info("Removed collector admin commands from Admin cog")
        except Exception:
            pass
