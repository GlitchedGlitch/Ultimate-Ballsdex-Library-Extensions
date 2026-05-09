from typing import TYPE_CHECKING

from .cog import CollectorCog, CollectorAdmin

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    # Add the player-facing cog normally
    await bot.add_cog(CollectorCog(bot))

    # Attach /admin collector to the existing /admin command group
    # exactly as BallsDex's own admin subgroups do it
    admin_command = bot.tree.get_command("admin")
    if admin_command and hasattr(admin_command, "add_command"):
        admin_command.add_command(CollectorAdmin(bot))
