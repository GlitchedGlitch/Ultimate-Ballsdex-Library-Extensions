"""
This is where magic happens :3
"""

import logging

import discord

from ballsdex.core.models import GuildConfig
from ballsdex.packages.countryballs.countryball import BallSpawnView

log = logging.getLogger("ballsdex.packages.spawnrole")

_original_spawn = BallSpawnView.spawn


def _get_spawn_role_raw(config) -> int | None:
    """Safely get spawn_role value from a GuildConfig instance."""
    if config is None:
        return None

    if hasattr(config, "_data"):
        val = config._data.get("spawn_role")
        if val is not None:
            return val

    val = getattr(config, "spawn_role", None)
    if isinstance(val, int):
        return val
    return None


async def _patched_spawn(self, channel: discord.TextChannel) -> bool:
    config = await GuildConfig.get_or_none(guild_id=channel.guild.id)
    role_suffix = ""
    
    spawn_role_id = _get_spawn_role_raw(config)
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
