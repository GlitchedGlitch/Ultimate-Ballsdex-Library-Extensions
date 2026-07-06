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


def _collect_leaf_commands(
    bot: "BallsDexBot",
) -> dict[tuple[str, str], app_commands.Command]:
    """
    Return { (group_name, cmd_internal_name): Command } for every leaf command.
    group_name is "" for ungrouped top-level commands.
    """
    result: dict[tuple[str, str], app_commands.Command] = {}
    for cmd in bot.tree.get_commands():
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.walk_commands():
                if isinstance(sub, app_commands.Command):
                    result[(cmd.name, sub.name)] = sub
        elif isinstance(cmd, app_commands.Command):
            result[("", cmd.name)] = cmd
    return result


class ReSlasherCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._originals: dict[tuple[str, str], str] = {}

    async def _sync_registry(self, leaf_commands: dict[tuple[str, str], app_commands.Command]):
        """Write all known leaf commands to CommandRegistry for admin panel discovery."""
        @sync_to_async
        def _do_sync():
            existing = {
                (r.group, r.command)
                for r in CommandRegistry.objects.all()
            }
            new_keys = set(leaf_commands.keys())

            to_create = [
                CommandRegistry(group=g, command=c)
                for g, c in new_keys - existing
            ]
            if to_create:
                CommandRegistry.objects.bulk_create(to_create, ignore_conflicts=True)

            stale = existing - new_keys
            if stale:
                for group, command in stale:
                    CommandRegistry.objects.filter(group=group, command=command).delete()

        await _do_sync()

    async def _apply_overrides(self, leaf_commands: dict[tuple[str, str], app_commands.Command]):
        """Read overrides from DB and apply them to live command objects."""
        overrides = {
            (o.group, o.command): o.name
            async for o in CommandNameOverride.objects.all()
        }

        renamed = 0
        for (group, cmd_internal), cmd in leaf_commands.items():
            override_name = overrides.get((group, cmd_internal))
            if override_name and override_name != cmd_internal:
                self._originals[(group, cmd_internal)] = cmd.name
                cmd.name = override_name
                renamed += 1

        if renamed:
            log.info("ReSlasher: applied %d command name override(s)", renamed)

    async def _restore_originals(self, leaf_commands: dict[tuple[str, str], app_commands.Command]):
        """Restore original command names on teardown."""
        for (group, cmd_internal), original_name in self._originals.items():
            cmd = leaf_commands.get((group, cmd_internal))
            if cmd:
                cmd.name = original_name
        self._originals.clear()

    @commands.Cog.listener()
    async def on_ready(self):
        """Apply overrides once the bot is ready and all extensions are loaded."""
        leaf_commands = _collect_leaf_commands(self.bot)

        await self._sync_registry(leaf_commands)
        log.info("ReSlasher: synced %d commands to registry", len(leaf_commands))

        await self._apply_overrides(leaf_commands)

        try:
            await self.bot.tree.sync()
            log.info("ReSlasher: command tree synced after applying overrides")
        except Exception:
            log.warning("ReSlasher: failed to sync command tree", exc_info=True)

    async def cog_unload(self):
        """Restore original names when the cog is unloaded."""
        leaf_commands = _collect_leaf_commands(self.bot)
        await self._restore_originals(leaf_commands)
        try:
            await self.bot.tree.sync()
            log.info("ReSlasher: command tree synced after restoring original names")
        except Exception:
            log.warning("ReSlasher: failed to sync command tree on unload", exc_info=True)
