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

    balls_cog = bot.cogs.get("Balls")

    if balls_cog is not None and hasattr(balls_cog, "balls"):
        try:
            try:
                balls_cog.balls.app_command.remove_command("rarity")
            except Exception:
                pass

            balls_cog.balls.app_command.add_command(
                build_rarity_command(bot)
            )

            log.info("Attached /balls rarity")

        except Exception:
            log.exception("Failed to attach /balls rarity")

    else:
        log.warning("Balls cog not found — /balls rarity not registered")


async def teardown(bot: "BallsDexBot") -> None:
    balls_cog = bot.cogs.get("Balls")

    if balls_cog is not None and hasattr(balls_cog, "balls"):
        try:
            balls_cog.balls.app_command.remove_command("rarity")
        except Exception:
            pass
