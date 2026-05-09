from typing import TYPE_CHECKING
from discord import app_commands
from .cog import CollectorAdminGroup, CollectorCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    # Attach /admin collector to the already-registered /admin group
    # without re-registering /admin itself (which would crash with
    # CommandAlreadyRegistered)
    admin_group = bot.tree.get_command("admin")
    if isinstance(admin_group, app_commands.Group):
        admin_group.add_command(CollectorAdminGroup(bot))
    else:
        import logging
        logging.getLogger("ballsdex.packages.collector").warning(
            "Could not find /admin group in bot tree. "
            "/admin collector commands will NOT be registered. "
            "Ensure ballsdex.packages.admin is loaded before ballsdex.packages.collector "
            "in config.yml."
        )

    # CollectorCog only contains /collector commands — no admin group inside,
    # so add_cog will not try to register /admin again
    await bot.add_cog(CollectorCog(bot))
