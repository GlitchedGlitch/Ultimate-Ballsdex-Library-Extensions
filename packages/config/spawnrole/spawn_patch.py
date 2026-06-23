"""
Patches BallSpawnView.spawn so the configured spawn_role is appended at the
end of the spawn message as a visible role mention WITHOUT pinging anyone.
"""

import logging

import discord

from ballsdex.core.models import GuildConfig
from ballsdex.packages.countryballs.spawn import BallSpawnView

log = logging.getLogger("ballsdex.packages.spawnrole")

_original_spawn = BallSpawnView.spawn


async def _patched_spawn(self, channel: discord.TextChannel) -> bool:
    config = await GuildConfig.get_or_none(guild_id=channel.guild.id)
    role_suffix = ""
    if config and config.spawn_role:
        role = channel.guild.get_role(config.spawn_role)
        if role:
            role_suffix = f" <@&{role.id}>"

    if not role_suffix:
        return await _original_spawn(self, channel)

    # Temporarily wrap channel.send to inject the role mention and
    # disable role pings via allowed_mentions
    original_send = channel.send

    async def patched_send(content=None, **kwargs):
        if content:
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
