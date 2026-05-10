from typing import TYPE_CHECKING
from .cog import CollectorAdminGroup, CollectorCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import logging
    log = logging.getLogger("ballsdex.packages.collector")

    # BallsDex adds subgroups to /admin via the Admin cog's
    # __cog_app_commands_group__, not via bot.tree directly.
    # This mirrors exactly how balls.py, blacklist.py etc. are attached.
    admin_cog = bot.get_cog("Admin")
    if admin_cog and admin_cog.__cog_app_commands_group__:
        admin_cog.__cog_app_commands_group__.add_command(CollectorAdminGroup(bot))
        log.info("Attached /admin collector to Admin cog group")
    else:
        log.warning(
            "Could not find Admin cog or its command group. "
            "/admin collector commands will NOT be registered. "
            "Ensure ballsdex.packages.admin is loaded before "
            "ballsdex.packages.collector in config.yml."
        )

    # CollectorCog only has /collector commands, safe to add without conflict
    await bot.add_cog(CollectorCog(bot))
