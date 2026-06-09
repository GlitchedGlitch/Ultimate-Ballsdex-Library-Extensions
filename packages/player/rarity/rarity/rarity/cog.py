"""
Rarity package for BallsDex v3 :333
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import ActionRow, Button, button

from bd_models.models import Ball, balls as balls_cache
from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import Menu
from ballsdex.core.utils.menus.source import ListSource
from ballsdex.core.utils.menus.formatter import ItemFormatter
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.rarity")

# How many rarity groups to show per page
GROUPS_PER_PAGE = 7


def _ball_emoji(bot: "BallsDexBot", ball: Ball) -> str:
    if ball.emoji_id:
        emoji = bot.get_emoji(ball.emoji_id)
        if emoji:
            return str(emoji)
    return "⋄"


class RarityCog(commands.Cog):
    """Rarity package — displays the ball rarity list."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot


class RarityItemFormatter(ItemFormatter):
    """Custom ItemFormatter that properly clears items between pages while keeping controls."""
    
    async def format_page(self, page):
        # Find the index where controls start (they're at the end after position)
        # We want to remove only the content items, not the control buttons
        children_list = list(self.item.children)
        
        # Remove items after position, but keep ActionRows (which contain the quit button)
        items_to_remove = []
        for i, child in enumerate(children_list[self.position:], start=self.position):
            # Keep ActionRows (they contain the control buttons)
            if not isinstance(child, ActionRow):
                items_to_remove.append(child)
        
        for item in items_to_remove:
            self.item.remove_item(item)
        
        # Add new page items
        for section in page:
            self.item.add_item(section)
        
        # Add footer
        if self.footer and self.menu.source.get_max_pages() > 1:
            self.item.add_item(
                discord.ui.TextDisplay(f"-# Page {self.menu.current_page + 1}/{self.menu.source.get_max_pages()}")
            )


class QuitButtonRow(ActionRow):
    """Quit button for rarity pagination."""
    
    def __init__(self, menu):
        super().__init__()
        self.menu = menu
    
    @button(label="Quit", style=discord.ButtonStyle.danger)
    async def quit_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        for item in self.menu.view.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore
        await interaction.edit_original_response(view=self.menu.view)


def build_rarity_command(bot: "BallsDexBot") -> app_commands.Command:
    """
    Build the rarity command as a standalone Command to attach to the Balls group.
    Mirrors the v2 factory pattern so __init__.py can attach it the same way.
    """

    @app_commands.command(
        name="rarity",
        description="Check the rarity list of the bot",
    )
    @app_commands.describe(
        search=f"Search a specific {settings.collectible_name}'s rarity",
        reverse="Reverse the output of the rarity list",
        ephemeral="Whether or not to send the command ephemerally",
    )
    async def rarity(
        interaction: discord.Interaction,
        search: str | None = None,
        reverse: bool = False,
        ephemeral: bool = False,
    ):
        plural = settings.plural_collectible_name.capitalize()

        # Fetch all enabled balls from Django ORM
        all_balls: list[Ball] = [b async for b in Ball.objects.filter(enabled=True)]

        if not all_balls:
            await interaction.response.send_message(
                f"No {settings.plural_collectible_name} are currently enabled.",
                ephemeral=True,
            )
            return

        # ── Search mode ───────────────────────────────────────────────────────
        if search:
            # Try rarity value first
            try:
                rarity_value = float(search.replace(",", "."))
                matches = [b for b in all_balls if float(b.rarity) == rarity_value]
                if not matches:
                    await interaction.response.send_message(
                        f"There are no {settings.collectible_name} with rarity `{search}`.",
                        ephemeral=True,
                    )
                    return
                lines = [f"{_ball_emoji(bot, b)} {b.country}" for b in matches]
                await interaction.response.send_message(
                    f"{plural} with rarity `{search}`:\n" + "\n".join(lines),
                    ephemeral=True,
                )
                return
            except ValueError:
                pass

            # Try exact then partial ball name
            match = next((b for b in all_balls if b.country.lower() == search.lower()), None)
            if not match:
                match = next((b for b in all_balls if search.lower() in b.country.lower()), None)
            if not match:
                await interaction.response.send_message(
                    f"No {settings.collectible_name} found matching `{search}`.",
                    ephemeral=True,
                )
                return

            emoji = _ball_emoji(bot, match)
            await interaction.response.send_message(
                f"{emoji} **{match.country}**\nRarity: `{match.rarity}`",
                ephemeral=True,
            )
            return

        # ── Full paginated list ───────────────────────────────────────────────
        await interaction.response.defer(ephemeral=ephemeral)

        # Group balls by rarity value
        rarity_map: dict[float, list[Ball]] = defaultdict(list)
        for b in all_balls:
            rarity_map[float(b.rarity)].append(b)

        sorted_rarities = sorted(rarity_map.keys(), reverse=reverse)

        # Build one TextDisplay per rarity group, then chunk into pages
        all_items: list[discord.ui.Item] = []
        for r in sorted_rarities:
            group_balls = rarity_map[r]
            lines = "\n".join(
                f"⋄ {_ball_emoji(bot, b)} {b.country}" for b in group_balls
            )
            all_items.append(discord.ui.TextDisplay(f"**∥ Rarity: {r}**\n{lines}"))

        if not all_items:
            await interaction.followup.send(
                f"No {settings.plural_collectible_name} are currently enabled.",
                ephemeral=ephemeral,
            )
            return

        # Chunk into pages of GROUPS_PER_PAGE
        pages: list[list[discord.ui.Item]] = [
            all_items[i : i + GROUPS_PER_PAGE]
            for i in range(0, len(all_items), GROUPS_PER_PAGE)
        ]

        # Build the LayoutView with a Container
        view = LayoutView()
        container = discord.ui.Container()

        # Title section — always visible, position 0
        container.add_item(discord.ui.TextDisplay(f"# {plural} Rarity List"))
        container.add_item(discord.ui.Separator())

        view.add_item(container)

        source = ListSource(pages)
        # Items are inserted at position 2 (after title + separator)
        formatter = RarityItemFormatter(container, position=2)
        menu = Menu(bot, view, source, formatter)
        
        # Initialize menu, buttons will be added to the view (outside container)
        await menu.init(container=container, position=3)
        
        # Add quit button at the bottom of the container (after controls)
        quit_button_row = QuitButtonRow(menu)
        container.add_item(quit_button_row)

        await interaction.followup.send(view=view, ephemeral=ephemeral)

    @rarity.autocomplete("search")
    async def rarity_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        results: list[app_commands.Choice[str]] = []
        async for b in Ball.objects.filter(enabled=True, country__icontains=current).order_by("country"):
            results.append(app_commands.Choice(name=b.country, value=b.country))
            if len(results) >= 25:
                break
        return results

    return rarity
