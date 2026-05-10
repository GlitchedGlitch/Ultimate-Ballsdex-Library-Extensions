from typing import TYPE_CHECKING
from .cog import CollectorAdminGroup, CollectorCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import discord
    import logging
    from ballsdex.settings import settings

    log = logging.getLogger("ballsdex.packages.collector")

    admin_cog = bot.get_cog("Admin")
    if admin_cog and admin_cog.__cog_app_commands_group__:
        group = admin_cog.__cog_app_commands_group__

        # On reload the subcommand is already registered — remove it first
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

    # Sync global tree and each admin guild so /admin collector appears immediately
    # without needing a manual sync or bot restart
    try:
        await bot.tree.sync()
        for guild_id in settings.admin_guild_ids:
            await bot.tree.sync(guild=discord.Object(id=guild_id))
        log.info("Command tree synced after collector setup")
    except Exception:
        log.warning("Failed to sync command tree after collector setup", exc_info=True)
