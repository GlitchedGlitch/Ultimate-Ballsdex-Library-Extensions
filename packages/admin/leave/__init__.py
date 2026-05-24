from typing import TYPE_CHECKING
from .cog import LeaveCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import discord
    import logging
    from ballsdex.settings import settings

    log = logging.getLogger("ballsdex.packages.leave")

    admin_cog = bot.get_cog("Admin")
    if admin_cog and admin_cog.__cog_app_commands_group__:
        group = admin_cog.__cog_app_commands_group__

        if group.get_command("leave_server") is not None:
            group.remove_command("leave_server")
            log.info("Removed existing leave_server command before re-adding")

        from .cog import LeaveCommand
        group.add_command(LeaveCommand(bot))
        log.info("Attached /admin leave_server to Admin cog group")
    else:
        log.warning(
            "Could not find Admin cog or its command group. "
            "/admin leave_server will NOT be registered. "
            "Ensure ballsdex.packages.admin is loaded before "
            "ballsdex.packages.leave in config.yml."
        )

    await bot.add_cog(LeaveCog(bot))

    try:
        import asyncio
        guild_syncs = [
            bot.tree.sync(guild=discord.Object(id=gid))
            for gid in settings.admin_guild_ids
        ]
        await asyncio.gather(bot.tree.sync(), *guild_syncs)
        log.info("Command tree synced after leave setup")
    except Exception:
        log.warning("Failed to sync command tree after leave setup", exc_info=True)
