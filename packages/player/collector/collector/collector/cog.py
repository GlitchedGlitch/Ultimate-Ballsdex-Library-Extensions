"""
Collector package for BallsDex v3 :DD
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput

from ballsdex.core.utils.menus import Menu, TextFormatter
from ballsdex.core.utils.menus.source import TextSource
from bd_models.models import Ball, BallInstance, Player, balls as balls_cache
from collector.models import CollectorClaim, CollectorRequirement
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")
Interaction = discord.Interaction["BallsDexBot"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ball_emoji(bot: "BallsDexBot", ball_id: int) -> str:
    ball = balls_cache.get(ball_id)
    if ball and ball.emoji_id:
        emoji = bot.get_emoji(ball.emoji_id)
        if emoji:
            return str(emoji)
    return "•"

async def _get_reqs(ball_id: int) -> list[CollectorRequirement]:
    return [
        r async for r in
        CollectorRequirement.objects.filter(ball_id=ball_id)
        .select_related("special")
        .order_by("amount")
        .aiterator()
    ]

async def _has_claimed(player: Player, req: CollectorRequirement) -> bool:
    return await CollectorClaim.objects.filter(
        player=player, requirement=req
    ).aexists()

async def _count_owned(player: Player, ball_id: int) -> int:
    return await BallInstance.objects.filter(
        player=player, ball_id=ball_id, deleted=False
    ).acount()

# ── Claim helpers ─────────────────────────────────────────────────────────────

async def _do_claim(
    interaction: Interaction,
    ball: Ball,
    player: Player,
    req: CollectorRequirement,
) -> None:
    if await _has_claimed(player, req):
        await interaction.followup.send(
            f"You already claimed **{req.special.name} {ball.country}**!",
            ephemeral=True,
        )
        return

    new_instance = await BallInstance.objects.acreate(
        player=player,
        ball=ball,
        special=req.special,
        attack_bonus=0,
        health_bonus=0,
        server_id=interaction.guild_id,
    )
    await CollectorClaim.objects.acreate(
        player=player,
        requirement=req,
        ball_instance=new_instance,
    )

    emoji_str = req.special.emoji or ""
    log.info(
        f"Player {player.discord_id} claimed {req.special.name} {ball.country} "
        f"(#{new_instance.pk:0X})",
    )
    await interaction.followup.send(
        f"Congratulations! You claimed **{emoji_str} {req.special.name} {ball.country}** "
        f"collector {settings.collectible_name}!\n"
        f"Added to your collection as `#{new_instance.pk:0X}`.",
        ephemeral=True,
    )

class ClaimSelectView(discord.ui.View):
    """Shown when a player qualifies for multiple rewards on the same ball."""

    def __init__(
        self,
        interaction: Interaction,
        ball: Ball,
        player: Player,
        eligible: list[CollectorRequirement],
    ):
        super().__init__(timeout=60)
        self.original = interaction
        for req in eligible:
            btn = discord.ui.Button(
                label=f"{req.special.name} — ≥{req.amount:,}",
                style=discord.ButtonStyle.primary,
            )

            async def callback(itx: Interaction, r: CollectorRequirement = req):
                await itx.response.defer(ephemeral=True)
                await _do_claim(itx, ball, player, r)
                self.stop()

            btn.callback = callback
            self.add_item(btn)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.original.user.id:
            await interaction.response.send_message(
                "This menu is not for you.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True  # type: ignore
        try:
            await self.original.edit_original_response(view=self)
        except Exception:
            pass

# ── Bulk modal ────────────────────────────────────────────────────────────────

class BulkAddModal(Modal, title="Bulk Add Collector Requirements"):
    requirements_input = TextInput(
        label="BallName | Amount | SpecialName",
        style=discord.TextStyle.paragraph,
        placeholder=(
            "One requirement per line:\n"
            "France | 30 | Bronze\n"
            "France | 50 | Silver\n"
            "Germany | 10 | Gold"
        ),
        required=True,
        max_length=4000,
    )

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self._process(interaction)
        except Exception:
            import traceback
            log.exception("Error in bulk add modal")
            await interaction.followup.send(
                f"An error occurred:\n```py\n{traceback.format_exc()[:1800]}\n```",
                ephemeral=True,
            )

    async def _process(self, interaction: Interaction):
        from bd_models.models import Special

        lines = [l.strip() for l in self.requirements_input.value.splitlines() if l.strip()]
        if not lines:
            await interaction.followup.send("No requirements provided.", ephemeral=True)
            return

        added: list[str] = []
        errors: list[str] = []

        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 3:
                errors.append(f"`{line}` — must be `BallName | Amount | SpecialName`")
                continue

            ball_name, amount_str, special_name = parts

            try:
                amount = int(amount_str)
                if not (1 <= amount <= 9999):
                    raise ValueError
            except ValueError:
                errors.append(f"`{line}` — amount must be 1–9999")
                continue

            ball = await Ball.objects.filter(
                country__iexact=ball_name, enabled=True
            ).afirst()
            if ball is None:
                ball = await Ball.objects.filter(
                    country__icontains=ball_name, enabled=True
                ).afirst()
            if ball is None:
                errors.append(
                    f"`{line}` — {settings.collectible_name} `{ball_name}` not found"
                )
                continue

            special = await Special.objects.filter(name__iexact=special_name).afirst()
            if special is None:
                special = await Special.objects.filter(
                    name__icontains=special_name
                ).afirst()
            if special is None:
                errors.append(f"`{line}` — special `{special_name}` not found")
                continue

            await CollectorRequirement.objects.aupdate_or_create(
                ball=ball,
                special=special,
                defaults={"amount": amount},
            )
            added.append(f"**{ball.country}** — ≥{amount:,} -> {special.name}")

        result_lines: list[str] = []
        if added:
            result_lines.append(f"**Added {len(added)} requirement(s):**")
            result_lines.extend(added)
        if errors:
            result_lines.append(f"\n**Errors ({len(errors)}):**")
            result_lines.extend(errors)

        result_text = "\n".join(result_lines)
        if len(result_text) > 1900:
            result_text = result_text[:1900] + "\n... (truncated)"

        await interaction.followup.send(result_text, ephemeral=True)

        if added:
            log.info(
                f"{interaction.user} bulk added {len(added)} collector requirement(s). "
                f"Errors: {len(errors)}",
                extra={"webhook": True},
            )

# ── Player cog ────────────────────────────────────────────────────────────────

class CollectorCog(commands.GroupCog, name="collector"):
    """Collector commands — claim special versions of balls you've collected enough of."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    # ── /collector claim ──────────────────────────────────────────────────────

    async def _claim_ball_autocomplete(
        self,
        interaction: Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Only show balls that have at least one requirement configured."""
        results: list[app_commands.Choice[str]] = []
        seen: set[int] = set()
        async for req in (
            CollectorRequirement.objects
            .select_related("ball")
            .filter(ball__enabled=True)
            .order_by("ball__country")
            .aiterator()
        ):
            if req.ball_id not in seen:
                if current.lower() in req.ball.country.lower():
                    seen.add(req.ball_id)
                    results.append(
                        app_commands.Choice(
                            name=req.ball.country, value=req.ball.country
                        )
                    )
                if len(results) >= 25:
                    break
        return results

    @app_commands.command()
    @app_commands.describe(
        countryball=(
            f"The {settings.collectible_name} to claim "
            "(leave empty to see your full overview)"
        )
    )
    @app_commands.autocomplete(countryball=_claim_ball_autocomplete)
    async def claim(self, interaction: Interaction, countryball: str | None = None):
        """Claim your collector ball reward, or see what you can claim."""
        await interaction.response.defer(ephemeral=True)

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

        # ── No argument: show overview ────────────────────────────────────────
        if countryball is None:
            all_reqs = [
                r async for r in
                CollectorRequirement.objects.select_related("ball", "special")
                .order_by("ball__country", "amount")
                .aiterator()
            ]
            if not all_reqs:
                await interaction.followup.send(
                    "There are no collector requirements set up yet.", ephemeral=True
                )
                return

            # Group by ball
            by_ball: dict[int, list[CollectorRequirement]] = defaultdict(list)
            for r in all_reqs:
                by_ball[r.ball_id].append(r)

            claimable: list[str] = []
            in_progress: list[str] = []

            for ball_id, reqs in by_ball.items():
                ball = balls_cache.get(ball_id) or reqs[0].ball
                count = await _count_owned(player, ball_id)
                emoji = _ball_emoji(self.bot, ball_id)

                for r in sorted(reqs, key=lambda x: x.amount):
                    if await _has_claimed(player, r):
                        continue
                    if count >= r.amount:
                        claimable.append(
                            f"• {emoji} **{ball.country}** — {r.special.name} ✅ ready"
                        )
                    else:
                        pct = round(100 * count / r.amount)
                        in_progress.append(
                            f"• {emoji} **{ball.country}** — {r.special.name} "
                            f"({count:,}/{r.amount:,} · {pct}%)"
                        )

            if not claimable and not in_progress:
                await interaction.followup.send(
                    "You have already claimed all available collector rewards!",
                    ephemeral=True,
                )
                return

            lines: list[str] = []
            if claimable:
                lines.append("**Ready to claim:**")
                lines.extend(claimable[:20])
                if len(claimable) > 20:
                    lines.append(f"*...and {len(claimable) - 20} more*")
            if in_progress:
                lines.append("\n**In progress:**")
                lines.extend(in_progress[:20])
                if len(in_progress) > 20:
                    lines.append(f"*...and {len(in_progress) - 20} more*")
                lines.append(
                    f"\nUse `/collector claim {settings.collectible_name}:` to claim a specific ball."
                )
            await interaction.followup.send("\n".join(lines), ephemeral=True)
            return

        # ── Specific ball ─────────────────────────────────────────────────────
        ball = await Ball.objects.filter(
            enabled=True, country__iexact=countryball
        ).afirst()
        if ball is None:
            ball = await Ball.objects.filter(
                enabled=True, country__icontains=countryball
            ).afirst()
        if ball is None:
            await interaction.followup.send(
                f"No ball found matching `{countryball}`.", ephemeral=True
            )
            return

        reqs = await _get_reqs(ball.pk)
        if not reqs:
            await interaction.followup.send(
                f"There is no collector requirement set for **{ball.country}**.",
                ephemeral=True,
            )
            return

        count = await _count_owned(player, ball.pk)

        BAR_LEN = 7
        BAR_FILL, BAR_EMPTY = "█", "░"

        def make_bar(current: int, required: int) -> str:
            ratio = min(current / required, 1.0)
            filled = round(BAR_LEN * ratio)
            pct = round(100 * current / required)
            return (
                f"[{BAR_FILL * filled}{BAR_EMPTY * (BAR_LEN - filled)}] "
                f"{current:,}/{required:,} {pct}%"
            )

        lines = [f"Collector requirements for **{ball.country}**"]
        eligible: list[CollectorRequirement] = []

        for r in reqs:
            bar = make_bar(count, r.amount)
            claimed = await _has_claimed(player, r)
            lines.append(f"{r.special.name} — {bar}")
            if not claimed and count >= r.amount:
                eligible.append(r)

        progress_text = "\n".join(lines)

        if not eligible:
            await interaction.followup.send(progress_text, ephemeral=True)
            return

        if len(eligible) == 1:
            await interaction.followup.send(progress_text, ephemeral=True)
            await _do_claim(interaction, ball, player, eligible[0])
        else:
            view = ClaimSelectView(interaction, ball, player, eligible)
            await interaction.followup.send(
                progress_text + "\n\nYou qualify for multiple rewards! Pick one:",
                view=view,
                ephemeral=True,
            )

    # ── /collector list ───────────────────────────────────────────────────────

    @app_commands.command()
    @app_commands.describe(
        special="Filter by special name",
        reverse="Reverse the output of the list",
    )
    async def list(
        self,
        interaction: Interaction,
        special: str | None = None,
        reverse: bool = False,
    ):
        """List all active collector requirements."""
        await interaction.response.defer(ephemeral=True)

        qs = CollectorRequirement.objects.select_related("ball", "special")
        if special:
            qs = qs.filter(special__name__iexact=special.strip())
        qs = qs.order_by(
            "-amount" if reverse else "amount",
            "ball__country",
        )

        all_reqs = [r async for r in qs.aiterator()]
        if not all_reqs:
            msg = (
                f"No requirements found for special `{special}`."
                if special
                else "There are no collector requirements set up yet."
            )
            await interaction.followup.send(msg, ephemeral=True)
            return

        lines: list[str] = []
        current_amount: int | None = None

        for r in all_reqs:
            emoji = _ball_emoji(self.bot, r.ball_id)
            if special:
                line = f"• {emoji} {r.ball.country}"
            else:
                line = f"• {emoji} {r.ball.country} -> *{r.special.name}*"

            if r.amount != current_amount:
                if lines:
                    lines.append("")
                lines.append(f"**Minimum: {r.amount:,}**")
                current_amount = r.amount

            lines.append(line)

        full_text = "\n".join(lines)
        title = f'"{special.strip()}" Collector List' if special else "Collector List"

        view = discord.ui.LayoutView()
        container = discord.ui.Container()

        header = discord.ui.Section(
            discord.ui.TextDisplay(f"# {title}"),
            accessory=discord.ui.Thumbnail(
                url=self.bot.user.display_avatar.url if self.bot.user else ""
            ),
        )
        container.add_item(header)
        container.add_item(discord.ui.Separator())

        text_display = discord.ui.TextDisplay("")
        container.add_item(text_display)
        view.add_item(container)

        source = TextSource(
            full_text,
            page_length=3500,
            prefix="",
            suffix="",
        )
        formatter = TextFormatter(text_display)

        menu = Menu(self.bot, view, source, formatter)
        await menu.init(container=container)

        await interaction.followup.send(view=view)

    @list.autocomplete("special")
    async def list_special_autocomplete(
        self,
        interaction: Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        seen: dict[str, str] = {}
        async for name in (
            CollectorRequirement.objects
            .values_list("special__name", flat=True)
            .distinct()
            .aiterator()
        ):
            if current.lower() in name.lower():
                seen[name.lower()] = name
                if len(seen) >= 25:
                    break
        return [app_commands.Choice(name=n, value=n) for n in seen.values()]
