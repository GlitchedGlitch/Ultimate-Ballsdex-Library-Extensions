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

from .rarity_settings import load_settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.rarity")

GROUPS_PER_PAGE = 7


def _ball_emoji(bot: "BallsDexBot", ball: Ball) -> str:
    if ball.emoji_id:
        emoji = bot.get_emoji(ball.emoji_id)
        if emoji:
            return str(emoji)
    return "⋄"


def _hex_to_color(hex_str: str) -> discord.Color | None:
    hex_str = hex_str.strip().lstrip("#")
    if not hex_str:
        return None
    try:
        return discord.Color(int(hex_str, 16))
    except ValueError:
        return None


class RarityCog(commands.Cog):
    """Rarity package — displays the ball rarity list."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot


class RarityItemFormatter(ItemFormatter):
    async def format_page(self, page):
        children = list(self.item.children)

        # Keep header items
        fixed_top = children[: self.position]

        # Keep button rows
        button_rows = [
            child
            for child in children
            if isinstance(child, ActionRow)
        ]

        # Remove everything
        for child in children[self.position:]:
            self.item.remove_item(child)

        # Re-add page content first
        for section in page:
            self.item.add_item(section)

        # Footer before buttons or somethinv
        if self.footer and self.menu.source.get_max_pages() > 1:
            self.item.add_item(
                discord.ui.TextDisplay(
                    f"-# Page {self.menu.current_page + 1}/{self.menu.source.get_max_pages()}"
                )
            )

        # Buttons at the end of the page (i suffered much trying to fix this)
        for row in button_rows:
            self.item.add_item(row)


class RarityView(LayoutView):
    """Custom view with permission checking."""

    def __init__(self, user_id: int, *, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You are not allowed to interact with this.",
                ephemeral=True
            )
            return False
        return True


class QuitButtonRow(ActionRow):
    """Quit button row"""

    def __init__(self, rarity_view: RarityView):
        super().__init__()
        self.rarity_view = rarity_view

    @button(label="Quit", style=discord.ButtonStyle.danger)
    async def quit_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        for item in self.rarity_view.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore
        await interaction.edit_original_response(view=self.rarity_view)


class GoToPageModal(discord.ui.Modal, title="Go to page"):
    page = discord.ui.TextInput(label="Page", placeholder="Enter a number", min_length=1)

    def __init__(self, paginator: "EmbedPaginatorView"):
        super().__init__()
        self.paginator = paginator
        as_string = str(len(paginator.pages))
        self.page.placeholder = f"Enter a number between 1 and {as_string}"
        self.page.max_length = len(as_string)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page.value)
        except ValueError:
            await interaction.response.send_message("Expected a number", ephemeral=True)
            return
        if page < 1:
            await interaction.response.send_message("Minimum value is 1", ephemeral=True)
        elif page > len(self.paginator.pages):
            await interaction.response.send_message(
                f"Maximum value is {len(self.paginator.pages)}", ephemeral=True
            )
        else:
            await self.paginator.show_page(interaction, page - 1)


class EmbedPaginatorView(discord.ui.View):
    """
    buttons like v2 but v3 buttons so v2 v3 yes
    """

    def __init__(
        self,
        user_id: int,
        pages: list[discord.Embed],
        buttons_inside: bool,
        *,
        timeout: float | None = 180,
    ):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.pages = pages
        self.current_page = 0
        self.buttons_inside = buttons_inside
        self._build()

    def _build(self):
        self.clear_items()
        multi_page = len(self.pages) > 1

        if multi_page:
            self.first_btn = Button(label="≪", style=discord.ButtonStyle.grey)
            self.first_btn.callback = self._go_first
            self.add_item(self.first_btn)

            self.prev_btn = Button(label="Back", style=discord.ButtonStyle.blurple)
            self.prev_btn.callback = self._go_prev
            self.add_item(self.prev_btn)

            self.goto_btn = Button(
                label=f"{self.current_page + 1} (go to)", style=discord.ButtonStyle.blurple
            )
            self.goto_btn.callback = self._go_to
            self.add_item(self.goto_btn)

            self.next_btn = Button(label="Next", style=discord.ButtonStyle.blurple)
            self.next_btn.callback = self._go_next
            self.add_item(self.next_btn)

            self.last_btn = Button(label="≫", style=discord.ButtonStyle.grey)
            self.last_btn.callback = self._go_last
            self.add_item(self.last_btn)

            self._edit_buttons()

        quit_btn = Button(label="Quit", style=discord.ButtonStyle.danger)
        quit_btn.callback = self._quit
        self.add_item(quit_btn)

    def _edit_buttons(self):
        max_page = len(self.pages)
        self.goto_btn.label = f"{self.current_page + 1} (go to)"

        if self.current_page > 0:
            self.prev_btn.label = str(self.current_page)
            self.prev_btn.disabled = False
            self.first_btn.disabled = False
        else:
            self.prev_btn.label = "Back"
            self.prev_btn.disabled = True
            self.first_btn.disabled = True

        if self.current_page < max_page - 1:
            self.next_btn.label = str(self.current_page + 2)
            self.next_btn.disabled = False
            self.last_btn.disabled = False
        else:
            self.next_btn.label = "Next"
            self.next_btn.disabled = True
            self.last_btn.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You are not allowed to interact with this.", ephemeral=True
            )
            return False
        return True

    async def show_page(self, interaction: discord.Interaction, page: int):
        self.current_page = page
        self._edit_buttons()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=self.pages[page], view=self)
        else:
            await interaction.response.edit_message(embed=self.pages[page], view=self)

    async def _go_first(self, interaction: discord.Interaction):
        await self.show_page(interaction, 0)

    async def _go_prev(self, interaction: discord.Interaction):
        await self.show_page(interaction, self.current_page - 1)

    async def _go_to(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GoToPageModal(self))

    async def _go_next(self, interaction: discord.Interaction):
        await self.show_page(interaction, self.current_page + 1)

    async def _go_last(self, interaction: discord.Interaction):
        await self.show_page(interaction, len(self.pages) - 1)

    async def _quit(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True  # type: ignore
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True  # type: ignore


def build_rarity_command(bot: "BallsDexBot") -> app_commands.Command:
    """
    Build the rarity command as a standalone Command to attach to the Balls group
    Mirrors the v2 factory pattern so __init__.py can attach it the same way
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
        pkg_settings = load_settings()

        all_balls: list[Ball] = [b async for b in Ball.objects.filter(enabled=True)]

        if not all_balls:
            await interaction.response.send_message(
                f"No {settings.plural_collectible_name} are currently enabled.",
                ephemeral=True,
            )
            return

        # ── Search mode ───────────────────────────────────────────────────────
        if search:

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

        await interaction.response.defer(ephemeral=ephemeral)

        rarity_map: dict[float, list[Ball]] = defaultdict(list)
        for b in all_balls:
            rarity_map[float(b.rarity)].append(b)

        sorted_rarities = sorted(rarity_map.keys(), reverse=reverse)

        line_color = _hex_to_color(pkg_settings["embed_color"])
        use_embed_style = pkg_settings["style"] == "embed"
        buttons_inside = pkg_settings["buttons_inside"] == "true"

        if not sorted_rarities:
            await interaction.followup.send(
                f"No {settings.plural_collectible_name} are currently enabled.",
                ephemeral=ephemeral,
            )
            return

        if use_embed_style:

            entries: list[tuple[str, str]] = []
            for r in sorted_rarities:
                group_balls = rarity_map[r]
                lines = "\n".join(
                    f"⋄ {_ball_emoji(bot, b)} {b.country}" for b in group_balls
                )
                entries.append((f"∥ Rarity: {r}", lines))

            chunks = [
                entries[i : i + GROUPS_PER_PAGE]
                for i in range(0, len(entries), GROUPS_PER_PAGE)
            ]
            total_pages = len(chunks)

            embed_pages: list[discord.Embed] = []
            for page_num, chunk in enumerate(chunks, start=1):
                e = discord.Embed(
                    title=f"{settings.bot_name} Rarity List",
                    color=line_color if line_color is not None else discord.Color(0xFFFFFF),
                )
                for name, value in chunk:
                    e.add_field(name=name, value=value, inline=False)
                if total_pages > 1:
                    e.set_footer(text=f"Page {page_num}/{total_pages}")
                embed_pages.append(e)

            view = EmbedPaginatorView(interaction.user.id, embed_pages, buttons_inside)

            await interaction.followup.send(
                embed=embed_pages[0], view=view, ephemeral=ephemeral
            )
            return

        all_items: list[discord.ui.Item] = []
        for r in sorted_rarities:
            group_balls = rarity_map[r]
            lines = "\n".join(
                f"⋄ {_ball_emoji(bot, b)} {b.country}" for b in group_balls
            )
            all_items.append(discord.ui.TextDisplay(f"**∥ Rarity: {r}**\n{lines}"))

        pages: list[list[discord.ui.Item]] = [
            all_items[i : i + GROUPS_PER_PAGE]
            for i in range(0, len(all_items), GROUPS_PER_PAGE)
        ]

        view = RarityView(interaction.user.id)
        container = discord.ui.Container()
        if line_color is not None:

            container.accent_color = line_color

        title_text = f"# {settings.bot_name} Rarity List"
        container.add_item(discord.ui.TextDisplay(title_text))
        container.add_item(discord.ui.Separator())
        header_item_count = 2 

        view.add_item(container)

        source = ListSource(pages)
        formatter = RarityItemFormatter(container, position=header_item_count)
        menu = Menu(bot, view, source, formatter)

        await menu.init(container=container, position=header_item_count)

        quit_row = QuitButtonRow(view)

        if buttons_inside:

            container.add_item(quit_row)
        else:

            for child in list(container.children):
                if isinstance(child, ActionRow):
                    container.remove_item(child)
                    view.add_item(child)
            view.add_item(quit_row)

        first_page = await source.get_page(0)
        await formatter.format_page(first_page)

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
