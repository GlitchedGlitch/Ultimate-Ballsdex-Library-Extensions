from typing import TYPE_CHECKING
from .cog import CollectorAdminGroup, CollectorCog, _migrate_requirements

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    import discord
    import logging
    from ballsdex.settings import settings

    log = logging.getLogger("ballsdex.packages.collector")

    try:
        await _migrate_requirements()
    except Exception:
        log.warning("requirements.txt migration failed or skipped", exc_info=True)

    admin_cog = bot.get_cog("Admin")
    if admin_cog and admin_cog.__cog_app_commands_group__:
        group = admin_cog.__cog_app_commands_group__

        if group.get_command("collector") is not None:
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

    try:
        import asyncio
        guild_syncs = [
            bot.tree.sync(guild=discord.Object(id=gid))
            for gid in settings.admin_guild_ids
        ]
        await asyncio.gather(bot.tree.sync(), *guild_syncs)
        log.info("Command tree synced after collector setup")
    except Exception:
        log.warning("Failed to sync command tree after collector setup", exc_info=True)
