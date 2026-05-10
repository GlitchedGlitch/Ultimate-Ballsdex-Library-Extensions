from typing import TYPE_CHECKING
from .cog import RarityCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import discord
    import logging
    from ballsdex.settings import settings

    log = logging.getLogger("ballsdex.packages.rarity")

    # The balls/objects group is a GroupCog — find it by cog name "Players"
    # and attach rarity to its __cog_app_commands_group__, same as admin subgroups
    players_cog = bot.get_cog("Players")
    if players_cog and players_cog.__cog_app_commands_group__:
        group = players_cog.__cog_app_commands_group__

        # Remove existing rarity command to avoid conflicts on reload
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
            "Could not find Players cog or its command group. "
            "rarity command will NOT be registered. "
            "Ensure ballsdex.packages.players is loaded before "
            "ballsdex.packages.rarity in config.yml."
        )

    await bot.add_cog(RarityCog(bot))

    try:
        await bot.tree.sync()
        log.info("Command tree synced after rarity setup")
    except Exception:
        log.warning("Failed to sync command tree after rarity setup", exc_info=True)
