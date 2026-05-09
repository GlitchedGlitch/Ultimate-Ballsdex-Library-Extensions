"""
Collector package for BallsDex.

Adds two commands:
  /collector claim  — players claim a collector version of a ball if they meet requirements.
  /collector list   — lists all active collector requirements.
  /admin collector set    — bot admins set a collector requirement and reward.
  /admin collector delete — bot admins delete a collector requirement.
  /admin collector view   — bot admins inspect a specific requirement.

Requirements are stored on the bot object so they persist across cog reloads.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import BallInstance, Player, Special
from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")


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

        # Check requirement exists
        if ball_id not in requirements:
            await interaction.followup.send(
                f"There is no collector requirement set for **{ball.country}**.",
                ephemeral=True,
            )
            return

        req = requirements[ball_id]

        # Get or create player
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        # Check if already claimed
        already_claimed = claimed.get(ball_id, set())
        if interaction.user.id in already_claimed:
            await interaction.followup.send(
                f"You have already claimed your collector **{ball.country}**!",
                ephemeral=True,
            )
            return

        # Count how many of this ball the player owns
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

        # Fetch the reward Special
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

        # Award — create a new BallInstance with the special
        new_instance = await BallInstance.create(
            player=player,
            ball=ball,
            special=special,
            attack_bonus=0,
            health_bonus=0,
            server_id=interaction.guild_id,
        )

        # Mark as claimed
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
            f"Congratulations! You have claimed your "
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
    async def collector_list(self, interaction: discord.Interaction["BallsDexBot"]):
        await interaction.response.defer(ephemeral=True)

        requirements = self.bot.collector_requirements

        if not requirements:
            await interaction.followup.send(
                "There are no collector requirements set up yet.",
                ephemeral=True,
            )
            return

        collectible = settings.collectible_name
        lines = [f"**Active Collector Requirements** ({len(requirements)} total)\n"]
        for req in requirements.values():
            lines.append(
                f"• **{req['ball_name']}** — own ≥ {req['amount']} {collectible}(s) → "
                f"reward: **{req['special_name']}** special"
            )

        await interaction.followup.send("\n".join(lines), ephemeral=True)

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
        # Reset claimed set when requirement changes
        self.bot.collector_claimed.pop(ball_id, None)

        collectible = settings.collectible_name
        await interaction.response.send_message(
            f"Collector requirement set:\n"
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
