"""
Collector package for BallsDex.

Adds two commands:
  /collector claim  — players claim a collector version of a ball if they meet requirements.
  /admin collector  — bot admins manage collector requirements and rewards.

Requirements are stored in-memory as a dict keyed by Ball.pk.
Each entry looks like:
    {
        "ball_id":   int,
        "ball_name": str,
        "amount":    int,       # minimum duplicates required
        "special_id": int,      # Special.pk to award
        "special_name": str,
    }

Players who have already claimed are tracked in a set per requirement to prevent
double-claiming within the same bot session. For persistent tracking across restarts
you would add a Django model — see the BallsDex wiki for guidance.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")

# ──────────────────────────────────────────────────────────────────────────────
# In-memory storage
# ──────────────────────────────────────────────────────────────────────────────

# collector_requirements: dict[ball_id -> requirement dict]
collector_requirements: dict[int, dict] = {}

# claimed_players: dict[ball_id -> set of discord user IDs that already claimed]
claimed_players: dict[int, set[int]] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _collectible_name() -> str:
    """Return the configured collectible name (cross-dex compatible)."""
    return settings.collectible_name


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class CollectorCog(commands.Cog):
    """Collector package — lets players claim special collector versions of balls."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

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
        countryball=f"The {_collectible_name()} you want to claim a collector version of",
    )
    async def collector_claim(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        """
        Claim a collector version of a ball if you meet the requirements.

        You must own at least the configured minimum number of that ball,
        and you can only claim once per ball.
        """
        await interaction.response.defer(ephemeral=True)

        ball = countryball
        ball_id = ball.pk

        # Check requirement exists
        if ball_id not in collector_requirements:
            await interaction.followup.send(
                f"There is no collector requirement set for **{ball.country}**.",
                ephemeral=True,
            )
            return

        req = collector_requirements[ball_id]

        # Check player exists in DB
        from bd_models.models import BallInstance, Player, Special

        try:
            player = await Player.objects.aget(discord_id=interaction.user.id)
        except Player.DoesNotExist:
            await interaction.followup.send(
                "You don't have a player profile yet. Catch some balls first!",
                ephemeral=True,
            )
            return

        # Check if already claimed this session
        already_claimed = claimed_players.get(ball_id, set())
        if interaction.user.id in already_claimed:
            await interaction.followup.send(
                f"You have already claimed your collector **{ball.country}**!",
                ephemeral=True,
            )
            return

        # Count how many of this ball the player owns
        count = await BallInstance.objects.filter(
            player=player,
            ball=ball,
            deleted=False,
        ).acount()

        required_amount = req["amount"]
        if count < required_amount:
            await interaction.followup.send(
                f"You need at least **{required_amount}** {ball.country} "
                f"to claim a collector version, but you only have **{count}**.",
                ephemeral=True,
            )
            return

        # Fetch the reward Special
        try:
            special = await Special.objects.aget(pk=req["special_id"])
        except Special.DoesNotExist:
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
        new_instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            special=special,
            attack_bonus=0,
            health_bonus=0,
            server_id=interaction.guild_id,
        )

        # Mark as claimed
        claimed_players.setdefault(ball_id, set()).add(interaction.user.id)

        log.info(
            "User %s (%d) claimed collector %s with special %s (instance #%X).",
            interaction.user,
            interaction.user.id,
            ball.country,
            special.name,
            new_instance.pk,
        )

        collectible = _collectible_name()
        emoji_str = special.emoji or ""
        await interaction.followup.send(
            f"🎉 Congratulations! You have claimed your **{emoji_str} {special.name} {ball.country}** "
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
        """Show all active collector requirements."""
        await interaction.response.defer(ephemeral=True)

        if not collector_requirements:
            await interaction.followup.send(
                "There are no collector requirements set up yet.",
                ephemeral=True,
            )
            return

        collectible = _collectible_name()
        lines = [f"**Active Collector Requirements** ({len(collector_requirements)} total)\n"]
        for req in collector_requirements.values():
            lines.append(
                f"• **{req['ball_name']}** — own ≥ {req['amount']} → "
                f"reward: {req['special_name']} special"
            )

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ── /admin collector set ──────────────────────────────────────────────────

    @admin_collector_group.command(
        name="set",
        description="Set or update a collector requirement for a ball",
    )
    @app_commands.describe(
        countryball=f"The {settings.collectible_name} to set a collector requirement for",
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
        """
        Set or update a collector requirement.

        Only bot admins (users listed in settings.discord_owners_ids) can use this.
        """
        if interaction.user.id not in self.bot.owner_ids:
            await interaction.response.send_message(
                "Only bot admins can manage collector requirements.",
                ephemeral=True,
            )
            return

        ball = countryball
        ball_id = ball.pk

        collector_requirements[ball_id] = {
            "ball_id": ball_id,
            "ball_name": ball.country,
            "amount": amount,
            "special_id": special.pk,
            "special_name": special.name,
        }
        # Reset claimed set when requirement changes
        claimed_players.pop(ball_id, None)

        collectible = _collectible_name()
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
        countryball=f"The {settings.collectible_name} whose collector requirement you want to remove",
    )
    async def admin_collector_delete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        """
        Delete an existing collector requirement.

        Only bot admins can use this.
        """
        if interaction.user.id not in self.bot.owner_ids:
            await interaction.response.send_message(
                "Only bot admins can manage collector requirements.",
                ephemeral=True,
            )
            return

        ball = countryball
        ball_id = ball.pk

        if ball_id not in collector_requirements:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.",
                ephemeral=True,
            )
            return

        del collector_requirements[ball_id]
        claimed_players.pop(ball_id, None)

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
        countryball=f"The {settings.collectible_name} to inspect",
    )
    async def admin_collector_view(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        """View details of a specific collector requirement."""
        if interaction.user.id not in self.bot.owner_ids:
            await interaction.response.send_message(
                "Only bot admins can view collector requirements.",
                ephemeral=True,
            )
            return

        ball = countryball
        ball_id = ball.pk

        if ball_id not in collector_requirements:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.",
                ephemeral=True,
            )
            return

        req = collector_requirements[ball_id]
        claimed_count = len(claimed_players.get(ball_id, set()))

        await interaction.response.send_message(
            f"**Collector Requirement — {ball.country}**\n"
            f"• Minimum amount: **{req['amount']}**\n"
            f"• Reward special: **{req['special_name']}** (ID: {req['special_id']})\n"
            f"• Claims this session: **{claimed_count}**",
            ephemeral=True,
        )
