"""
this is where magic happens :3
"""

import logging

import discord

from ballsdex.packages.countryballs.countryball import BallSpawnView
from bd_models.models import GuildConfig

log = logging.getLogger("ballsdex.packages.spawnrole")

_original_spawn = BallSpawnView.spawn


async def _fetch_spawn_role(guild_id: int) -> int | None:
    """Fetch the configured spawn role for a guild using the OneToOne relation."""
    config = await GuildConfig.objects.filter(guild_id=guild_id).select_related("spawn_role").afirst()
    return config.spawn_role.role_id if config and hasattr(config, "spawn_role") and config.spawn_role else None


class _ChannelProxy:
    """Proxy that wraps a TextChannel and appends the role mention on send()."""

    def __init__(self, channel: discord.TextChannel, role_suffix: str, role_id: int | None):
        self._channel = channel
        self._role_suffix = role_suffix
        self._role_id = role_id

    def __getattr__(self, name: str):
        return getattr(self._channel, name)

    async def send(self, content=None, **kwargs):
        if content and isinstance(content, str) and self._role_suffix not in content:
            content = content + self._role_suffix

        if self._role_id:
            kwargs["allowed_mentions"] = discord.AllowedMentions(
                roles=[discord.Object(id=self._role_id)],
                users=False,
                everyone=False,
            )
        else:
            kwargs.setdefault("allowed_mentions", discord.AllowedMentions.none())

        return await self._channel.send(content=content, **kwargs)


async def _patched_spawn(self, channel: discord.TextChannel, custom_message: str | None = None) -> bool:
    spawn_role_id = await _fetch_spawn_role(channel.guild.id)

    role_suffix = ""
    role = None
    if spawn_role_id:
        role = channel.guild.get_role(spawn_role_id)
        if role:
            role_suffix = f" <@&{role.id}>"

    if not role_suffix:
        return await _original_spawn(self, channel, custom_message=custom_message)

    proxy_channel = _ChannelProxy(channel, role_suffix, spawn_role_id)
    return await _original_spawn(self, proxy_channel, custom_message=custom_message)


def apply():
    BallSpawnView.spawn = _patched_spawn
    log.info("Patched BallSpawnView.spawn for spawn role mentions (runtime-only, no core files touched)")


def revert():
    BallSpawnView.spawn = _original_spawn
    log.info("Reverted BallSpawnView.spawn patch")
