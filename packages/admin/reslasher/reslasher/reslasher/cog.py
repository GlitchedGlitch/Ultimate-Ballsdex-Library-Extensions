"""
ReSlasher runtime command name override cog
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from asgiref.sync import sync_to_async

from reslasher.models import CommandNameOverride, CommandRegistry

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.reslasher")


def _walk_commands(tree) -> list[tuple[str, str, str, app_commands.Command]]:
    """
    Walk the entire command tree and return flat list
    """
    result: list[tuple[str, str, str, app_commands.Command]] = []
    
    for cmd in tree.get_commands():
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.walk_commands():
                if isinstance(sub, app_commands.Command):
                    parent = sub.parent
                    if isinstance(parent, app_commands.Group) and parent != cmd:
                        result.append((cmd.name, parent.name, sub.name, sub))
                    else:
                        result.append((cmd.name, "", sub.name, sub))
        elif isinstance(cmd, app_commands.Command):
            result.append(("", "", cmd.name, cmd))
    
    return result


async def sync_registry(commands_list: list) -> int:
    """Write all known commands to CommandRegistry for admin panel discovery."""
    @sync_to_async
    def _do_sync():
        existing = {
            (r.group, r.subgroup, r.command)
            for r in CommandRegistry.objects.all()
        }
        new_keys = {(g, sg, c) for g, sg, c, _ in commands_list}

        to_create = [
            CommandRegistry(group=g, subgroup=sg, command=c)
            for g, sg, c in new_keys - existing
        ]
        created = 0
        if to_create:
            CommandRegistry.objects.bulk_create(to_create, ignore_conflicts=True)
            created = len(to_create)

        stale = existing - new_keys
        if stale:
            for group, subgroup, command in stale:
                CommandRegistry.objects.filter(
                    group=group, subgroup=subgroup, command=command
                ).delete()

        return created

    return await _do_sync()


class ReSlasherCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Sync registry on startup."""
        commands_list = _walk_commands(self.bot.tree)
        created = await sync_registry(commands_list)
        log.info("ReSlasher: synced %d commands to registry (%d new)", len(commands_list), created)

    async def cog_unload(self):
        pass


async def apply_overrides(bot: "BallsDexBot") -> int:
    """
    Read overrides from DB and apply them by deleting old commands and creating new ones
    """
    @sync_to_async
    def _get_overrides():
        return {
            (o.group, o.subgroup, o.command): o.name
            for o in CommandNameOverride.objects.all()
        }

    overrides = await _get_overrides()
    if not overrides:
        return 0

    commands_list = _walk_commands(bot.tree)
    current_by_key: dict[tuple[str, str, str], app_commands.Command] = {
        (g, sg, c): cmd for g, sg, c, cmd in commands_list
    }

    renamed = 0
    for (group, subgroup, cmd_internal), new_name in overrides.items():
        key = (group, subgroup, cmd_internal)
        cmd = current_by_key.get(key)
        if not cmd:
            continue

        if cmd.name == new_name:
            continue
        
        cmd.name = new_name
        renamed += 1
        log.info("ReSlasher: renamed /%s to '%s'", " ".join(filter(None, key)), new_name)

    return renamed


async def setup(bot: "BallsDexBot") -> None:
    from .cog import ReSlasherCog, _walk_commands, sync_registry
    
    cog = ReSlasherCog(bot)
    await bot.add_cog(cog)
    
    if bot.is_ready():
        commands_list = _walk_commands(bot.tree)
        created = await sync_registry(commands_list)
        log.info("ReSlasher: eagerly synced %d commands (%d new)", len(commands_list), created)
    
    log.info("ReSlasherCog loaded")


async def teardown(bot: "BallsDexBot") -> None:
    pass
