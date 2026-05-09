from typing import TYPE_CHECKING
from discord import app_commands
from .cog import CollectorCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    cog = CollectorCog(bot)

    # Attach /admin collector to the existing /admin group
    admin_group = bot.tree.get_command("admin")
    if isinstance(admin_group, app_commands.Group):
        # Build a Group from the cog's admin_collector_group commands
        collector_group = app_commands.Group(
            name="collector",
            description="Manage collector requirements",
        )
        for cmd in cog.admin_collector_group.commands:
            collector_group.add_command(cmd)
        admin_group.add_command(collector_group)

    await bot.add_cog(cog)
