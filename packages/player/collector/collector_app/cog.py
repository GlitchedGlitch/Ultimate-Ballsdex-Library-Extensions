from __future__ import annotations
import json, logging, os
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands
from bd_models.models import BallInstance, Ball, Player, Special
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")
REQUIREMENTS_FILE = os.path.join(os.path.dirname(__file__), "requirements.json")


def _save(req: dict) -> None:
    try:
        with open(REQUIREMENTS_FILE, "w") as f:
            json.dump(req, f, indent=2)
    except Exception:
        log.warning("Could not save requirements.json", exc_info=True)


def _load() -> dict:
    if not os.path.isfile(REQUIREMENTS_FILE):
        return {}
    try:
        with open(REQUIREMENTS_FILE) as f:
            return {int(k): v for k, v in json.load(f).items()}
    except Exception:
        log.warning("Could not load requirements.json", exc_info=True)
        return {}


def _emoji(bot, ball_id: int) -> str:
    from ballsdex.core.models import balls as cache
    b = cache.get(ball_id)
    if b and b.emoji_id:
        e = bot.get_emoji(b.emoji_id)
        if e:
            return str(e)
    return "•"


def _admin_check():
    async def predicate(ctx: commands.Context) -> bool:
        from ballsdex.core.utils import checks
        try:
            await checks.has_permissions("bd_models.add_ballinstance")(ctx)
            return True
        except Exception:
            pass
        if ctx.guild and ctx.guild.owner_id == ctx.author.id:
            return True
        raise commands.CheckFailure("You do not have permission to use this command.")
    return commands.check(predicate)


class CollectorAdminCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        super().__init__()

    @commands.hybrid_command(name="collector-set")
    @app_commands.describe(countryball="Ball to set requirement for", amount="Minimum owned", special="Reward special")
    @_admin_check()
    async def collector_set(self, ctx: commands.Context, countryball: str, amount: app_commands.Range[int, 1, 9999], special: str):
        """Set or update a collector requirement"""
        ball = None
        async for b in Ball.objects.filter(enabled=True):
            if b.country.lower() == countryball.lower():
                ball = b; break
        if not ball:
            return await ctx.send(f"No ball matching `{countryball}`.", ephemeral=True)
        sp = None
        async for s in Special.objects.all():
            if s.name.lower() == special.lower():
                sp = s; break
        if not sp:
            return await ctx.send(f"No special matching `{special}`.", ephemeral=True)
        self.bot.collector_requirements[ball.pk] = {"ball_id": ball.pk, "ball_name": ball.country, "amount": amount, "special_id": sp.pk, "special_name": sp.name}
        self.bot.collector_claimed.pop(ball.pk, None)
        _save(self.bot.collector_requirements)
        await ctx.send(f"Set: **{ball.country}** ≥ **{amount}** → **{sp.name}**.", ephemeral=True)
        log.info(f"{ctx.author} set collector requirement for {ball.country} (min={amount} special={sp.name})", extra={"webhook": True})

    @commands.hybrid_command(name="collector-delete")
    @app_commands.describe(countryball="Ball to remove requirement for")
    @_admin_check()
    async def collector_delete(self, ctx: commands.Context, countryball: str):
        """Delete a collector requirement"""
        match = next((v for v in self.bot.collector_requirements.values() if v["ball_name"].lower() == countryball.lower()), None)
        if not match:
            return await ctx.send(f"No requirement for **{countryball}**.", ephemeral=True)
        del self.bot.collector_requirements[match["ball_id"]]
        self.bot.collector_claimed.pop(match["ball_id"], None)
        _save(self.bot.collector_requirements)
        await ctx.send(f"Deleted requirement for **{match['ball_name']}**.", ephemeral=True)
        log.info(f"{ctx.author} deleted collector requirement for {match['ball_name']}", extra={"webhook": True})

    @commands.hybrid_command(name="collector-view")
    @app_commands.describe(countryball="Ball to inspect")
    @_admin_check()
    async def collector_view(self, ctx: commands.Context, countryball: str):
        """View a collector requirement"""
        match = next((v for v in self.bot.collector_requirements.values() if v["ball_name"].lower() == countryball.lower()), None)
        if not match:
            return await ctx.send(f"No requirement for **{countryball}**.", ephemeral=True)
        claimed = len(self.bot.collector_claimed.get(match["ball_id"], set()))
        await ctx.send(f"**{match['ball_name']}** — min: **{match['amount']}** • reward: **{match['special_name']}** • claims this session: **{claimed}**", ephemeral=True)


class CollectorCog(commands.GroupCog, name="collector"):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        if not hasattr(bot, "collector_requirements"):
            bot.collector_requirements = _load()
        if not hasattr(bot, "collector_claimed"):
            bot.collector_claimed = {}
        super().__init__()

    @commands.hybrid_command(name="claim", description="Claim your collector ball reward")
    @app_commands.describe(countryball="Ball to claim a collector version of")
    async def collector_claim(self, ctx: commands.Context, countryball: str):
        ball = None
        async for b in Ball.objects.filter(enabled=True):
            if b.country.lower() == countryball.lower():
                ball = b; break
        if not ball:
            return await ctx.send(f"No ball matching `{countryball}`.", ephemeral=True)

        req = self.bot.collector_requirements.get(ball.pk)
        if not req:
            return await ctx.send(f"No collector requirement for **{ball.country}**.", ephemeral=True)

        player, _ = await Player.objects.aget_or_create(discord_id=ctx.author.id)

        if ctx.author.id in self.bot.collector_claimed.get(ball.pk, set()):
            return await ctx.send(f"You already claimed your collector **{ball.country}**!", ephemeral=True)

        count = await BallInstance.objects.filter(player=player, ball=ball, deleted=False).acount()
        if count < req["amount"]:
            return await ctx.send(f"You need **{req['amount']}** {ball.country} but only have **{count}**.", ephemeral=True)

        special = await Special.objects.filter(pk=req["special_id"]).afirst()
        if not special:
            log.error("Collector special ID %d not found for %s", req["special_id"], ball.country)
            return await ctx.send("The reward special no longer exists. Contact an admin.", ephemeral=True)

        inst = await BallInstance.objects.acreate(player=player, ball=ball, special=special, attack_bonus=0, health_bonus=0, server_id=ctx.guild.id if ctx.guild else None)
        self.bot.collector_claimed.setdefault(ball.pk, set()).add(ctx.author.id)
        log.info(f"{ctx.author} claimed collector {ball.country} / {special.name} (#{inst.pk:0X})", extra={"webhook": True})
        await ctx.send(f"🎉 You claimed your **{special.emoji or ''} {special.name} {ball.country}** collector {settings.collectible_name}! (`#{inst.pk:0X}`)", ephemeral=True)

    @commands.hybrid_command(name="list", description="List all active collector requirements")
    @app_commands.describe(reverse="Reverse the list order")
    async def collector_list(self, ctx: commands.Context, reverse: bool = False):
        req = self.bot.collector_requirements
        if not req:
            return await ctx.send("No collector requirements set up yet.", ephemeral=True)

        grouped: dict[int, list] = {}
        for r in sorted(req.values(), key=lambda x: x["amount"], reverse=reverse):
            grouped.setdefault(r["amount"], []).append(r)

        lines = []
        for amount, reqs in grouped.items():
            lines.append(f"**Minimum: {amount}**")
            for r in reqs:
                lines.append(f"* {_emoji(self.bot, r['ball_id'])} {r['ball_name']} → *{r['special_name']}*")
            lines.append("")

        pages, cur, cur_len = [], [], 0
        for line in lines:
            if cur_len + len(line) + 1 > 1800 and cur:
                pages.append("\n".join(cur)); cur = []; cur_len = 0
            cur.append(line); cur_len += len(line) + 1
        if cur:
            pages.append("\n".join(cur))

        for i, page in enumerate(pages, 1):
            embed = discord.Embed(title="Collector List" if i == 1 else "Collector List (cont.)", description=page, color=discord.Color.gold())
            if len(pages) > 1:
                embed.set_footer(text=f"Page {i}/{len(pages)}")
            await ctx.send(embed=embed, ephemeral=True)
