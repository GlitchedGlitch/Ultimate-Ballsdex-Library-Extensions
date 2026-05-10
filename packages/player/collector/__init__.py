from typing import TYPE_CHECKING
from .cog import CollectorAdminGroup, CollectorCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import logging
    log = logging.getLogger("ballsdex.packages.collector")

    admin_cog = bot.get_cog("Admin")
    if admin_cog and admin_cog.__cog_app_commands_group__:
        group = admin_cog.__cog_app_commands_group__

        # On reload, the subcommand is already registered — remove it first
        existing = group.get_command("collector")
        if existing is not None:
            group.remove_command("collector")
            log.info("Removed existing /admin collector before re-adding")

        group.add_command(CollectorAdminGroup(bot))
        log.info("Attached /admin collector to Admin cog group")
    else:
        log.warning(
            "Could not find Admin cog or its command group. "
            "/admin collector commands will NOT be registered. "
            "Ensure ballsdex.packages.admin is loaded before "
            "ballsdex.packages.collector in config.yml."
        )

    await bot.add_cog(CollectorCog(bot))
