"""
Admin commands for the collector package :))
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from ballsdex.core.utils import checks
from bd_models.models import Ball, Special
from collector.models import CollectorClaim, CollectorRequirement

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.admin.collector")


# ── Converters ────────────────────────────────────────────────────────────────

class BallConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, value: str) -> Ball:
        ball = await Ball.objects.filter(country__iexact=value, enabled=True).afirst()
        if ball is None:
            ball = await Ball.objects.filter(
                country__icontains=value, enabled=True
            ).afirst()
        if ball is None:
            raise commands.BadArgument(f'Collectible "{value}" not found.')
        return ball


class SpecialConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, value: str) -> Special:
        special = await Special.objects.filter(name__iexact=value).afirst()
        if special is None:
            special = await Special.objects.filter(name__icontains=value).afirst()
        if special is None:
            raise commands.BadArgument(f'Special "{value}" not found.')
        return special


# ── Bulk modal ────────────────────────────────────────────────────────────────

class BulkAddModal(discord.ui.Modal, title="Bulk Add Collector Requirements"):
    requirements_input = discord.ui.TextInput(
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

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        from collector.collector.cog import BulkAddModal as CogBulkAddModal
        # Reuse the same processing logic from the cog modal
        modal = CogBulkAddModal()
        modal.requirements_input._value = self.requirements_input.value
        await modal._process(interaction)


# ── Command group ─────────────────────────────────────────────────────────────

@commands.hybrid_group()
@checks.is_staff()
async def collector(ctx: commands.Context["BallsDexBot"]):
    """Collector requirement management."""
    await ctx.send_help(ctx.command)


@collector.command(name="set")
@checks.is_staff()
async def collector_set(
    ctx: commands.Context["BallsDexBot"],
    countryball: BallConverter,
    amount: int,
    special: SpecialConverter,
):
    """
    Set or update a collector requirement.

    Parameters
    ----------
    countryball: BallConverter
        The ball to set a requirement for.
    amount: int
        Minimum number the player must own (1–9999).
    special: SpecialConverter
        The special reward applied to the claimed collector ball.
    """
    if not (1 <= amount <= 9999):
        await ctx.send("Amount must be between 1 and 9999.", ephemeral=True)
        return

    _, created = await CollectorRequirement.objects.aupdate_or_create(
        ball=countryball,
        special=special,
        defaults={"amount": amount},
    )
    action = "Created" if created else "Updated"
    await ctx.send(
        f"{action} collector requirement: **{countryball.country}** — "
        f"own ≥ **{amount:,}** → **{special.name}**.",
        ephemeral=True,
    )
    log.info(
        f"{ctx.author} set collector requirement for {countryball.country} "
        f"(min={amount} special={special.name})",
        extra={"webhook": True},
    )


@collector.command(name="bulk")
@checks.is_staff()
async def collector_bulk(ctx: commands.Context["BallsDexBot"]):
    """Add multiple collector requirements at once via a modal form."""
    if ctx.interaction is None:
        await ctx.send(
            "This command must be used as a slash command to open the modal.",
            ephemeral=True,
        )
        return
    await ctx.interaction.response.send_modal(BulkAddModal())


@collector.command(name="delete")
@checks.is_staff()
async def collector_delete(
    ctx: commands.Context["BallsDexBot"],
    countryball: BallConverter,
    special: str | None = None,
):
    """
    Delete collector requirement(s) for a ball.

    Parameters
    ----------
    countryball: BallConverter
        The ball whose requirement(s) you want to remove.
    special: str | None
        Which specific special to remove. Leave empty to delete all for this ball.
    """
    qs = CollectorRequirement.objects.filter(ball=countryball)

    if special is not None:
        sp = await Special.objects.filter(name__iexact=special.strip()).afirst()
        if sp is None:
            sp_obj = await Special.objects.filter(
                name__icontains=special.strip()
            ).afirst()
        else:
            sp_obj = sp

        if sp_obj is None:
            await ctx.send(
                f"No requirement with special `{special}` found for "
                f"**{countryball.country}**.",
                ephemeral=True,
            )
            return
        qs = qs.filter(special=sp_obj)

    deleted, _ = await qs.adelete()
    if deleted:
        target = f"**{special}**" if special else "all requirements"
        await ctx.send(
            f"Deleted {target} for **{countryball.country}** "
            f"({deleted} requirement(s) removed).",
            ephemeral=True,
        )
        log.info(
            f"{ctx.author} deleted collector requirement(s) for "
            f"{countryball.country} (special={special or 'all'})",
            extra={"webhook": True},
        )
    else:
        await ctx.send(
            f"No collector requirement(s) found for **{countryball.country}**"
            + (f" with special `{special}`" if special else "") + ".",
            ephemeral=True,
        )


@collector.command(name="view")
@checks.is_staff()
async def collector_view(
    ctx: commands.Context["BallsDexBot"],
    countryball: BallConverter,
):
    """
    View all collector requirements for a ball.

    Parameters
    ----------
    countryball: BallConverter
        The ball to inspect.
    """
    reqs = [
        r async for r in
        CollectorRequirement.objects.filter(ball=countryball)
        .select_related("special")
        .order_by("amount")
        .aiterator()
    ]
    if not reqs:
        await ctx.send(
            f"No collector requirement exists for **{countryball.country}**.",
            ephemeral=True,
        )
        return

    lines: list[str] = []
    for r in reqs:
        claim_count = await CollectorClaim.objects.filter(requirement=r).acount()
        lines.append(
            f"• ≥**{r.amount:,}** → **{r.special.name}** "
            f"(ID `{r.special_id}`) — {claim_count:,} claimed"
        )

    await ctx.send(
        f"**Collector Requirements — {countryball.country}**\n" + "\n".join(lines),
        ephemeral=True,
    )
