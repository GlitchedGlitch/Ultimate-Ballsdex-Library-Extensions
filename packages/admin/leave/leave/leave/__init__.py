from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from .cog import LeaveCog, LeaveCommand

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.leave")


async def setup(bot: "BallsDexBot") -> None:
    await bot.add_cog(LeaveCog(bot))
    log.info("LeaveCog loaded")

    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            if admin_cog.admin.app_command.get_command("leave_server"):
                admin_cog.admin.app_command.remove_command("leave_server")
            admin_cog.admin.app_command.add_command(LeaveCommand(bot))
            log.info("Attached /admin leave_server to Admin cog")
        except Exception:
            log.warning("Failed to attach /admin leave_server", exc_info=True)
    else:
        log.warning(
            "Admin cog not found — /admin leave_server will not be registered."
        )


async def teardown(bot: "BallsDexBot") -> None:
    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            admin_cog.admin.app_command.remove_command("leave_server")
        except Exception:
            pass
 
