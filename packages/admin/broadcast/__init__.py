from typing import TYPE_CHECKING
from .cog import BroadcastCog, BroadcastAdminCommand

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import discord
    import logging
    from ballsdex.settings import settings

    log = logging.getLogger("ballsdex.packages.broadcast")

    admin_cog = bot.get_cog("Admin")
    if admin_cog and admin_cog.__cog_app_commands_group__:
        group = admin_cog.__cog_app_commands_group__

        for cmd in list(group.commands):
            if isinstance(cmd, discord.app_commands.Group) and hasattr(cmd, "_is_broadcast"):
                group.remove_command(cmd.name)
                log.info("Removed existing broadcast subgroup before re-adding")

        subgroup = BroadcastAdminCommand(bot)
        group.add_command(subgroup)
        log.info("Attached /admin broadcast to Admin cog group")
    else:
        log.warning(
            "Could not find Admin cog or its command group. "
            "/admin broadcast will NOT be registered. "
            "Ensure ballsdex.packages.admin is loaded before "
            "ballsdex.packages.broadcast in config.yml."
        )

    await bot.add_cog(BroadcastCog(bot))

    try:
        await bot.tree.sync()
        for guild_id in settings.admin_guild_ids:
            await bot.tree.sync(guild=discord.Object(id=guild_id))
        log.info("Command tree synced after broadcast setup")
    except Exception:
        log.warning("Failed to sync command tree after broadcast setup", exc_info=True)
