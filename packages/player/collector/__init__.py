from typing import TYPE_CHECKING
from discord import app_commands
from .cog import CollectorAdminGroup, CollectorCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import logging
    log = logging.getLogger("ballsdex.packages.collector")

    # BallsDex registers /admin as a guild-specific command (only in
    # settings.admin_guild_ids), NOT as a global command. So we must look it
    # up per guild using bot.tree.get_command("admin", guild=...) rather than
    # the global bot.tree.get_command("admin").
    from ballsdex.settings import settings
    import discord

    attached = False
    for guild_id in settings.admin_guild_ids:
        guild = discord.Object(id=guild_id)
        admin_group = bot.tree.get_command("admin", guild=guild)
        if isinstance(admin_group, app_commands.Group):
            try:
                admin_group.add_command(CollectorAdminGroup(bot))
                attached = True
                log.info(
                    "Attached /admin collector to guild %d", guild_id
                )
            except Exception as e:
                log.warning(
                    "Could not attach /admin collector to guild %d: %s",
                    guild_id, e,
                )
            break  # only need to attach once; it applies to all matching guilds

    if not attached:
        log.warning(
            "Could not find /admin group in any admin guild. "
            "/admin collector commands will NOT be registered. "
            "Ensure ballsdex.packages.admin is loaded before "
            "ballsdex.packages.collector in config.yml."
        )

    # CollectorCog only has /collector commands — safe to add_cog without conflict
    await bot.add_cog(CollectorCog(bot))
