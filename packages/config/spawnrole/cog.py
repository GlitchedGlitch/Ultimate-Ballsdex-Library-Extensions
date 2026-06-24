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
    if getattr(GuildConfig, "_spawn_role_patched", False):
        return

    meta = GuildConfig._meta
    if "spawn_role" in getattr(meta, "fields_db_projection", {}):
        GuildConfig._spawn_role_patched = True
        return

    from tortoise import fields

    _field = fields.BigIntField(null=True, description="Discord role ID that gets mentioned in every spawn")
    _field.model = GuildConfig
    _field.model_field_name = "spawn_role"
    _field.source_field = "spawn_role"

    class _SpawnRoleDescriptor:
        def __get__(self, obj, objtype=None):
            if obj is None:
                return _field
            if hasattr(obj, "_data"):
                return obj._data.get("spawn_role")
            return getattr(obj, "__dict__", {}).get("spawn_role")
        
        def __set__(self, obj, value):
            if hasattr(obj, "_data"):
                obj._data["spawn_role"] = value
            else:
                obj.__dict__["spawn_role"] = value

    meta.fields_map["spawn_role"] = _field
    meta.fields.add("spawn_role")
    meta.db_fields.add("spawn_role")
    meta.fields_db_projection["spawn_role"] = "spawn_role"
    
    if hasattr(meta, "db_default_fields"):
        meta.db_default_fields.add("spawn_role")

    GuildConfig.spawn_role = _SpawnRoleDescriptor()  # type: ignore
    GuildConfig._spawn_role_patched = True

    log.debug("Runtime-patched spawn_role onto GuildConfig")

_ensure_spawn_role_field()


def _get_spawn_role(config: GuildConfig) -> int | None:
    """Safely get the spawn_role value from a GuildConfig instance."""
    val = getattr(config, "spawn_role", None)
    if val is not None and not isinstance(val, int):
        if hasattr(config, "_data"):
            val = config._data.get("spawn_role")
    return val


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

            current_role_id = _get_spawn_role(config)

            if remove or (role and current_role_id == role.id):
                config.spawn_role = None  # type: ignore
                await config.save(update_fields=("spawn_role",))

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
