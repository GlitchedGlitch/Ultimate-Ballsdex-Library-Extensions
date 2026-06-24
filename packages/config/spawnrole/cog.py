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


# ── Runtime model patch ──

def _ensure_spawn_role_field():
    """Monkey-patch spawn_role onto GuildConfig if the model wasn't restarted."""
    if getattr(GuildConfig, "_spawn_role_patched", False):
        return

    attr = getattr(GuildConfig, "spawn_role", None)
    if attr is not None and hasattr(type(attr), "__get__"):
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

    meta = GuildConfig._meta
    meta.fields_map["spawn_role"] = _field
    meta.fields.add("spawn_role")
    meta.db_fields.add("spawn_role")
    meta.fields_db_projection["spawn_role"] = "spawn_role"

    GuildConfig.spawn_role = _SpawnRoleDescriptor()  # type: ignore
    GuildConfig._spawn_role_patched = True

    log.debug("Runtime-patched spawn_role onto GuildConfig")

_ensure_spawn_role_field()


# ── Helper to fetch spawn_role reliably from DB ──

async def _fetch_spawn_role_from_db(guild_id: int) -> int | None:
    """Fetch spawn_role directly from the database to avoid cache issues."""
    try:
        from tortoise import Tortoise
        conn = Tortoise.get_connection("default")
        result = await conn.execute_query_dict(
            "SELECT spawn_role FROM guildconfig WHERE guild_id = %s",
            [guild_id]
        )
        if result and result[0].get("spawn_role") is not None:
            return int(result[0]["spawn_role"])
    except Exception as e:
        log.debug(f"Could not fetch spawn_role from DB: {e}")
    return None


def _get_spawn_role_from_instance(config: GuildConfig) -> int | None:
    """Get spawn_role from a GuildConfig instance's _data dict."""
    if hasattr(config, "_data"):
        val = config._data.get("spawn_role")
        if val is not None:
            return val
    val = getattr(config, "spawn_role", None)
    if isinstance(val, int):
        return val
    return None


# ── Patch GuildConfig.save() to preserve spawn_role on full saves ──

def _patch_guildconfig_save():
    """Patch GuildConfig.save() to preserve spawn_role when other commands do full saves."""
    if getattr(GuildConfig, "_spawn_role_save_patched", False):
        return
    
    _original_save = GuildConfig.save
    
    async def _patched_save(self, *args, **kwargs):
        # If doing a full save (no update_fields specified), preserve spawn_role
        if kwargs.get("update_fields") is None:
            if hasattr(self, "_data") and "spawn_role" not in self._data:
                # Fetch current value from DB to prevent it being set to NULL
                try:
                    current = await _fetch_spawn_role_from_db(self.guild_id)
                    if current is not None:
                        self._data["spawn_role"] = current
                except Exception:
                    pass  # DB might not have column yet, ignore
        
        return await _original_save(self, *args, **kwargs)
    
    GuildConfig.save = _patched_save
    GuildConfig._spawn_role_save_patched = True

_patch_guildconfig_save()


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

            # Always fetch fresh from DB to get accurate current value
            current_role_id = await _fetch_spawn_role_from_db(guild_id)

            if remove or (role and current_role_id == role.id):
                # Remove the role
                config, _ = await GuildConfig.get_or_create(guild_id=guild_id)
                if hasattr(config, "_data"):
                    config._data["spawn_role"] = None
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

            # Set the role
            config, _ = await GuildConfig.get_or_create(guild_id=guild_id)
            if hasattr(config, "_data"):
                config._data["spawn_role"] = role.id
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
