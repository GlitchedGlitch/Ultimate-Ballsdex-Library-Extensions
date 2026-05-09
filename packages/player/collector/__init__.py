from typing import TYPE_CHECKING
from discord import app_commands
from .cog import CollectorCog, CollectorAdmin

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    # Find the existing /admin group registered by ballsdex.packages.admin
    # and attach our /admin collector subgroup to it instead of registering
    # a new top-level /admin group (which would cause CommandAlreadyRegistered)
    admin_group = bot.tree.get_command("admin")
    if isinstance(admin_group, app_commands.Group):
        collector_admin = CollectorAdmin(bot)
        admin_group.add_command(collector_admin)
    else:
        import logging
        logging.getLogger("ballsdex.packages.collector").warning(
            "Could not find /admin group — /admin collector commands will not be registered. "
            "Make sure ballsdex.packages.admin is loaded before ballsdex.packages.collector."
        )

    await bot.add_cog(CollectorCog(bot))
