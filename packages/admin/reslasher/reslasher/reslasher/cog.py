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
    Walk the entire command tree and return flat list of:
    (group, subgroup, command_name, command_object)
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


def _apply_overrides(tree, overrides: dict) -> tuple[int, list[str]]:
    """
    Apply name overrides to the command tree.
    Also updates parent Group._children and Tree._children dicts.
    Returns (applied_count, errors).
    """
    commands_list = _walk_commands(tree)
    current_by_key: dict[tuple[str, str, str], app_commands.Command] = {
        (g, sg, c): cmd for g, sg, c, cmd in commands_list
    }

    names_by_parent: dict[tuple[str, str], dict[str, tuple]] = {}
    errors: list[str] = []
    
    for (group, subgroup, cmd_internal), new_name in overrides.items():
        key = (group, subgroup, cmd_internal)
        cmd = current_by_key.get(key)
        if not cmd:
            continue
        
        parent = (group, subgroup)
        if parent not in names_by_parent:
            names_by_parent[parent] = {}
        
        for other_key, other_cmd in current_by_key.items():
            if other_key == key:
                continue
            og, osg, oc = other_key
            if (og, osg) == parent and other_cmd.name == new_name:
                errors.append(
                    f"Skip: /{' '.join(filter(None, key))} -> '{new_name}' "
                    f"(conflicts with /{' '.join(filter(None, other_key))})"
                )
                break
        
        if new_name not in names_by_parent.get(parent, {}):
            if parent not in names_by_parent:
                names_by_parent[parent] = {}
            names_by_parent[parent][new_name] = key

    if errors:
        return 0, errors

    applied = 0
    for (group, subgroup, cmd_internal), new_name in overrides.items():
        key = (group, subgroup, cmd_internal)
        cmd = current_by_key.get(key)
        if not cmd or cmd.name == new_name:
            continue
        
        old_name = cmd.name
        
        if cmd.parent and hasattr(cmd.parent, '_children'):
            parent_children = cmd.parent._children
            if old_name in parent_children:
                del parent_children[old_name]
            parent_children[new_name] = cmd
        
        if not cmd.parent and hasattr(tree, '_children'):
            tree_children = tree._children
            if old_name in tree_children:
                del tree_children[old_name]
            tree_children[new_name] = cmd
        
        cmd.name = new_name
        applied += 1
        log.info("ReSlasher: renamed /%s -> '%s'", " ".join(filter(None, key)), new_name)

    return applied, errors


class ReSlasherCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._original_sync = None

    def _patch_sync(self):
        """Monkey-patch tree.sync to apply overrides before syncing."""
        if self._original_sync is not None:
            return

        self._original_sync = self.bot.tree.sync

        async def patched_sync(guild=None):
            @sync_to_async
            def _load_overrides():
                return {
                    (o.group, o.subgroup, o.command): o.name
                    for o in CommandNameOverride.objects.all()
                }

            try:
                overrides = await _load_overrides()
                if overrides:
                    applied, errors = _apply_overrides(self.bot.tree, overrides)
                    if applied:
                        log.info("ReSlasher: applied %d override(s) before sync", applied)
                    if errors:
                        for err in errors:
                            log.warning("ReSlasher: %s", err)
            except Exception:
                log.warning("ReSlasher: failed to apply overrides before sync", exc_info=True)

            return await self._original_sync(guild=guild)

        self.bot.tree.sync = patched_sync
        log.info("ReSlasher: patched tree.sync()")

    def _unpatch_sync(self):
        """Restore original tree.sync."""
        if self._original_sync is not None:
            self.bot.tree.sync = self._original_sync
            self._original_sync = None
            log.info("ReSlasher: restored original tree.sync()")

    @commands.Cog.listener()
    async def on_ready(self):
        """Sync registry and patch tree.sync on startup."""
        commands_list = _walk_commands(self.bot.tree)
        created = await sync_registry(commands_list)
        log.info("ReSlasher: synced %d commands to registry (%d new)", len(commands_list), created)
        
        self._patch_sync()

    async def cog_unload(self):
        self._unpatch_sync()


async def setup(bot: "BallsDexBot") -> None:
    from .cog import ReSlasherCog, _walk_commands, sync_registry
    
    cog = ReSlasherCog(bot)
    await bot.add_cog(cog)
    
    if bot.is_ready():
        commands_list = _walk_commands(bot.tree)
        created = await sync_registry(commands_list)
        log.info("ReSlasher: eagerly synced %d commands (%d new)", len(commands_list), created)
        cog._patch_sync()
    
    log.info("ReSlasherCog loaded")


async def teardown(bot: "BallsDexBot") -> None:
    pass
