"""
Collector package for BallsDex v3

Commands:
  collector claim  — claim a collector ball if requirements are met
  collector list   — paginated list of active requirements
  admin collector set    — set a requirement and reward (Django permission required)
  admin collector delete — remove a requirement (Django permission required)
  admin collector view   — inspect a requirement (Django permission required)
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bd_models.models import BallInstance, Player, Special
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.menus import (
    ChunkedListSource,
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

REQUIREMENTS_FILE = "/code/ballsdex/packages/collector/requirements.txt"


# ── Persistence ───────────────────────────────────────────────────────────────

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
        return {int(k): v for k, v in raw.items()}
    except Exception:
        log.warning("Could not load requirements.txt", exc_info=True)
        return {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ball_emoji(bot: "BallsDexBot", ball_id: int) -> str:
    from ballsdex.core.models import balls as balls_cache
    ball = balls_cache.get(ball_id)
    if ball and ball.emoji_id:
        emoji = bot.get_emoji(ball.emoji_id)
        if emoji:
            return str(emoji)
    return "•"


# ── Permission check ──────────────────────────────────────────────────────────
# v3 uses Django permissions; the built-in helper below mirrors what core admin
# commands do — require the Discord user to have the "admin" Django permission.

def _is_admin():
    """Decorator that checks Django-based admin permission (v3 style)."""
    async def predicate(ctx: commands.Context) -> bool:
        # BallsDexBot exposes is_admin() or similar; fall back to guild-owner check.
        if hasattr(ctx.bot, "is_admin"):
            return await ctx.bot.is_admin(ctx.author)
        # Fallback: guild owner always passes
        if ctx.guild and ctx.guild.owner_id == ctx.author.id:
            return True
        raise commands.CheckFailure(
            "You do not have the required permissions to use this command."
        )
    return commands.check(predicate)


# ── /admin collector — GroupCog attached to the admin group ───────────────────

class CollectorAdminCog(commands.GroupCog, name="collector"):
    """Admin subgroup: manage collector requirements."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        super().__init__()

    # ── set ───────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="set", description="Set or update a collector requirement")
    @app_commands.describe(
        countryball="The ball to set a requirement for",
        amount="Minimum number the player must own",
        special="The special reward the player receives",
    )
    @_is_admin()
    async def collector_set(
        self,
        ctx: commands.Context["BallsDexBot"],
        countryball: BallTransform,
        amount: app_commands.Range[int, 1, 9999],
        special: SpecialTransform,
    ):
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

        await ctx.send(
            f"Collector requirement set: **{ball.country}** — "
            f"own ≥ **{amount}** → reward **{special.name}**.\n"
            f"Previous claims for this ball have been reset.",
            ephemeral=True,
        )
        await log_action(
            f"{ctx.author.name} set collector requirement for "
            f"{ball.country}. "
            f"(Minimum={amount} Special={special.name})",
            ctx.bot,
        )

    # ── delete ────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="delete", description="Delete a collector requirement")
    @app_commands.describe(countryball="The ball whose requirement you want to remove")
    @_is_admin()
    async def collector_delete(
        self,
        ctx: commands.Context["BallsDexBot"],
        countryball: BallTransform,
    ):
        ball = countryball
        if ball.pk not in self.bot.collector_requirements:
            await ctx.send(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        del self.bot.collector_requirements[ball.pk]
        self.bot.collector_claimed.pop(ball.pk, None)
        _save_requirements(self.bot.collector_requirements)

        await ctx.send(
            f"Collector requirement for **{ball.country}** has been deleted.",
            ephemeral=True,
        )
        await log_action(
            f"{ctx.author.name} deleted collector requirement for {ball.country}.",
            ctx.bot,
        )

    # ── view ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="view", description="View a specific collector requirement")
    @app_commands.describe(countryball="The ball to inspect")
    @_is_admin()
    async def collector_view(
        self,
        ctx: commands.Context["BallsDexBot"],
        countryball: BallTransform,
    ):
        ball = countryball
        if ball.pk not in self.bot.collector_requirements:
            await ctx.send(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        req = self.bot.collector_requirements[ball.pk]
        claimed_count = len(self.bot.collector_claimed.get(ball.pk, set()))
        await ctx.send(
            f"**Collector Requirement — {ball.country}**\n"
            f"• Minimum: **{req['amount']}**\n"
            f"• Reward: **{req['special_name']}** (ID `{req['special_id']}`)\n"
            f"• Claims this session: **{claimed_count}**",
            ephemeral=True,
        )


# ── Player-facing cog ─────────────────────────────────────────────────────────

class CollectorCog(commands.GroupCog, name="collector"):
    """Collector package — player commands."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        if not hasattr(bot, "collector_requirements"):
            bot.collector_requirements: dict[int, dict] = _load_requirements()
        if not hasattr(bot, "collector_claimed"):
            bot.collector_claimed: dict[int, set[int]] = {}
        super().__init__()

    # ── claim ─────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="claim", description="Claim your collector ball reward")
    @app_commands.describe(countryball="The ball you want to claim a collector version of")
    async def collector_claim(
        self,
        ctx: commands.Context["BallsDexBot"],
        countryball: BallTransform,
    ):
        ball = countryball
        ball_id = ball.pk
        requirements = self.bot.collector_requirements
        claimed = self.bot.collector_claimed

        if ball_id not in requirements:
            await ctx.send(
                f"There is no collector requirement set for **{ball.country}**.",
                ephemeral=True,
            )
            return

        req = requirements[ball_id]
        player, _ = await Player.objects.aget_or_create(discord_id=ctx.author.id)

        if ctx.author.id in claimed.get(ball_id, set()):
            await ctx.send(
                f"You have already claimed your collector **{ball.country}**!",
                ephemeral=True,
            )
            return

        count = await BallInstance.objects.filter(
            player=player, ball=ball, deleted=False
        ).acount()
        required = req["amount"]
        if count < required:
            await ctx.send(
                f"You need at least **{required}** {ball.country} "
                f"but you only have **{count}**.",
                ephemeral=True,
            )
            return

        special = await Special.objects.filter(pk=req["special_id"]).afirst()
        if special is None:
            await ctx.send(
                "The collector reward special no longer exists. Contact an admin.",
                ephemeral=True,
            )
            log.error(
                "Collector special ID %d for %s not found.", req["special_id"], ball.country
            )
            return

        new_instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            special=special,
            attack_bonus=0,
            health_bonus=0,
            server_id=ctx.guild.id if ctx.guild else None,
        )
        claimed.setdefault(ball_id, set()).add(ctx.author.id)

        log.info(
            "User %s (%d) claimed collector %s / special %s (#%X)",
            ctx.author,
            ctx.author.id,
            ball.country,
            special.name,
            new_instance.pk,
        )
        await log_action(
            f"{ctx.author.name} claimed {ball.country} "
            f"`(#{new_instance.pk:0X})`. "
            f"(Special={special.name} "
            f"ATK={new_instance.attack_bonus:+d} "
            f"HP={new_instance.health_bonus:+d})",
            ctx.bot,
        )

        emoji_str = special.emoji or ""
        await ctx.send(
            f"Congratulations! You claimed your **{emoji_str} {special.name} {ball.country}** "
            f"collector {settings.collectible_name}!\n"
            f"Added to your collection as `#{new_instance.pk:0X}`.",
            ephemeral=True,
        )

    # ── list ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="list", description="List all active collector requirements")
    @app_commands.describe(reverse="Reverse the output of the list")
    async def collector_list(
        self,
        ctx: commands.Context["BallsDexBot"],
        reverse: bool = False,
    ):
        requirements = self.bot.collector_requirements
        if not requirements:
            await ctx.send(
                "There are no collector requirements set up yet.", ephemeral=True
            )
            return

        sorted_reqs = sorted(
            requirements.values(), key=lambda r: r["amount"], reverse=reverse
        )
        # Group by minimum amount
        grouped: dict[int, list[dict]] = {}
        for req in sorted_reqs:
            grouped.setdefault(req["amount"], []).append(req)

        # Build one TextDisplay per amount-group for the v3 paginator
        async def _generate_items():
            for amount, reqs in grouped.items():
                lines = "\n".join(
                    f"* {_ball_emoji(self.bot, r['ball_id'])} "
                    f"{r['ball_name']} → *{r['special_name']}*"
                    for r in reqs
                )
                yield discord.ui.TextDisplay(f"**Minimum: {amount}**\n{lines}")
                yield discord.ui.Separator()

        view = discord.ui.LayoutView()
        container = discord.ui.Container()

        # Title section
        container.add_item(
            discord.ui.Section(
                discord.ui.TextDisplay("# Collector List"),
            )
        )
        container.add_item(discord.ui.Separator())

        view.add_item(container)

        chunks = await dynamic_chunks(view, _generate_items())
        if not chunks:
            await ctx.send("There are no collector requirements set up yet.", ephemeral=True)
            return

        source = ChunkedListSource(chunks, per_page=1)  # each chunk is already a page
        formatter = ItemFormatter(container, position=2)  # insert after header + separator
        menu = Menu(ctx.bot, view, source, formatter)
        await menu.init(container=container)

        await ctx.send(view=view, ephemeral=True)
