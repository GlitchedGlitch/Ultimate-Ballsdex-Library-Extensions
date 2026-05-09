"""
Collector package for BallsDex (v2.30 compatible).

Commands:
  /collector claim  — claim a collector ball if requirements are met
  /collector list   — paginated list of active requirements
  /admin collector set    — set a requirement (bot admins only, hidden)
  /admin collector delete — delete a requirement (bot admins only, hidden)
  /admin collector view   — inspect a requirement (bot admins only, hidden)

Requirements persist on the bot object across cog reloads.
They are also saved to /code/ballsdex/packages/collector/requirements.txt
so they survive package updates.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.bot import owner_check
from ballsdex.core.models import BallInstance, GuildConfig, Player, Special
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")

GROUPS_PER_PAGE = 7
REQUIREMENTS_FILE = "/code/ballsdex/packages/collector/requirements.txt"


# ── Persistence helpers ───────────────────────────────────────────────────────

def _save_requirements(requirements: dict[int, dict]) -> None:
    try:
        with open(REQUIREMENTS_FILE, "w") as f:
            json.dump(requirements, f, indent=2)
    except Exception:
        log.warning("Could not save requirements.txt", exc_info=True)


def _load_requirements() -> dict[int, dict]:
    if not os.path.isfile(REQUIREMENTS_FILE):
        return {}
    try:
        with open(REQUIREMENTS_FILE, "r") as f:
            raw = json.load(f)
        # JSON keys are always strings; convert back to int
        return {int(k): v for k, v in raw.items()}
    except Exception:
        log.warning("Could not load requirements.txt", exc_info=True)
        return {}


# ── Emoji helper ─────────────────────────────────────────────────────────────

def _ball_emoji(bot: "BallsDexBot", ball_id: int) -> str:
    from ballsdex.core.models import balls as balls_cache
    ball = balls_cache.get(ball_id)
    if ball and ball.emoji_id:
        emoji = bot.get_emoji(ball.emoji_id)
        if emoji:
            return str(emoji)
    return "•"


# ── Log channel helper ────────────────────────────────────────────────────────

async def _send_admin_log(
    bot: "BallsDexBot",
    interaction: discord.Interaction,
    message: str,
) -> None:
    """Send a message to the guild's configured log channel, if any."""
    if not interaction.guild_id:
        return
    try:
        config = await GuildConfig.get_or_none(guild_id=interaction.guild_id)
        if config and config.spawn_channel:
            # BallsDex stores the log/spawn channel id on GuildConfig
            channel = bot.get_channel(config.spawn_channel)
            if isinstance(channel, discord.TextChannel):
                await channel.send(message)
    except Exception:
        log.warning("Could not send admin log to channel", exc_info=True)


# ── Cog ───────────────────────────────────────────────────────────────────────

class CollectorCog(commands.Cog):
    """Collector package."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        # Persist requirements on bot object so reloads don't wipe them
        if not hasattr(bot, "collector_requirements"):
            bot.collector_requirements: dict[int, dict] = _load_requirements()
        if not hasattr(bot, "collector_claimed"):
            bot.collector_claimed: dict[int, set[int]] = {}

    # ── Groups ────────────────────────────────────────────────────────────────

    collector_group = app_commands.Group(
        name="collector",
        description="Collector commands",
    )

    # /admin group: guild-level administrator permission hides it from non-admins
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
    @app_commands.describe(countryball="The ball you want to claim a collector version of")
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

        if interaction.user.id in claimed.get(ball_id, set()):
            await interaction.followup.send(
                f"You have already claimed your collector **{ball.country}**!",
                ephemeral=True,
            )
            return

        count = await BallInstance.filter(player=player, ball=ball, deleted=False).count()
        required = req["amount"]
        if count < required:
            await interaction.followup.send(
                f"You need at least **{required}** {ball.country} "
                f"but you only have **{count}**.",
                ephemeral=True,
            )
            return

        special = await Special.get_or_none(pk=req["special_id"])
        if special is None:
            await interaction.followup.send(
                "The collector reward special no longer exists. Contact an admin.",
                ephemeral=True,
            )
            log.error("Collector special ID %d for %s not found.", req["special_id"], ball.country)
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
            "User %s (%d) claimed collector %s / special %s (#%X)",
            interaction.user, interaction.user.id, ball.country, special.name, new_instance.pk,
        )
        emoji_str = special.emoji or ""
        await interaction.followup.send(
            f"🎉 Congratulations! You claimed your **{emoji_str} {special.name} {ball.country}** "
            f"collector {settings.collectible_name}!\n"
            f"Added to your collection as `#{new_instance.pk:0X}`.",
            ephemeral=True,
        )

    # ── /collector list ───────────────────────────────────────────────────────

    @collector_group.command(name="list", description="List all active collector requirements")
    @app_commands.describe(reverse="Sort from highest to lowest amount (default: lowest first)")
    async def collector_list(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        reverse: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        requirements = self.bot.collector_requirements
        if not requirements:
            await interaction.followup.send(
                "There are no collector requirements set up yet.", ephemeral=True
            )
            return

        # Sort and group by amount
        sorted_reqs = sorted(requirements.values(), key=lambda r: r["amount"], reverse=reverse)
        grouped: dict[int, list[dict]] = {}
        for req in sorted_reqs:
            grouped.setdefault(req["amount"], []).append(req)
        sorted_amounts = list(grouped.keys())

        # Build (field_name, field_value) tuples for FieldPageSource
        entries: list[tuple[str, str]] = []
        for amount in sorted_amounts:
            reqs = grouped[amount]
            lines = [
                f"* {_ball_emoji(self.bot, r['ball_id'])} {r['ball_name']} → *{r['special_name']}*"
                for r in reqs
            ]
            entries.append((f"Minimum: {amount}", "\n".join(lines)))

        sort_label = "Highest → Lowest" if reverse else "Lowest → Highest"
        source = FieldPageSource(entries, per_page=GROUPS_PER_PAGE, inline=False)
        source.embed.title = "🏆 Collector List"
        source.embed.color = discord.Color.gold()
        source.embed.set_footer(
            text=f"{len(requirements)} requirement(s) • Sorted: {sort_label}"
        )

        pages = Pages(source, interaction=interaction)
        await pages.start(ephemeral=True)

    # ── /admin collector set ──────────────────────────────────────────────────

    @admin_collector_group.command(name="set", description="Set or update a collector requirement")
    @app_commands.describe(
        countryball="The ball to set a requirement for",
        amount="Minimum number the player must own",
        special="The special reward the player receives",
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
                "Only bot admins can manage collector requirements.", ephemeral=True
            )
            return

        ball = countryball
        self.bot.collector_requirements[ball.pk] = {
            "ball_id": ball.pk,
            "ball_name": ball.country,
            "amount": amount,
            "special_id": special.pk,
            "special_name": special.name,
        }
        self.bot.collector_claimed.pop(ball.pk, None)
        _save_requirements(self.bot.collector_requirements)

        msg = (
            f"✅ **Collector requirement set** by {interaction.user.mention}\n"
            f"• Ball: **{ball.country}** | Minimum: **{amount}** | Reward: **{special.name}**"
        )
        await interaction.response.send_message(msg, ephemeral=True)
        await _send_admin_log(self.bot, interaction, msg)
        log.info("Admin %s set collector: ball=%s amount=%d special=%s",
                 interaction.user, ball.country, amount, special.name)

    # ── /admin collector delete ───────────────────────────────────────────────

    @admin_collector_group.command(name="delete", description="Delete a collector requirement")
    @app_commands.describe(countryball="The ball whose requirement you want to remove")
    async def admin_collector_delete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        if interaction.user.id not in self.bot.owner_ids:
            await interaction.response.send_message(
                "Only bot admins can manage collector requirements.", ephemeral=True
            )
            return

        ball = countryball
        if ball.pk not in self.bot.collector_requirements:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        del self.bot.collector_requirements[ball.pk]
        self.bot.collector_claimed.pop(ball.pk, None)
        _save_requirements(self.bot.collector_requirements)

        msg = (
            f"🗑️ **Collector requirement deleted** by {interaction.user.mention}\n"
            f"• Ball: **{ball.country}**"
        )
        await interaction.response.send_message(msg, ephemeral=True)
        await _send_admin_log(self.bot, interaction, msg)
        log.info("Admin %s deleted collector: ball=%s", interaction.user, ball.country)

    # ── /admin collector view ─────────────────────────────────────────────────

    @admin_collector_group.command(name="view", description="View a specific collector requirement")
    @app_commands.describe(countryball="The ball to inspect")
    async def admin_collector_view(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        if interaction.user.id not in self.bot.owner_ids:
            await interaction.response.send_message(
                "Only bot admins can view collector requirements.", ephemeral=True
            )
            return

        ball = countryball
        if ball.pk not in self.bot.collector_requirements:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        req = self.bot.collector_requirements[ball.pk]
        claimed_count = len(self.bot.collector_claimed.get(ball.pk, set()))
        await interaction.response.send_message(
            f"**Collector Requirement — {ball.country}**\n"
            f"• Minimum: **{req['amount']}**\n"
            f"• Reward: **{req['special_name']}** (ID `{req['special_id']}`)\n"
            f"• Claims this session: **{claimed_count}**",
            ephemeral=True,
        )
