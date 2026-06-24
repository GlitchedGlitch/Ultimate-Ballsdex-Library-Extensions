"""
This is where magic happens :3
"""

import logging

import discord

from ballsdex.core.models import GuildConfig
from ballsdex.packages.countryballs.countryball import BallSpawnView

log = logging.getLogger("ballsdex.packages.spawnrole")

_original_spawn = BallSpawnView.spawn


async def _fetch_spawn_role_from_db(guild_id: int) -> int | None:
    """Fetch spawn_role directly from the database."""
    try:
        from tortoise import Tortoise
        conn = Tortoise.get_connection("default")
        result = await conn.execute_query_dict(
            "SELECT spawn_role FROM guildconfig WHERE guild_id = %s",
            [guild_id]
        )
        if result and result[0].get("spawn_role") is not None:
            return int(result[0]["spawn_role"])
    except Exception:
        pass
    return None


async def _patched_spawn(self, channel: discord.TextChannel) -> bool:
    # Fetch role ID directly from DB to bypass any instance cache issues
    spawn_role_id = await _fetch_spawn_role_from_db(channel.guild.id)
    
    role_suffix = ""
    if spawn_role_id:
        role = channel.guild.get_role(spawn_role_id)
        if role:
            role_suffix = f" <@&{role.id}>"

    if not role_suffix:
        return await _original_spawn(self, channel)

    original_send = channel.send

    async def patched_send(content=None, **kwargs):
        if content and isinstance(content, str):
            content = content + role_suffix
        kwargs.setdefault("allowed_mentions", discord.AllowedMentions.none())
        return await original_send(content=content, **kwargs)

    channel.send = patched_send  # type: ignore
    try:
        return await _original_spawn(self, channel)
    finally:
        channel.send = original_send  # type: ignore


def apply():
    BallSpawnView.spawn = _patched_spawn
    log.info("Patched BallSpawnView.spawn for spawn role mentions")


def revert():
    BallSpawnView.spawn = _original_spawn
    log.info("Reverted BallSpawnView.spawn patch")
