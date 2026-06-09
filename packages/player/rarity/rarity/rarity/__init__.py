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

    balls_cog = bot.get_cog("Balls")

    if balls_cog is None or not hasattr(balls_cog, "admin"):
        log.warning("Balls cog not found — rarity command not registered")
        return

    group = balls_cog.admin.app_command

    try:
        group.remove_command("rarity")
    except Exception:
        pass

    group.add_command(build_rarity_command(bot))

    log.info("Attached /balls rarity")


async def teardown(bot: "BallsDexBot") -> None:
    balls_cog = bot.get_cog("Balls")

    if balls_cog is None or not hasattr(balls_cog, "admin"):
        return

    try:
        balls_cog.admin.app_command.remove_command("rarity")
    except Exception:
        pass
