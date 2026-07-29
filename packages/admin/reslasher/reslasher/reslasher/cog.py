"""
ReSlasher runtime command name override cog
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from asgiref.sync import sync_to_async

from reslasher.models import CommandNameOverride, CommandRegistry

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.reslasher")


def _walk_all_entities(tree: app_commands.CommandTree) -> List[Tuple[str, str, str, bool, app_commands.AppCommand | app_commands.Group]]:
    """
    Safely walk the entire command tree (including groups and subcommands).
    Returns list of: (group, subgroup, command, is_group, entity_object)
    """
    results = []

    for item in tree.get_commands():
        if isinstance(item, app_commands.Group):
            # Record top-level group
            results.append((item.name, "", "", True, item))
            
            for sub_item in item.commands:
                if isinstance(sub_item, app_commands.Group):
                    # Record subgroup
                    results.append((item.name, sub_item.name, "", True, sub_item))
                    for sub_sub_item in sub_item.commands:
                        # Subcommand under subgroup
                        results.append((item.name, sub_item.name, sub_sub_item.name, False, sub_sub_item))
                elif isinstance(sub_item, app_commands.Command):
                    # Direct command under group
                    results.append((item.name, "", sub_item.name, False, sub_item))
        elif isinstance(item, app_commands.Command):
            # Standalone top-level command
            results.append(("", "", item.name, False, item))

    return results


async def sync_registry(tree: app_commands.CommandTree) -> int:
    """Write all known commands/groups to CommandRegistry for admin panel discovery."""
    entities = _walk_all_entities(tree)

    @sync_to_async
    def _do_sync():
        existing = {
            (r.group, r.subgroup, r.command)
            for r in CommandRegistry.objects.all()
        }
        new_keys = {(g, sg, c) for g, sg, c, _, _ in entities}

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


def _apply_overrides(tree: app_commands.CommandTree, overrides: dict) -> Tuple[int, list[str]]:
    """
    Apply name overrides to commands AND groups, properly updating discord.py's internal children mappings.
    """
    entities = _walk_all_entities(tree)
    errors: list[str] = []
    applied = 0

    # Build lookup map
    entity_map = {(g, sg, c): (is_grp, obj) for g, sg, c, is_grp, obj in entities}

    for (group, subgroup, cmd_internal), new_name in overrides.items():
        key = (group, subgroup, cmd_internal)
        if key not in entity_map:
            continue

        is_grp, entity = entity_map[key]
        if entity.name == new_name:
            continue

        old_name = entity.name

        # Update discord.py internal children mapping dictionary
        if entity.parent and hasattr(entity.parent, '_children'):
            parent_children = entity.parent._children
            if old_name in parent_children:
                del parent_children[old_name]
            parent_children[new_name] = entity
        else:
            # Top-level entity under Tree root (guild_id=None for global commands)
            global_children = tree._children.get(None, {})
            if old_name in global_children:
                del global_children[old_name]
            global_children[new_name] = entity

        # Update entity name
        entity.name = new_name
        applied += 1
        log.info("ReSlasher: renamed /%s -> '%s'", " ".join(filter(None, key)), new_name)

    return applied, errors


class ReSlasherCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._original_sync = None

    async def apply_database_overrides(self):
        """Fetch and apply database overrides immediately across all tree commands."""
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
                    log.info("ReSlasher: applied %d override(s)", applied)
                if errors:
                    for err in errors:
                        log.warning("ReSlasher: %s", err)
        except Exception:
            log.warning("ReSlasher: failed to apply overrides", exc_info=True)

    def _patch_sync(self):
        """Monkey-patch tree.sync to apply overrides immediately before syncing with Discord's API."""
        if self._original_sync is not None:
            return

        self._original_sync = self.bot.tree.sync

        async def patched_sync(guild=None):
            # Apply overrides right before sync call executes
            await self.apply_database_overrides()
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
        """Sync registry and patch tree.sync on startup after all cogs have loaded."""
        await self.apply_database_overrides()
        created = await sync_registry(self.bot.tree)
        log.info("ReSlasher: synced command tree to registry (%d new entries)", created)
        self._patch_sync()

    async def cog_unload(self):
        self._unpatch_sync()


async def setup(bot: "BallsDexBot") -> None:
    cog = ReSlasherCog(bot)
    await bot.add_cog(cog)

    if bot.is_ready():
        await cog.apply_database_overrides()
        created = await sync_registry(bot.tree)
        log.info("ReSlasher: eagerly synced registry (%d new)", created)
        cog._patch_sync()

    log.info("ReSlasherCog loaded")


async def teardown(bot: "BallsDexBot") -> None:
    pass
