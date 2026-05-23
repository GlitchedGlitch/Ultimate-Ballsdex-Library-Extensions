from typing import TYPE_CHECKING

from .cog import CollectorAdminCog, CollectorCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    import logging

    log = logging.getLogger("ballsdex.packages.collector")

    await bot.add_cog(CollectorCog(bot))
    log.info("CollectorCog loaded")

    admin_cog = bot.get_cog("admin") or bot.get_cog("Admin")

    if admin_cog and admin_cog.__cog_app_commands_group__:
        group = admin_cog.__cog_app_commands_group__

        existing = group.get_command("collector")
        if existing is not None:
            group.remove_command("collector")
            log.debug("Removed stale /admin collector subgroup before re-adding")

        await bot.add_cog(CollectorAdminCog(bot))
        admin_sub = bot.get_cog("collector")
        if admin_sub and admin_sub.__cog_app_commands_group__:
            group.add_command(admin_sub.__cog_app_commands_group__)
            log.info("Attached /admin collector subgroup to Admin cog")
        else:
            log.warning("Could not find CollectorAdminCog's app commands group")
    else:
        log.warning(
            "Could not find Admin cog or its command group. "
            "/admin collector commands will NOT be registered. "
            "Ensure the admin package is loaded before collector in config/extra.toml."
        )
