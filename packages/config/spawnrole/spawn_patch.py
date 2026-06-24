"""
This is where magic happens :3
"""

import logging

import discord

from ballsdex.packages.countryballs.countryball import BallSpawnView

log = logging.getLogger("ballsdex.packages.spawnrole")

_original_spawn = BallSpawnView.spawn


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
    except Exception:
        pass
    return None


class _ChannelProxy:
    """Proxy that wraps a TextChannel and modifies send() content."""
    
    def __init__(self, channel: discord.TextChannel, role_suffix: str, role_id: int | None):
        self._channel = channel
        self._role_suffix = role_suffix
        self._role_id = role_id
    
    def __getattr__(self, name: str):
        return getattr(self._channel, name)
    
    async def send(self, content=None, **kwargs):
        if content and isinstance(content, str) and self._role_suffix not in content:
            content = content + self._role_suffix
        
        # Only allow the specific role to be mentioned, suppress everything else
        if self._role_id:
            kwargs["allowed_mentions"] = discord.AllowedMentions(
                roles=[discord.Object(id=self._role_id)],
                users=False,
                everyone=False,
            )
        else:
            kwargs.setdefault("allowed_mentions", discord.AllowedMentions.none())
        
        return await self._channel.send(content=content, **kwargs)


async def _patched_spawn(self, channel: discord.TextChannel) -> bool:
    spawn_role_id = await _fetch_spawn_role_from_db(channel.guild.id)
    
    role_suffix = ""
    role = None
    if spawn_role_id:
        role = channel.guild.get_role(spawn_role_id)
        if role:
            role_suffix = f" <@&{role.id}>"

    if not role_suffix:
        return await _original_spawn(self, channel)

    proxy_channel = _ChannelProxy(channel, role_suffix, spawn_role_id)
    
    return await _original_spawn(self, proxy_channel)


def apply():
    BallSpawnView.spawn = _patched_spawn
    log.info("Patched BallSpawnView.spawn for spawn role mentions")


def revert():
    BallSpawnView.spawn = _original_spawn
    log.info("Reverted BallSpawnView.spawn patch")
