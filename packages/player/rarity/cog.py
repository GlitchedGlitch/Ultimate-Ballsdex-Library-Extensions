"""
Rarity package for BallsDex.

Adds /{players_group} rarity — shows the rarity list of all enabled balls.

Features:
  - search: by ball name OR rarity value on the same parameter
  - reverse: sort highest to lowest
  - ephemeral: show only to you
  - BallsDex FieldPageSource/Pages paginator
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import Ball
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.settings import settings

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


def build_rarity_command(bot: "BallsDexBot") -> app_commands.Command:
    """Build the rarity command as a standalone Command to attach to the Players group."""

    @app_commands.command(
        name="rarity",
        description="Check the rarity list of the bot",
    )
    @app_commands.describe(
        search=f"Search a specific {settings.collectible_name}'s rarity",
        reverse="Reverse the output of the rarity list",
        ephemeral="Whether or not to send the command ephemerally.",
    )
    async def rarity(
        interaction: discord.Interaction,
        search: str | None = None,
        reverse: bool = False,
        ephemeral: bool = False,
    ):
        name = settings.collectible_name.capitalize()
        plural = settings.plural_collectible_name.capitalize()

        balls: list[Ball] = [b for b in await Ball.all() if b.enabled]

        if not balls:
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
                matches = [b for b in balls if float(b.rarity) == rarity_value]

                if not matches:
                    await interaction.response.send_message(
                        f"There are no {settings.collectible_name} "
                        f"with rarity `{search}`.",
                        ephemeral=True,
                    )
                    return

                lines = [
                    f"{_ball_emoji(bot, b)} {b.country}"
                    for b in matches
                ]
                await interaction.response.send_message(
                    f"{plural} with rarity `{search}`:\n" + "\n".join(lines),
                    ephemeral=True,
                )
                return
            except ValueError:
                pass

            # Try exact ball name, then partial
            match = next(
                (b for b in balls if b.country.lower() == search.lower()), None
            )
            if not match:
                match = next(
                    (b for b in balls if search.lower() in b.country.lower()), None
                )
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

        rarity_map: dict[float, list[Ball]] = defaultdict(list)
        for b in balls:
            rarity_map[float(b.rarity)].append(b)

        sorted_rarities = sorted(rarity_map.keys(), reverse=reverse)

        entries: list[tuple[str, str]] = []
        for r in sorted_rarities:
            group_balls = rarity_map[r]
            lines = [
                f"⋄ {_ball_emoji(bot, b)} {b.country}"
                for b in group_balls
            ]
            entries.append((f"∥ Rarity: {r}", "\n".join(lines)))

        total_pages = -(-len(entries) // GROUPS_PER_PAGE)

        source = FieldPageSource(entries, per_page=GROUPS_PER_PAGE, inline=False)
        source.embed.title = f"{plural} Rarity List"
        source.embed.color = 0XFFFFFF

        pages = Pages(source, interaction=interaction)
        await pages.start(ephemeral=ephemeral)

    @rarity.autocomplete("search")
    async def rarity_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        balls: list[Ball] = await Ball.all()
        results: list[app_commands.Choice[str]] = []
        for b in balls:
            if not b.enabled:
                continue
            if current.lower() in b.country.lower():
                results.append(app_commands.Choice(name=b.country, value=b.country))
            if len(results) >= 25:
                break
        return results

    return rarity


class RarityCog(commands.Cog):
    """Rarity package — displays the ball rarity list."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
