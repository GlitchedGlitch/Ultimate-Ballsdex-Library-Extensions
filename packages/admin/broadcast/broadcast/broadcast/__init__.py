from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .cog import BroadcastCog, broadcast

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.broadcast")


async def setup(bot: "BallsDexBot") -> None:
    await bot.add_cog(BroadcastCog(bot))
    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            try:
                admin_cog.admin.app_command.remove_command("broadcast")
            except Exception:
                pass

            admin_cog.admin.app_command.add_command(
                broadcast.app_command
            )

            log.info("Attached /admin broadcast")
        except Exception:
            log.exception("Failed to attach /admin broadcast")
    else:
        log.warning("Admin cog not found — /admin broadcast not registered")


async def teardown(bot: "BallsDexBot") -> None:
    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            admin_cog.admin.app_command.remove_command("broadcast")
        except Exception:
            pass
