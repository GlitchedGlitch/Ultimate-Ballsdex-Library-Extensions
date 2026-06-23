from typing import TYPE_CHECKING
from .cog import SpawnRoleCog
from . import spawn_patch

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    spawn_patch.apply()
    await bot.add_cog(SpawnRoleCog(bot))


async def teardown(bot: "BallsDexBot"):
    spawn_patch.revert()
