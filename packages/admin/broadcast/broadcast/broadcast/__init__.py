from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from .cog import BroadcastCog, broadcast as broadcast_command

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.broadcast")


async def setup(bot: "BallsDexBot") -> None:
    await bot.add_cog(BroadcastCog(bot))
    log.info("BroadcastCog loaded")

    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            if admin_cog.admin.app_command.get_command("broadcast"):
                admin_cog.admin.app_command.remove_command("broadcast")
            admin_cog.admin.app_command.add_command(broadcast_command.app_command)
            log.info("Attached /admin broadcast to Admin cog")
        except Exception:
            log.warning("Failed to attach /admin broadcast", exc_info=True)
    else:
        log.warning(
            "Admin cog not found — /admin broadcast will not be registered."
        )


async def teardown(bot: "BallsDexBot") -> None:
    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            admin_cog.admin.app_command.remove_command("broadcast")
        except Exception:
            pass
