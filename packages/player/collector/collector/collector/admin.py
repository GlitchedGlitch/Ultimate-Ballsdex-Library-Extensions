"""
Admin commands for the collector package :))
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils import checks
from ballsdex.core.utils.menus import Menu, TextFormatter
from bd_models.models import Ball, Special
from collector.models import CollectorClaim, CollectorRequirement
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.admin.collector")


# ── Converters ───────────────────────────────────────────────────────────────

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


# ── Autocomplete functions ───────────────────────────────────────────────────

async def _ball_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """All enabled balls."""
    results: list[app_commands.Choice[str]] = []
    async for ball in (
        Ball.objects.filter(enabled=True, country__icontains=current)
        .order_by("country")
        .aiterator()
    ):
        results.append(app_commands.Choice(name=ball.country, value=ball.country))
        if len(results) >= 25:
            break
    return results


async def _ball_with_req_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Only balls that have at least one requirement (for delete/view)."""
    results: list[app_commands.Choice[str]] = []
    seen: set[int] = set()
    async for req in (
        CollectorRequirement.objects
        .select_related("ball")
        .filter(ball__enabled=True, ball__country__icontains=current)
        .order_by("ball__country")
        .aiterator()
    ):
        if req.ball_id not in seen:
            seen.add(req.ball_id)
            results.append(
                app_commands.Choice(name=req.ball.country, value=req.ball.country)
            )
            if len(results) >= 25:
                break
    return results


async def _special_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """All specials."""
    results: list[app_commands.Choice[str]] = []
    async for special in (
        Special.objects.filter(name__icontains=current)
        .order_by("name")
        .aiterator()
    ):
        results.append(app_commands.Choice(name=special.name, value=special.name))
        if len(results) >= 25:
            break
    return results


async def _special_with_req_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Only specials that have a requirement for the already-chosen ball."""
    ball_name = getattr(interaction.namespace, "countryball", None)
    qs = CollectorRequirement.objects.select_related("special")
    if ball_name:
        qs = qs.filter(ball__country__iexact=ball_name)
    if current:
        qs = qs.filter(special__name__icontains=current)

    results: list[app_commands.Choice[str]] = []
    seen: set[int] = set()
    async for req in qs.order_by("special__name").aiterator():
        if req.special_id not in seen:
            seen.add(req.special_id)
            results.append(
                app_commands.Choice(name=req.special.name, value=req.special.name)
            )
            if len(results) >= 25:
                break
    return results


# ── Helper: ephemeral for slash, public for prefix ───────────────────────────

def _ephemeral(ctx: commands.Context) -> bool:
    """Return True for slash commands, False for prefix commands."""
    return ctx.interaction is not None


# ── Bulk modal ───────────────────────────────────────────────────────────────

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
        modal = CogBulkAddModal()
        modal.requirements_input._value = self.requirements_input.value
        await modal._process(interaction)


class BulkAddButtonView(discord.ui.View):
    """Button view that opens the bulk add modal."""

    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=300)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "This button is not for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="Open Bulk Add Modal",
        style=discord.ButtonStyle.primary,
    )
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BulkAddModal())


# ── Helper: build paginated list ─────────────────────────────────────────────

async def _build_collector_list(
    bot: "BallsDexBot",
    special: str | None = None,
    reverse: bool = False,
) -> tuple[discord.ui.LayoutView, Menu] | tuple[None, None]:
    """Build the paginated collector list view. Returns (view, menu)."""
    from .cog import ChunkedCollectorSource, _ball_emoji

    qs = CollectorRequirement.objects.select_related("ball", "special")
    if special:
        qs = qs.filter(special__name__iexact=special.strip())
    qs = qs.order_by(
        "-amount" if reverse else "amount",
        "ball__country",
    )

    all_reqs = [r async for r in qs.aiterator()]
    if not all_reqs:
        return None, None

    entries: list[tuple[str, int]] = []
    for r in all_reqs:
        emoji = _ball_emoji(bot, r.ball_id)
        if special:
            line = f"⋄ {emoji} {r.ball.country}"
        else:
            line = f"⋄ {emoji} {r.ball.country} -> *{r.special.name}*"
        entries.append((line, r.amount))

    title = f'"{special.strip()}" Collector List' if special else "Collector List"

    view = discord.ui.LayoutView()
    container = discord.ui.Container()

    header = discord.ui.Section(
        discord.ui.TextDisplay(f"# {title}"),
        accessory=discord.ui.Thumbnail(
            bot.user.display_avatar.url if bot.user else ""
        ),
    )
    container.add_item(header)
    container.add_item(discord.ui.Separator())

    text_display = discord.ui.TextDisplay("")
    container.add_item(text_display)
    view.add_item(container)

    source = ChunkedCollectorSource(entries, max_blocks_per_page=7, max_lines_per_page=18)
    formatter = TextFormatter(text_display)

    menu = Menu(bot, view, source, formatter)
    await menu.init(container=container)

    return view, menu


# ── Command group ─────────────────────────────────────────────────────────────

@commands.hybrid_group()
@checks.is_staff()
async def collector(ctx: commands.Context["BallsDexBot"]):
    """
    Collector requirement management.
    """
    await ctx.send_help(ctx.command)


@collector.command(name="list")
@checks.is_staff()
@app_commands.describe(
    special="Filter by special name",
    reverse="Reverse the output of the list",
)
async def collector_list(
    ctx: commands.Context["BallsDexBot"],
    special: str | None = None,
    reverse: bool = False,
):
    """
    List all active collector requirements.

    Flags:
      special
        Filter by special name.
      reverse
        Reverse the output of the list.
    """
    view, menu = await _build_collector_list(ctx.bot, special, reverse)
    if view is None:
        msg = (
            f"No requirements found for special `{special}`."
            if special
            else "There are no collector requirements set up yet."
        )
        await ctx.send(msg, ephemeral=_ephemeral(ctx))
        return

    await ctx.send(view=view, ephemeral=_ephemeral(ctx))


@collector.command(name="set")
@checks.is_staff()
@app_commands.describe(
    countryball="The ball to set a requirement for",
    amount="Minimum number the player must own (1–9999)",
    special="The special reward applied to the claimed collector ball",
)
@app_commands.autocomplete(countryball=_ball_autocomplete, special=_special_autocomplete)
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
    countryball: str
        The ball to set a requirement for.
    amount: int
        Minimum number the player must own (1–9999).
    special: str
        The special reward applied to the claimed collector ball.
    """
    if not (1 <= amount <= 9999):
        await ctx.send("Amount must be between 1 and 9999.", ephemeral=_ephemeral(ctx))
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
        ephemeral=_ephemeral(ctx),
    )
    log.info(
        f"{ctx.author} set collector requirement for {countryball.country} "
        f"(min={amount} special={special.name})",
        extra={"webhook": True},
    )


@collector.command(name="bulk")
@checks.is_staff()
async def collector_bulk(ctx: commands.Context["BallsDexBot"]):
    """
    Add multiple collector requirements at once via a modal form.

    Click the button below to open the bulk add form.
    """
    if ctx.interaction is not None:
        await ctx.interaction.response.send_modal(BulkAddModal())
        return
    view = BulkAddButtonView(ctx)
    await ctx.send(
        "Click the button below to bulk add collector requirements:",
        view=view,
    )


@collector.command(name="delete")
@checks.is_staff()
@app_commands.describe(
    countryball="The ball whose requirement(s) you want to remove",
    special="Which specific special to remove (leave empty to delete all for this ball)",
)
@app_commands.autocomplete(
    countryball=_ball_with_req_autocomplete,
    special=_special_with_req_autocomplete,
)
async def collector_delete(
    ctx: commands.Context["BallsDexBot"],
    countryball: BallConverter,
    special: str | None = None,
):
    """
    Delete collector requirement(s) for a ball.

    Parameters
    ----------
    countryball: str
        The ball whose requirement(s) you want to remove.
    special: str | None
        Which specific special to remove (leave empty to delete all for this ball).
    """
    qs = CollectorRequirement.objects.filter(ball=countryball)

    if special is not None:
        sp_obj = await Special.objects.filter(name__iexact=special.strip()).afirst()
        if sp_obj is None:
            sp_obj = await Special.objects.filter(
                name__icontains=special.strip()
            ).afirst()
        if sp_obj is None:
            await ctx.send(
                f"No requirement with special `{special}` found for "
                f"**{countryball.country}**.",
                ephemeral=_ephemeral(ctx),
            )
            return
        qs = qs.filter(special=sp_obj)

    deleted, _ = await qs.adelete()
    if deleted:
        target = f"**{special}**" if special else "all requirements"
        await ctx.send(
            f"Deleted {target} for **{countryball.country}** "
            f"({deleted} requirement(s) removed).",
            ephemeral=_ephemeral(ctx),
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
            ephemeral=_ephemeral(ctx),
        )


@collector.command(name="view")
@checks.is_staff()
@app_commands.describe(countryball="The ball to inspect")
@app_commands.autocomplete(countryball=_ball_with_req_autocomplete)
async def collector_view(
    ctx: commands.Context["BallsDexBot"],
    countryball: BallConverter,
):
    """
    View all collector requirements for a ball.

    Parameters
    ----------
    countryball: str
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
            ephemeral=_ephemeral(ctx),
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
        ephemeral=_ephemeral(ctx),
    )
