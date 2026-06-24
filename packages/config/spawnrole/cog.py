"""
Spawn Role package for BallsDex :3
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import GuildConfig
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.spawnrole")

def _ensure_spawn_role_field():
    """Monkey-patch spawn_role onto GuildConfig if the model wasn't restarted."""
    if hasattr(GuildConfig, "spawn_role"):

        if "spawn_role" in GuildConfig._meta.fields_db_projection:
            return

    from tortoise import fields

    field = fields.BigIntField(null=True, description="Discord role ID that gets mentioned in every spawn")
    field.model = GuildConfig
    field.model_field_name = "spawn_role"
    field.source_field = "spawn_role"

    GuildConfig.spawn_role = field

    meta = GuildConfig._meta
    meta.fields_map["spawn_role"] = field
    meta.fields.add("spawn_role")
    meta.db_fields.add("spawn_role")
    meta.fields_db_projection["spawn_role"] = "spawn_role"
    meta.db_default_values["spawn_role"] = None

    if hasattr(meta, "default_ordering"):
        pass

    log.debug("Runtime-patched spawn_role onto GuildConfig")

_ensure_spawn_role_field()


@app_commands.guild_only()
class SpawnRoleGroup(app_commands.Group):
    """Server-side spawn role configuration, attached under /config."""

    def __init__(self, bot: "BallsDexBot"):
        super().__init__(name="spawnrole_group_unused")
        self.bot = bot


class SpawnRoleCog(commands.Cog):
    """Adds /config spawnrole to the existing Config group."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._attach()

    def _attach(self):
        config_cog = self.bot.get_cog("Config")
        if not config_cog or not config_cog.__cog_app_commands_group__:
            log.warning(
                "Could not find Config cog. /config spawnrole will not be registered. "
                "Ensure ballsdex.packages.config loads before ballsdex.packages.spawnrole."
            )
            return

        group = config_cog.__cog_app_commands_group__
        if group.get_command("spawnrole"):
            group.remove_command("spawnrole")

        group.add_command(self._build_command())

    def _build_command(self) -> app_commands.Command:
        bot = self.bot

        @app_commands.command(
            name="spawnrole",
            description="Mention a role in each spawn",
        )
        @app_commands.checks.has_permissions(manage_guild=True)
        @app_commands.describe(
            role="The role to ping on each spawn message.",
            remove="Whether or not remove the spawn role.",
        )
        async def spawnrole(
            interaction: discord.Interaction["BallsDexBot"],
            role: Optional[discord.Role] = None,
            remove: bool = False,
        ):
            guild_id = interaction.guild_id
            assert guild_id

            config, _ = await GuildConfig.get_or_create(guild_id=guild_id)

            if remove or (role and config.spawn_role == role.id):
                old_role_id = config.spawn_role
                config.spawn_role = None  # type: ignore
                await config.save(update_fields=("spawn_role",))

                if old_role_id:
                    await interaction.response.send_message(
                        f"{settings.bot_name} will no longer alert "
                        f"<@&{old_role_id}> when "
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

            config.spawn_role = role.id  # type: ignore
            await config.save(update_fields=("spawn_role",))

            await interaction.response.send_message(
                f"{settings.bot_name} will now alert "
                f"<@&{role.id}> when "
                f"{settings.plural_collectible_name} spawn.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

        return spawnrole


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(SpawnRoleCog(bot))
