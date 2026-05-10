from typing import TYPE_CHECKING
from .cog import RarityCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import asyncio
    import discord
    import logging
    from ballsdex.settings import settings

    log = logging.getLogger("ballsdex.packages.rarity")

    balls_cog = bot.get_cog("Balls")
    if balls_cog and balls_cog.__cog_app_commands_group__:
        group = balls_cog.__cog_app_commands_group__

        if group.get_command("rarity") is not None:
            group.remove_command("rarity")
            log.info("Removed existing rarity command before re-adding")

        from .cog import build_rarity_command
        group.add_command(build_rarity_command(bot))
        log.info(
            "Attached rarity command to /%s group",
            settings.players_group_cog_name,
        )
    else:
        log.warning(
            "Could not find Balls cog or its command group. "
            "rarity command will NOT be registered. "
            "Ensure ballsdex.packages.balls is loaded before "
            "ballsdex.packages.rarity in config.yml."
        )

    await bot.add_cog(RarityCog(bot))

    try:
        guild_syncs = [
            bot.tree.sync(guild=discord.Object(id=gid))
            for gid in settings.admin_guild_ids
        ]
        await asyncio.gather(bot.tree.sync(), *guild_syncs)
        log.info("Command tree synced after rarity setup")
    except Exception:
        log.warning("Failed to sync command tree after rarity setup", exc_info=True)
