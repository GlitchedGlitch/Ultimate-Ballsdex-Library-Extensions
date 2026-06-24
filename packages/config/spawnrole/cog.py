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


# ── Raw SQL helpers (most reliable, bypasses Tortoise model caching issues) ──

async def _fetch_spawn_role_from_db(guild_id: int) -> int | None:
    """Fetch spawn_role directly from the database."""
    try:
        from tortoise import Tortoise
        conn = Tortoise.get_connection("default")
        result = await conn.execute_query_dict(
            "SELECT spawn_role FROM guildconfig WHERE guild_id = $1",
            [guild_id]
        )
        if result and result[0].get("spawn_role") is not None:
            return int(result[0]["spawn_role"])
    except Exception as e:
        log.debug(f"Failed to fetch spawn_role: {e}")
    return None


async def _set_spawn_role_in_db(guild_id: int, role_id: int | None) -> None:
    """Set spawn_role using raw SQL to avoid Tortoise model cache issues."""
    from tortoise import Tortoise
    conn = Tortoise.get_connection("default")
    
    result = await conn.execute_query_dict(
        "SELECT guild_id FROM guildconfig WHERE guild_id = $1",
        [guild_id]
    )
    
    if result:
        await conn.execute_query_dict(
            "UPDATE guildconfig SET spawn_role = $1 WHERE guild_id = $2",
            [role_id, guild_id]
        )
    else:
        await conn.execute_query_dict(
            "INSERT INTO guildconfig (guild_id, spawn_channel, enabled, silent, spawn_role) "
            "VALUES ($1, NULL, TRUE, FALSE, $2)",
            [guild_id, role_id]
        )


# ── GuildConfig.save() patch to preserve spawn_role from other commands ──

def _patch_guildconfig_save():
    """Patch GuildConfig.save() so /config disable/channel doesn't wipe spawn_role."""
    if getattr(GuildConfig, "_spawn_role_save_patched", False):
        return
    
    _original_save = GuildConfig.save
    
    async def _patched_save(self, *args, **kwargs):
        # On full saves (no update_fields), preserve spawn_role if missing from _data
        if kwargs.get("update_fields") is None and hasattr(self, "_data"):
            if "spawn_role" not in self._data:
                try:
                    from tortoise import Tortoise
                    conn = Tortoise.get_connection("default")
                    result = await conn.execute_query_dict(
                        "SELECT spawn_role FROM guildconfig WHERE guild_id = $1",
                        [self.guild_id]
                    )
                    if result and result[0].get("spawn_role") is not None:
                        self._data["spawn_role"] = result[0]["spawn_role"]
                    else:
                        self._data["spawn_role"] = None
                except Exception as e:
                    log.debug(f"Save patch failed to fetch spawn_role: {e}")
                    self._data["spawn_role"] = None
        
        return await _original_save(self, *args, **kwargs)
    
    GuildConfig.save = _patched_save
    GuildConfig._spawn_role_save_patched = True

_patch_guildconfig_save()


# ── Cog ──

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

            # Always read current value from DB
            current_role_id = await _fetch_spawn_role_from_db(guild_id)

            if remove or (role and current_role_id == role.id):
                # Remove the role
                await _set_spawn_role_in_db(guild_id, None)

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
            await _set_spawn_role_in_db(guild_id, role.id)

            await interaction.response.send_message(
                f"{settings.bot_name} will now alert "
                f"<@&{role.id}> when "
                f"{settings.plural_collectible_name} spawn.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

        return spawnrole


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(SpawnRoleCog(bot))
