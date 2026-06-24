"""
Spawn Role package for BallsDex v3 :3
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from bd_models.models import GuildConfig
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.spawnrole")


class SpawnRoleCog(commands.Cog):
    """Adds /config spawnrole to the existing Config group."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._attach()

    def _attach(self):
        config_cog = self.bot.cogs.get("Config")
        if config_cog is None or not hasattr(config_cog, "config"):
            log.warning(
                "Could not find Config cog. /config spawnrole will not be registered. "
                "Ensure the config package loads before spawnrole."
            )
            return

        group = config_cog.config.app_command
        if group.get_command("spawnrole"):
            group.remove_command("spawnrole")

        group.add_command(self._build_command())
        log.info("Attached /config spawnrole to Config cog")

    def _detach(self):
        config_cog = self.bot.cogs.get("Config")
        if config_cog is not None and hasattr(config_cog, "config"):
            try:
                config_cog.config.app_command.remove_command("spawnrole")
            except Exception:
                pass

    def _build_command(self) -> app_commands.Command:
        bot = self.bot

        @app_commands.command(
            name="spawnrole",
            description="Mention a role in each spawn",
        )
        @app_commands.checks.has_permissions(manage_guild=True)
        @app_commands.describe(
            role="The role to ping on each spawn message.",
            remove="Whether or not to remove the spawn role.",
        )
        async def spawnrole(
            interaction: discord.Interaction["BallsDexBot"],
            role: Optional[discord.Role] = None,
            remove: bool = False,
        ):
            guild_id = interaction.guild_id
            assert guild_id

            config, _ = await GuildConfig.objects.aget_or_create(
                guild_id=guild_id, defaults={"guild_id": guild_id}
            )
            current_role_id = config.spawn_role

            if remove or (role and current_role_id == role.id):
                config.spawn_role = None
                await config.asave(update_fields=("spawn_role",))

                if current_role_id:
                    await interaction.response.send_message(
                        f"{settings.bot_name} will no longer alert "
                        f"<@&{current_role_id}> when "
                        f"{settings.plural_collectible_name} spawn.",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                else:
                    await interaction.response.send_message(
                        "There is no spawn role configured for this server.",
                        ephemeral=True,
                    )
                return

            if role is None:
                await interaction.response.send_message(
                    "Please provide a `role`, or use `remove: True` to clear the current one.",
                    ephemeral=True,
                )
                return

            config.spawn_role = role.id
            await config.asave(update_fields=("spawn_role",))

            await interaction.response.send_message(
                f"{settings.bot_name} will now alert "
                f"<@&{role.id}> when "
                f"{settings.plural_collectible_name} spawn.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

        return spawnrole
