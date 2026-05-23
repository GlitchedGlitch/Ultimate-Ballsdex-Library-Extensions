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
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")

# Stored alongside the Django app inside config/packages/collector_app/
REQUIREMENTS_FILE = os.path.join(os.path.dirname(__file__), "requirements.json")


# ── Persistence ───────────────────────────────────────────────────────────────

def _save_requirements(requirements: dict[int, dict]) -> None:
    try:
        with open(REQUIREMENTS_FILE, "w") as f:
            json.dump(requirements, f, indent=2)
    except Exception:
        log.warning("Could not save requirements.json", exc_info=True)


def _load_requirements() -> dict[int, dict]:
    if not os.path.isfile(REQUIREMENTS_FILE):
        return {}
    try:
        with open(REQUIREMENTS_FILE, "r") as f:
            raw = json.load(f)
        return {int(k): v for k, v in raw.items()}
    except Exception:
        log.warning("Could not load requirements.json", exc_info=True)
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

def _is_admin():
    async def predicate(ctx: commands.Context) -> bool:
        if hasattr(ctx.bot, "is_admin"):
            return await ctx.bot.is_admin(ctx.author)
        if ctx.guild and ctx.guild.owner_id == ctx.author.id:
            return True
        raise commands.CheckFailure(
            "You do not have the required permissions to use this command."
        )
    return commands.check(predicate)


# ── /admin collector subgroup ─────────────────────────────────────────────────

class CollectorAdminCog(commands.GroupCog, name="collector"):
    """Admin subgroup: manage collector requirements."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        super().__init__()

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
        countryball: str,
        amount: app_commands.Range[int, 1, 9999],
        special: str,
    ):
        # Resolve ball and special by name
        ball = None
        async for b in __import__("bd_models.models", fromlist=["Ball"]).Ball.objects.filter(enabled=True):
            if b.country.lower() == countryball.lower():
                ball = b
                break
        if ball is None:
            await ctx.send(f"No ball found matching `{countryball}`.", ephemeral=True)
            return

        sp = None
        async for s in Special.objects.all():
            if s.name.lower() == special.lower():
                sp = s
                break
        if sp is None:
            await ctx.send(f"No special found matching `{special}`.", ephemeral=True)
            return

        self.bot.collector_requirements[ball.pk] = {
            "ball_id": ball.pk,
            "ball_name": ball.country,
            "amount": amount,
            "special_id": sp.pk,
            "special_name": sp.name,
        }
        self.bot.collector_claimed.pop(ball.pk, None)
        _save_requirements(self.bot.collector_requirements)

        await ctx.send(
            f"Collector requirement set: **{ball.country}** — "
            f"own ≥ **{amount}** → reward **{sp.name}**.\n"
            f"Previous claims for this ball have been reset.",
            ephemeral=True,
        )
        await log_action(
            f"{ctx.author.name} set collector requirement for "
            f"{ball.country}. (Minimum={amount} Special={sp.name})",
            ctx.bot,
        )

    @commands.hybrid_command(name="delete", description="Delete a collector requirement")
    @app_commands.describe(countryball="The ball whose requirement you want to remove")
    @_is_admin()
    async def collector_delete(
        self,
        ctx: commands.Context["BallsDexBot"],
        countryball: str,
    ):
        match = next(
            (v for v in self.bot.collector_requirements.values()
             if v["ball_name"].lower() == countryball.lower()),
            None,
        )
        if match is None:
            await ctx.send(
                f"No collector requirement exists for **{countryball}**.", ephemeral=True
            )
            return

        ball_pk = match["ball_id"]
        del self.bot.collector_requirements[ball_pk]
        self.bot.collector_claimed.pop(ball_pk, None)
        _save_requirements(self.bot.collector_requirements)

        await ctx.send(
            f"Collector requirement for **{match['ball_name']}** has been deleted.",
            ephemeral=True,
        )
        await log_action(
            f"{ctx.author.name} deleted collector requirement for {match['ball_name']}.",
            ctx.bot,
        )

    @commands.hybrid_command(name="view", description="View a specific collector requirement")
    @app_commands.describe(countryball="The ball to inspect")
    @_is_admin()
    async def collector_view(
        self,
        ctx: commands.Context["BallsDexBot"],
        countryball: str,
    ):
        match = next(
            (v for v in self.bot.collector_requirements.values()
             if v["ball_name"].lower() == countryball.lower()),
            None,
        )
        if match is None:
            await ctx.send(
                f"No collector requirement exists for **{countryball}**.", ephemeral=True
            )
            return

        ball_pk = match["ball_id"]
        claimed_count = len(self.bot.collector_claimed.get(ball_pk, set()))
        await ctx.send(
            f"**Collector Requirement — {match['ball_name']}**\n"
            f"• Minimum: **{match['amount']}**\n"
            f"• Reward: **{match['special_name']}** (ID `{match['special_id']}`)\n"
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

    @commands.hybrid_command(name="claim", description="Claim your collector ball reward")
    @app_commands.describe(countryball="The ball you want to claim a collector version of")
    async def collector_claim(
        self,
        ctx: commands.Context["BallsDexBot"],
        countryball: str,
    ):
        requirements = self.bot.collector_requirements
        claimed = self.bot.collector_claimed

        # Resolve ball by name
        from bd_models.models import Ball
        ball = None
        async for b in Ball.objects.filter(enabled=True):
            if b.country.lower() == countryball.lower():
                ball = b
                break
        if ball is None:
            await ctx.send(
                f"No ball found matching `{countryball}`.", ephemeral=True
            )
            return

        ball_id = ball.pk
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
            ctx.author, ctx.author.id, ball.country, special.name, new_instance.pk,
        )
        await log_action(
            f"{ctx.author.name} claimed {ball.country} `(#{new_instance.pk:0X})`. "
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
        grouped: dict[int, list[dict]] = {}
        for req in sorted_reqs:
            grouped.setdefault(req["amount"], []).append(req)

        lines = []
        for amount, reqs in grouped.items():
            lines.append(f"**Minimum: {amount}**")
            for r in reqs:
                emoji = _ball_emoji(self.bot, r["ball_id"])
                lines.append(f"* {emoji} {r['ball_name']} → *{r['special_name']}*")
            lines.append("")

        # Simple paginated output — split into 1800-char chunks to stay within limits
        pages = []
        current = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > 1800 and current:
                pages.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line) + 1
        if current:
            pages.append("\n".join(current))

        total = len(pages)
        for i, page in enumerate(pages, 1):
            embed = discord.Embed(
                title="Collector List" if i == 1 else f"Collector List (cont.)",
                description=page,
                color=discord.Color.gold(),
            )
            if total > 1:
                embed.set_footer(text=f"Page {i}/{total}")
            await ctx.send(embed=embed, ephemeral=True)
