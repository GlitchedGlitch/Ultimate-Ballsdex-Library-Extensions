"""
Collector package for BallsDex.

Adds five commands:
  /collector claim  — players claim a collector version of a ball if they meet requirements.
  /collector list   — paginated embed list of all active collector requirements.
  /admin collector set    — bot admins set a collector requirement and reward.
  /admin collector delete — bot admins delete a collector requirement.
  /admin collector view   — bot admins inspect a specific requirement.

Requirements are stored on the bot object so they persist across cog reloads.
"""

from __future__ import annotations

import logging
from itertools import groupby
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import BallInstance, Player, Special
from ballsdex.core.utils.menus import (
    ItemFormatter,
    Menu,
    dynamic_chunks,
    iter_to_async,
)
from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")

GROUPS_PER_PAGE = 7


def _get_ball_emoji(bot: "BallsDexBot", ball_id: int) -> str:
    """Try to resolve the ball's Discord emoji, fall back to a plain bullet."""
    from ballsdex.core.models import balls as balls_cache
    ball = balls_cache.get(ball_id)
    if ball and ball.emoji_id:
        emoji = bot.get_emoji(ball.emoji_id)
        if emoji:
            return str(emoji)
    return "•"


async def _generate_list_items(
    bot: "BallsDexBot",
    grouped: dict[int, list[dict]],
    sorted_amounts: list[int],
):
    """Yield TextDisplay items for each minimum-amount group."""
    for amount in sorted_amounts:
        entries = grouped[amount]
        lines = [f"**Minimum: {amount}**"]
        for req in entries:
            emoji = _get_ball_emoji(bot, req["ball_id"])
            lines.append(f"* {emoji} {req['ball_name']}")
        yield discord.ui.TextDisplay("\n".join(lines))
        yield discord.ui.Separator()


class CollectorCog(commands.Cog):
    """Collector package — lets players claim special collector versions of balls."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        # Store on the bot object so data survives cog reloads
        if not hasattr(bot, "collector_requirements"):
            bot.collector_requirements: dict[int, dict] = {}
        if not hasattr(bot, "collector_claimed"):
            bot.collector_claimed: dict[int, set[int]] = {}

    # ── /collector (group) ────────────────────────────────────────────────────

    collector_group = app_commands.Group(
        name="collector",
        description="Collector commands",
    )

    # ── /admin collector (group) ──────────────────────────────────────────────

    admin_group = app_commands.Group(
        name="admin",
        description="Admin commands",
        default_permissions=discord.Permissions(administrator=True),
    )
    admin_collector_group = app_commands.Group(
        name="collector",
        description="Manage collector requirements",
        parent=admin_group,
        default_permissions=discord.Permissions(administrator=True),
    )

    # ── /collector claim ──────────────────────────────────────────────────────

    @collector_group.command(name="claim", description="Claim your collector ball reward")
    @app_commands.describe(
        countryball="The ball you want to claim a collector version of",
    )
    async def collector_claim(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        await interaction.response.defer(ephemeral=True)

        ball = countryball
        ball_id = ball.pk
        requirements = self.bot.collector_requirements
        claimed = self.bot.collector_claimed

        if ball_id not in requirements:
            await interaction.followup.send(
                f"There is no collector requirement set for **{ball.country}**.",
                ephemeral=True,
            )
            return

        req = requirements[ball_id]
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        already_claimed = claimed.get(ball_id, set())
        if interaction.user.id in already_claimed:
            await interaction.followup.send(
                f"You have already claimed your collector **{ball.country}**!",
                ephemeral=True,
            )
            return

        count = await BallInstance.filter(
            player=player,
            ball=ball,
            deleted=False,
        ).count()

        required_amount = req["amount"]
        if count < required_amount:
            await interaction.followup.send(
                f"You need at least **{required_amount}** {ball.country} "
                f"to claim a collector version, but you only have **{count}**.",
                ephemeral=True,
            )
            return

        special = await Special.get_or_none(pk=req["special_id"])
        if special is None:
            await interaction.followup.send(
                "The collector reward special no longer exists. Please contact an admin.",
                ephemeral=True,
            )
            log.error(
                "Collector special ID %d for ball %s not found in DB.",
                req["special_id"],
                ball.country,
            )
            return

        new_instance = await BallInstance.create(
            player=player,
            ball=ball,
            special=special,
            attack_bonus=0,
            health_bonus=0,
            server_id=interaction.guild_id,
        )

        claimed.setdefault(ball_id, set()).add(interaction.user.id)

        log.info(
            "User %s (%d) claimed collector %s with special %s (instance #%X).",
            interaction.user,
            interaction.user.id,
            ball.country,
            special.name,
            new_instance.pk,
        )

        collectible = settings.collectible_name
        emoji_str = special.emoji or ""
        await interaction.followup.send(
            f"🎉 Congratulations! You have claimed your "
            f"**{emoji_str} {special.name} {ball.country}** "
            f"collector {collectible}!\n"
            f"It has been added to your collection as `#{new_instance.pk:0X}`.",
            ephemeral=True,
        )

    # ── /collector list ───────────────────────────────────────────────────────

    @collector_group.command(
        name="list",
        description="List all active collector requirements",
    )
    @app_commands.describe(
        reverse="Sort from highest to lowest amount instead of lowest to highest",
    )
    async def collector_list(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        reverse: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        requirements = self.bot.collector_requirements

        if not requirements:
            await interaction.followup.send(
                "There are no collector requirements set up yet.",
                ephemeral=True,
            )
            return

        collectible = settings.collectible_name

        # Group requirements by amount, sorted low→high (or reversed)
        all_reqs = sorted(
            requirements.values(),
            key=lambda r: r["amount"],
            reverse=reverse,
        )
        grouped: dict[int, list[dict]] = {}
        for req in all_reqs:
            grouped.setdefault(req["amount"], []).append(req)
        sorted_amounts = list(grouped.keys())

        # Split sorted_amounts into pages of GROUPS_PER_PAGE
        amount_pages = [
            sorted_amounts[i : i + GROUPS_PER_PAGE]
            for i in range(0, len(sorted_amounts), GROUPS_PER_PAGE)
        ]
        total_pages = len(amount_pages)
        sort_label = "Highest → Lowest" if reverse else "Lowest → Highest"

        # Build one embed per page
        pages: list[discord.Embed] = []
        for page_num, page_amounts in enumerate(amount_pages, start=1):
            embed = discord.Embed(
                title="🏆 Collector List",
                color=discord.Color.gold(),
            )
            embed.set_footer(
                text=(
                    f"Page {page_num}/{total_pages} • "
                    f"{len(requirements)} requirement(s) • "
                    f"Sorted: {sort_label}"
                )
            )

            for amount in page_amounts:
                entries = grouped[amount]
                ball_lines = []
                for req in entries:
                    emoji = _get_ball_emoji(self.bot, req["ball_id"])
                    reward_emoji = ""
                    # Try to get reward special emoji
                    special_name = req["special_name"]
                    # Look for emoji in special data if we can
                    ball_lines.append(f"* {emoji} {req['ball_name']} → *{special_name}*")

                embed.add_field(
                    name=f"Minimum: {amount}",
                    value="\n".join(ball_lines),
                    inline=False,
                )

            pages.append(embed)

        if total_pages == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
            return

        # Multi-page: use a simple previous/next view
        class PaginatorView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.page = 0
                self.message: discord.WebhookMessage | None = None
                self._update_buttons()

            def _update_buttons(self):
                self.prev_button.disabled = self.page == 0
                self.next_button.disabled = self.page == total_pages - 1

            async def on_timeout(self):
                for child in self.children:
                    child.disabled = True
                if self.message:
                    try:
                        await self.message.edit(view=self)
                    except Exception:
                        pass

            async def interaction_check(self, itx: discord.Interaction) -> bool:
                if itx.user.id != interaction.user.id:
                    await itx.response.send_message(
                        "This menu is not for you.", ephemeral=True
                    )
                    return False
                return True

            @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
            async def prev_button(self, itx: discord.Interaction, button: discord.ui.Button):
                self.page -= 1
                self._update_buttons()
                await itx.response.edit_message(embed=pages[self.page], view=self)

            @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
            async def next_button(self, itx: discord.Interaction, button: discord.ui.Button):
                self.page += 1
                self._update_buttons()
                await itx.response.edit_message(embed=pages[self.page], view=self)

        view = PaginatorView()
        msg = await interaction.followup.send(
            embed=pages[0], view=view, ephemeral=True, wait=True
        )
        view.message = msg

    # ── /admin collector set ──────────────────────────────────────────────────

    @admin_collector_group.command(
        name="set",
        description="Set or update a collector requirement for a ball",
    )
    @app_commands.describe(
        countryball="The ball to set a collector requirement for",
        amount="Minimum number of this ball the player must own to claim",
        special="The special event reward the player receives upon claiming",
    )
    async def admin_collector_set(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
        amount: app_commands.Range[int, 1, 9999],
        special: SpecialTransform,
    ):
        if interaction.user.id not in self.bot.owner_ids:
            await interaction.response.send_message(
                "Only bot admins can manage collector requirements.",
                ephemeral=True,
            )
            return

        ball = countryball
        ball_id = ball.pk

        self.bot.collector_requirements[ball_id] = {
            "ball_id": ball_id,
            "ball_name": ball.country,
            "amount": amount,
            "special_id": special.pk,
            "special_name": special.name,
        }
        self.bot.collector_claimed.pop(ball_id, None)

        collectible = settings.collectible_name
        await interaction.response.send_message(
            f"✅ Collector requirement set:\n"
            f"**{ball.country}** — own ≥ **{amount}** {collectible}(s) "
            f"→ reward **{special.name}** special.\n"
            f"Previous claims for this ball have been reset.",
            ephemeral=True,
        )
        log.info(
            "Admin %s set collector requirement: ball=%s amount=%d special=%s",
            interaction.user,
            ball.country,
            amount,
            special.name,
        )

    # ── /admin collector delete ───────────────────────────────────────────────

    @admin_collector_group.command(
        name="delete",
        description="Delete a collector requirement for a ball",
    )
    @app_commands.describe(
        countryball="The ball whose collector requirement you want to remove",
    )
    async def admin_collector_delete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        if interaction.user.id not in self.bot.owner_ids:
            await interaction.response.send_message(
                "Only bot admins can manage collector requirements.",
                ephemeral=True,
            )
            return

        ball = countryball
        ball_id = ball.pk

        if ball_id not in self.bot.collector_requirements:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.",
                ephemeral=True,
            )
            return

        del self.bot.collector_requirements[ball_id]
        self.bot.collector_claimed.pop(ball_id, None)

        await interaction.response.send_message(
            f"🗑️ Collector requirement for **{ball.country}** has been deleted.",
            ephemeral=True,
        )
        log.info(
            "Admin %s deleted collector requirement for ball=%s",
            interaction.user,
            ball.country,
        )

    # ── /admin collector view ─────────────────────────────────────────────────

    @admin_collector_group.command(
        name="view",
        description="View the collector requirement for a specific ball",
    )
    @app_commands.describe(
        countryball="The ball to inspect",
    )
    async def admin_collector_view(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        if interaction.user.id not in self.bot.owner_ids:
            await interaction.response.send_message(
                "Only bot admins can view collector requirements.",
                ephemeral=True,
            )
            return

        ball = countryball
        ball_id = ball.pk

        if ball_id not in self.bot.collector_requirements:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.",
                ephemeral=True,
            )
            return

        req = self.bot.collector_requirements[ball_id]
        claimed_count = len(self.bot.collector_claimed.get(ball_id, set()))

        await interaction.response.send_message(
            f"**Collector Requirement — {ball.country}**\n"
            f"• Minimum amount: **{req['amount']}**\n"
            f"• Reward special: **{req['special_name']}** (ID: {req['special_id']})\n"
            f"• Claims this session: **{claimed_count}**",
            ephemeral=True,
        )
