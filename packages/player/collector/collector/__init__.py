from __future__ import annotations

default_app_config = "collector.apps.CollectorAppConfig"
import logging
from typing import TYPE_CHECKING
from discord import app_commands
from .cog import CollectorAdminCog, CollectorCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(CollectorCog(bot))
    log.info("CollectorCog loaded")

    admin_cog = bot.get_cog("admin") or bot.get_cog("Admin")
    if not (admin_cog and admin_cog.__cog_app_commands_group__):
        log.warning("Admin cog not found — /admin collector commands will not be registered")
        return

    admin_group: app_commands.Group = admin_cog.__cog_app_commands_group__
    if admin_group.get_command("collector"):
        admin_group.remove_command("collector")

    admin_cog_inst = CollectorAdminCog(bot)
    await bot.add_cog(admin_cog_inst)

    sub = app_commands.Group(name="collector", description="Manage collector requirements")
    for cmd in admin_cog_inst.__cog_app_commands__:
        slash_name = cmd.name.removeprefix("collector-")
        wrapped = app_commands.Command(
            name=slash_name,
            description=cmd.description or "-",
            callback=cmd._callback,
            parent=sub,
        )
        if hasattr(cmd, "_params"):
            wrapped._params = cmd._params
        sub.add_command(wrapped)

    admin_group.add_command(sub)
    log.info("Attached /admin collector subgroup to Admin cog")
