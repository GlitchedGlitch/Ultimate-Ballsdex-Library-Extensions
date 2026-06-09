from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from .cog import RarityCog, build_rarity_command

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.rarity")


async def setup(bot: "BallsDexBot") -> None:
    await bot.add_cog(RarityCog(bot))
    log.info("RarityCog loaded")

    from settings.models import settings

    group_name = getattr(settings, "players_group_cog_name", None)

    balls_cog = bot.get_cog("Balls")
    if balls_cog is None and group_name:
        balls_cog = bot.get_cog(group_name)

    if balls_cog is not None and getattr(balls_cog, "__cog_app_commands_group__", None):
        group = balls_cog.__cog_app_commands_group__

        existing = group.get_command("rarity")
        if existing is not None:
            group.remove_command("rarity")
            log.debug("Removed stale rarity command before re-adding")

        group.add_command(build_rarity_command(bot))
        log.info("Attached rarity command to /balls group")
    else:
        log.warning(
            "Balls cog not found — rarity command will not be registered. "
            "Ensure the balls package loads before rarity."
        )


async def teardown(bot: "BallsDexBot") -> None:
    from settings.models import settings

    group_name = getattr(settings, "players_group_cog_name", None)

    balls_cog = bot.get_cog("Balls")
    if balls_cog is None and group_name:
        balls_cog = bot.get_cog(group_name)

    if balls_cog is not None and getattr(balls_cog, "__cog_app_commands_group__", None):
        try:
            balls_cog.__cog_app_commands_group__.remove_command("rarity")
        except Exception:
            pass
