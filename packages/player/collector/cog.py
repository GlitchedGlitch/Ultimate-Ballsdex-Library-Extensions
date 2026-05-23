"""
Collector package for BallsDex

Commands:
  /collector claim  — claim a collector ball if requirements are met
  /collector list   — paginated list of active requirements
  /admin collector set    — set a requirement (admin only)
  /admin collector bulk   — set multiple requirements at once (admin only)
  /admin collector delete — delete a requirement (admin only)
  /admin collector view   — inspect a requirement (admin only)
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput

from ballsdex.core.models import BallInstance, Player, Special
from ballsdex.core.models import balls as balls_cache
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")

GROUPS_PER_PAGE = 7
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
    ball = balls_cache.get(ball_id)
    if ball and ball.emoji_id:
        emoji = bot.get_emoji(ball.emoji_id)
        if emoji:
            return str(emoji)
    return "•"


def _find_ball_by_name(name: str):
    """Find a ball from the cache by name (case-insensitive)."""
    name = name.strip().lower()
    for ball in balls_cache.values():
        if ball.country.lower() == name:
            return ball
    return None


async def _find_special_by_name(name: str):
    """Find a special by name (case-insensitive)."""
    name = name.strip().lower()
    special = await Special.get_or_none(name__iexact=name)
    return special


# ── Bulk modal ────────────────────────────────────────────────────────────────

class BulkAddModal(Modal, title="Bulk Add Collector Requirements"):
    """
    Modal for adding multiple collector requirements at once.

    Format (one per line):
      BallName | Amount | SpecialName

    Example:
      France | 5 | Shiny
      Germany | 10 | Gold
      Japan | 3 | Shiny
    """

    requirements_input = TextInput(
        label="Requirements (BallName | Amount | SpecialName)",
        style=discord.TextStyle.paragraph,
        placeholder=(
            "One requirement per line:\n"
            "France | 5 | Shiny\n"
            "Germany | 10 | Gold\n"
            "Japan | 3 | Shiny"
        ),
        required=True,
        max_length=4000,
    )

    def __init__(self, bot: "BallsDexBot", interaction: discord.Interaction):
        super().__init__()
        self.bot = bot
        self.original_interaction = interaction

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        lines = [l.strip() for l in self.requirements_input.value.splitlines() if l.strip()]
        if not lines:
            await interaction.followup.send("No requirements provided.", ephemeral=True)
            return

        added:   list[str] = []
        skipped: list[str] = []
        errors:  list[str] = []

        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 3:
                errors.append(f"`{line}` — must be `BallName | Amount | SpecialName`")
                continue

            ball_name, amount_str, special_name = parts

            # Validate amount
            try:
                amount = int(amount_str)
                if not (1 <= amount <= 9999):
                    raise ValueError
            except ValueError:
                errors.append(f"`{line}` — amount must be a number between 1 and 9999")
                continue

            # Find ball
            ball = _find_ball_by_name(ball_name)
            if ball is None:
                errors.append(f"`{line}` — ball `{ball_name}` not found")
                continue

            # Find special
            special = await _find_special_by_name(special_name)
            if special is None:
                errors.append(f"`{line}` — special `{special_name}` not found")
                continue

            # Set requirement
            self.bot.collector_requirements[ball.pk] = {
                "ball_id": ball.pk,
                "ball_name": ball.country,
                "amount": amount,
                "special_id": special.pk,
                "special_name": special.name,
            }
            self.bot.collector_claimed.pop(ball.pk, None)
            added.append(f"**{ball.country}** — ≥{amount} → {special.name}")

        if added:
            _save_requirements(self.bot.collector_requirements)

        # Build result message
        result_lines: list[str] = []
        if added:
            result_lines.append(f"**Added {len(added)} requirement(s):**")
            result_lines.extend(added)
        if skipped:
            result_lines.append(f"\n**Skipped {len(skipped)}:**")
            result_lines.extend(skipped)
        if errors:
            result_lines.append(f"\n**Errors ({len(errors)}):**")
            result_lines.extend(errors)

        result_text = "\n".join(result_lines)

        # Split if too long for one message
        if len(result_text) > 1900:
            result_text = result_text[:1900] + "\n... (truncated)"

        await interaction.followup.send(result_text, ephemeral=True)

        # Log to admin channel
        if added:
            await log_action(
                f"{interaction.user.name} bulk added {len(added)} collector requirement(s). "
                f"Errors: {len(errors)}",
                interaction.client,
            )
        log.info(
            "Bulk add by %s: %d added, %d errors",
            interaction.user, len(added), len(errors),
        )


# ── Bulk confirm view ─────────────────────────────────────────────────────────

class BulkConfirmView(discord.ui.View):
    """
    Shown before opening the bulk modal — gives the admin the format guide
    and a button to open the input modal.
    """

    def __init__(self, bot: "BallsDexBot", interaction: discord.Interaction):
        super().__init__(timeout=120)
        self.bot = bot
        self.interaction = interaction

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        try:
            await self.interaction.edit_original_response(view=self)
        except Exception:
            pass

    @discord.ui.button(label="Open Input", style=discord.ButtonStyle.success, emoji="📝")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BulkAddModal(self.bot, self.interaction))
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Bulk add cancelled.", embed=None, view=None
        )
        self.stop()


# ── /admin collector — standalone Group ───────────────────────────────────────

class CollectorAdminGroup(app_commands.Group):
    """Manage collector requirements"""

    def __init__(self, bot: "BallsDexBot"):
        super().__init__(
            name="collector",
            description="Manage collector requirements",
            default_permissions=discord.Permissions(manage_guild=True),
        )
        self.bot = bot

    @app_commands.command(name="set", description="Set or update a collector requirement")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.describe(
        countryball="The ball to set a requirement for",
        amount="Minimum number the player must own",
        special="The special reward the player receives",
    )
    async def collector_set(
        self,
        interaction: discord.Interaction["BallsDexBot"],
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

        await interaction.response.send_message(
            f"Collector requirement set: **{ball.country}** — "
            f"own ≥ **{amount}** → reward **{special.name}**.\n"
            f"Previous claims for this ball have been reset.",
            ephemeral=True,
        )
        await log_action(
            f"{interaction.user.name} set collector requirement for "
            f"{ball.country} `({ball.pk:0X})`. "
            f"(Minimum={amount} Special={special.name})",
            interaction.client,
        )

    @app_commands.command(
        name="bulk",
        description="Add multiple collector requirements at once",
    )
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def collector_bulk(
        self,
        interaction: discord.Interaction["BallsDexBot"],
    ):
        embed = discord.Embed(
            title="📋 Bulk Add Collector Requirements",
            description=(
                "Add multiple requirements at once using the format below.\n\n"
                "**Format** (one per line):\n"
                "```\n"
                "BallName | Amount | SpecialName\n"
                "```\n"
                "**Example:**\n"
                "```\n"
                "France | 5 | Shiny\n"
                "Germany | 10 | Gold\n"
                "Japan | 3 | Shiny\n"
                "```\n\n"
                "⚠️ Ball names and special names must match exactly as they appear in the bot.\n"
                "Existing requirements for the same ball will be **overwritten**.\n"
                "Claims for updated balls will be **reset**.\n\n"
                "Press **Open Input** to enter your requirements."
            ),
            color=discord.Color.blurple(),
        )
        view = BulkConfirmView(self.bot, interaction)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="delete", description="Delete a collector requirement")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.describe(countryball="The ball whose requirement you want to remove")
    async def collector_delete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        ball = countryball
        if ball.pk not in self.bot.collector_requirements:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        del self.bot.collector_requirements[ball.pk]
        self.bot.collector_claimed.pop(ball.pk, None)
        _save_requirements(self.bot.collector_requirements)

        await interaction.response.send_message(
            f"🗑️ Collector requirement for **{ball.country}** has been deleted.",
            ephemeral=True,
        )
        await log_action(
            f"{interaction.user.name} deleted collector requirement for "
            f"{ball.country} `({ball.pk:0X})`.",
            interaction.client,
        )

    @app_commands.command(name="view", description="View a specific collector requirement")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.describe(countryball="The ball to inspect")
    async def collector_view(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
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


# ── Player-facing cog ─────────────────────────────────────────────────────────

class CollectorCog(commands.Cog):
    """Collector package — player commands."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        if not hasattr(bot, "collector_requirements"):
            bot.collector_requirements: dict[int, dict] = _load_requirements()
        if not hasattr(bot, "collector_claimed"):
            bot.collector_claimed: dict[int, set[int]] = {}

    collector_group = app_commands.Group(
        name="collector",
        description="Collector commands",
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
        await log_action(
            f"{interaction.user.name} claimed {ball.country} "
            f"`(#{new_instance.pk:0X})`. "
            f"(Special={special.name} "
            f"ATK={new_instance.attack_bonus:+d} "
            f"HP={new_instance.health_bonus:+d})",
            interaction.client,
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

        sorted_reqs = sorted(requirements.values(), key=lambda r: r["amount"], reverse=reverse)
        grouped: dict[int, list[dict]] = {}
        for req in sorted_reqs:
            grouped.setdefault(req["amount"], []).append(req)
        sorted_amounts = list(grouped.keys())

        entries: list[tuple[str, str]] = []
        for amount in sorted_amounts:
            reqs = grouped[amount]
            lines = [
                f"* {_ball_emoji(self.bot, r['ball_id'])} {r['ball_name']} → *{r['special_name']}*"
                for r in reqs
            ]
            entries.append((f"Minimum: {amount}", "\n".join(lines)))

        total_pages = -(-len(entries) // GROUPS_PER_PAGE)
        sort_label = "Highest → Lowest" if reverse else "Lowest → Highest"

        source = FieldPageSource(entries, per_page=GROUPS_PER_PAGE, inline=False)
        source.embed.title = "Collector List"
        source.embed.color = discord.Color.gold()

        if total_pages > 1:
            source.embed.set_footer(
                text=f"{len(requirements)} requirement(s) • Sorted: {sort_label}"
            )
        else:
            source.embed.set_footer(text=f"{len(requirements)} requirement(s)")

        pages = Pages(source, interaction=interaction)
        await pages.start(ephemeral=True)
