"""
Rarity package for BallsDex.

Adds /{players_group} rarity — shows the rarity list of all enabled balls,
with search (by name or rarity value), reverse sort, ephemeral toggle,
and BallsDex's built-in FieldPageSource/Pages paginator.
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

GROUPS_PER_PAGE = 5


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

    @app_commands.command(
        name="rarity",
        description="Shows the rarity list",
    )
    @app_commands.describe(
        search="Search by ball name or rarity value",
        reverse="Reverse the output of the list",
        ephemeral="Whether show the list ephemerally",
    )
    async def rarity(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        search: str | None = None,
        reverse: bool = False,
        ephemeral: bool = False,
    ):
        name = settings.collectible_name.capitalize()
        plural = settings.plural_collectible_name.capitalize()

        # Fetch all enabled balls
        balls: list[Ball] = [b for b in await Ball.all() if b.enabled]

        if not balls:
            await interaction.response.send_message(
                f"No {plural.lower()} are currently enabled.", ephemeral=True
            )
            return

        # ── Search mode ───────────────────────────────────────────────────────
        if search:
            # Try rarity value first
            try:
                rarity_value = float(search.replace(",", "."))
                matches = [b for b in balls if float(b.rarity) == rarity_value]
                if matches:
                    lines = [
                        f"⋄ {_ball_emoji(self.bot, b)} {b.country}"
                        for b in matches
                    ]
                    embed = discord.Embed(
                        title=f"{plural} with rarity `{search}`",
                        description="\n".join(lines),
                        color=0x40E0D0,
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            except ValueError:
                pass

            # Try ball name
            match = next(
                (b for b in balls if b.country.lower() == search.lower()), None
            )
            if not match:
                # Partial match fallback
                match = next(
                    (b for b in balls if search.lower() in b.country.lower()), None
                )
            if not match:
                await interaction.response.send_message(
                    f"No {name.lower()} found matching `{search}`.", ephemeral=True
                )
                return

            emoji = _ball_emoji(self.bot, match)
            embed = discord.Embed(
                title=f"{emoji} {match.country}",
                description=f"Rarity: `{match.rarity}`",
                color=0x40E0D0,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # ── Full paginated list ───────────────────────────────────────────────
        await interaction.response.defer(ephemeral=ephemeral)

        # Group balls by rarity
        rarity_map: dict[float, list[Ball]] = defaultdict(list)
        for b in balls:
            rarity_map[float(b.rarity)].append(b)

        sorted_rarities = sorted(rarity_map.keys(), reverse=reverse)

        # Build (field_name, field_value) entries for FieldPageSource
        entries: list[tuple[str, str]] = []
        for rarity in sorted_rarities:
            group_balls = rarity_map[rarity]
            lines = [
                f"⋄ {_ball_emoji(self.bot, b)} {b.country}"
                for b in group_balls
            ]
            entries.append((f"Rarity: {rarity}", "\n".join(lines)))

        sort_label = "Highest → Lowest" if reverse else "Lowest → Highest"
        total_pages = -(-len(entries) // GROUPS_PER_PAGE)

        source = FieldPageSource(entries, per_page=GROUPS_PER_PAGE, inline=False)
        source.embed.title = f"{plural} Rarity List"
        source.embed.color = 0x40E0D0

        if total_pages > 1:
            source.embed.set_footer(
                text=f"{len(balls)} {plural.lower()} • Sorted: {sort_label}"
            )
        else:
            source.embed.set_footer(text=f"{len(balls)} {plural.lower()}")

        pages = Pages(source, interaction=interaction)
        await pages.start(ephemeral=ephemeral)

    @rarity.autocomplete("search")
    async def rarity_autocomplete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
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
