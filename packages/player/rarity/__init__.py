from typing import TYPE_CHECKING
from .cog import RarityCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import discord
    import logging
    from ballsdex.settings import settings

    log = logging.getLogger("ballsdex.packages.rarity")

    # Find the existing balls/objects group (settings.players_group_cog_name)
    group_name = settings.players_group_cog_name  # e.g. "objects" or "balls"
    balls_group = bot.tree.get_command(group_name)

    if balls_group is None:
        log.warning(
            "Could not find /%s command group in bot tree. "
            "/objects rarity will NOT be registered. "
            "Ensure ballsdex.packages.balls (or equivalent) is loaded before "
            "ballsdex.packages.rarity in config.yml.",
            group_name,
        )
    else:
        from discord import app_commands
        # Remove any pre-existing rarity command to avoid conflicts
        existing = balls_group.get_command("rarity")  # type: ignore
        if existing is not None:
            balls_group.remove_command("rarity")  # type: ignore
            log.info("Removed existing /%s rarity before re-adding", group_name)

    cog = RarityCog(bot)
    await bot.add_cog(cog)

    # Sync so the command appears immediately
    try:
        await bot.tree.sync()
        log.info("Command tree synced after rarity setup")
    except Exception:
        log.warning("Failed to sync command tree after rarity setup", exc_info=True)
