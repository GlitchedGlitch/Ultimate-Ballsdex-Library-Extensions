import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

from settings.models import settings

log = logging.getLogger("rarity")


async def setup(bot: "BallsDexBot"):
    """
    Rarity extension setup hook.
    Safely attaches the command group using settings if available.
    """

    group_name = getattr(settings, "players_group_cog_name", None)

    if not group_name:
        group_name = "players"

    log.info("Attached rarity command to /%s group", group_name)

    await bot.add_cog(RarityCog(bot, group_name))
