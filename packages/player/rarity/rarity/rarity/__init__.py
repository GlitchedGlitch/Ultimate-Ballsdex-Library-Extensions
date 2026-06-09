import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

from .cog import RarityCog

log = logging.getLogger("rarity")


async def setup(bot: "BallsDexBot"):
    """
    Rarity extension setup hook.
    """

    # ❌ DO NOT access settings.players_group_cog_name (it doesn't exist)
    log.info("Attaching rarity cog")

    await bot.add_cog(RarityCog(bot))
