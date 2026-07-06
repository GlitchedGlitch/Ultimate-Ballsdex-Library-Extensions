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


async def sync_registry(commands_list: list[tuple[str, str, str, app_commands.Command]]) -> int:
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


async def apply_overrides(
    commands_list: list[tuple[str, str, str, app_commands.Command]],
    originals: dict[tuple[str, str, str], str],
) -> int:
    """Read overrides from DB and apply them to live command objects."""
    overrides = {
        (o.group, o.subgroup, o.command): o.name
        async for o in CommandNameOverride.objects.all()
    }

    renamed = 0
    for group, subgroup, cmd_name, cmd in commands_list:
        key = (group, subgroup, cmd_name)
        override_name = overrides.get(key)
        if override_name and override_name != cmd_name:
            originals[key] = cmd.name
            cmd.name = override_name
            renamed += 1

    return renamed


class ReSlasherCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._originals: dict[tuple[str, str, str], str] = {}

    async def _reload_overrides(self):
        """Re-apply overrides from DB to live commands. Call after saving in admin."""
        commands_list = _walk_commands(self.bot.tree)
        for key, original in self._originals.items():
            group, subgroup, cmd_name = key
            for g, sg, c, cmd in commands_list:
                if (g, sg, c) == key:
                    cmd.name = original
                    break
        self._originals.clear()
        renamed = await apply_overrides(commands_list, self._originals)
        if renamed:
            log.info("ReSlasher: re-applied %d command name override(s)", renamed)
        
        try:
            await self.bot.tree.sync()
            log.info("ReSlasher: command tree re-synced")
        except Exception:
            log.warning("ReSlasher: failed to re-sync command tree", exc_info=True)

    @commands.Cog.listener()
    async def on_ready(self):
        """Apply overrides once the bot is ready and all extensions are loaded."""
        commands_list = _walk_commands(self.bot.tree)

        created = await sync_registry(commands_list)
        log.info("ReSlasher: synced %d commands to registry (%d new)", len(commands_list), created)

        renamed = await apply_overrides(commands_list, self._originals)
        if renamed:
            log.info("ReSlasher: applied %d command name override(s)", renamed)

        try:
            await self.bot.tree.sync()
            log.info("ReSlasher: command tree synced after applying overrides")
        except Exception:
            log.warning("ReSlasher: failed to sync command tree", exc_info=True)

    async def cog_unload(self):
        """Restore original names when the cog is unloaded."""
        commands_list = _walk_commands(self.bot.tree)
        for key, original_name in self._originals.items():
            for g, sg, c, cmd in commands_list:
                if (g, sg, c) == key:
                    cmd.name = original_name
                    break
        self._originals.clear()
        try:
            await self.bot.tree.sync()
            log.info("ReSlasher: command tree synced after restoring original names")
        except Exception:
            log.warning("ReSlasher: failed to sync command tree on unload", exc_info=True)
