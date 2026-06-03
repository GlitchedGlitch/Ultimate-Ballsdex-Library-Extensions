"""
Collector package for BallsDex :)))
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
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

# Claimed format: {ball_id: {special_id: set(user_ids)}}
# This allows tracking claims per ball+special combination


# ── Persistence ───────────────────────────────────────────────────────────────

def _save_requirements(requirements: dict[int, list[dict]]) -> None:
    try:
        with open(REQUIREMENTS_FILE, "w") as f:
            json.dump(requirements, f, indent=2)
    except Exception:
        log.warning("Could not save requirements.txt", exc_info=True)


def _load_requirements() -> dict[int, list[dict]]:
    if not os.path.isfile(REQUIREMENTS_FILE):
        return {}
    try:
        with open(REQUIREMENTS_FILE, "r") as f:
            raw = json.load(f)
        result: dict[int, list[dict]] = {}
        for k, v in raw.items():
            ball_id = int(k)
            # Backward compat: old format was a single dict
            if isinstance(v, dict):
                result[ball_id] = [v]
            else:
                result[ball_id] = v
        return result
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
    name = name.strip().lower()
    for ball in balls_cache.values():
        if ball.country.lower() == name:
            return ball
    return None


async def _find_special_by_name(name: str):
    name_lower = name.strip().lower()
    for s in await Special.all():
        if s.name.lower() == name_lower:
            return s
    return None


def _get_reqs(bot: "BallsDexBot", ball_id: int) -> list[dict]:
    return bot.collector_requirements.get(ball_id, [])


def _claimed_key(ball_id: int, special_id: int) -> str:
    return f"{ball_id}:{special_id}"


def _has_claimed(bot: "BallsDexBot", user_id: int, ball_id: int, special_id: int) -> bool:
    return user_id in bot.collector_claimed.get(_claimed_key(ball_id, special_id), set())


def _mark_claimed(bot: "BallsDexBot", user_id: int, ball_id: int, special_id: int) -> None:
    key = _claimed_key(ball_id, special_id)
    bot.collector_claimed.setdefault(key, set()).add(user_id)


# ── Claim view (multi-requirement) ────────────────────────────────────────────

class ClaimSelectView(discord.ui.View):
    def __init__(
        self,
        bot: "BallsDexBot",
        interaction: discord.Interaction,
        ball,
        player: "Player",
        count: int,
        eligible: list[dict],
    ):
        super().__init__(timeout=60)
        self.bot = bot
        self.original = interaction
        self.ball = ball
        self.player = player
        self.count = count

        for req in eligible:
            btn = discord.ui.Button(
                label=f"{req['special_name']} — {req['amount']}",
                style=discord.ButtonStyle.primary,
            )
            async def callback(itx: discord.Interaction, r=req):
                await itx.response.defer(ephemeral=True)
                await _do_claim(self.bot, itx, self.ball, self.player, r)
                self.stop()
            btn.callback = callback
            self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original.user.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        try:
            await self.original.edit_original_response(view=self)
        except Exception:
            pass


async def _do_claim(
    bot: "BallsDexBot",
    interaction: discord.Interaction,
    ball,
    player: "Player",
    req: dict,
) -> None:
    ball_id = ball.pk
    special_id = req["special_id"]

    if _has_claimed(bot, interaction.user.id, ball_id, special_id):
        await interaction.followup.send(
            f"You already claimed **{req['special_name']} {ball.country}**!",
            ephemeral=True,
        )
        return

    special = await Special.get_or_none(pk=special_id)
    if special is None:
        await interaction.followup.send(
            "The reward special no longer exists. Contact an admin.", ephemeral=True
        )
        return

    new_instance = await BallInstance.create(
        player=player,
        ball=ball,
        special=special,
        attack_bonus=0,
        health_bonus=0,
        server_id=interaction.guild_id,
    )
    _mark_claimed(bot, interaction.user.id, ball_id, special_id)

    log.info(
        "User %s claimed collector %s / special %s (#%X)",
        interaction.user, ball.country, special.name, new_instance.pk,
    )
    await log_action(
        f"{interaction.user.name} claimed {ball.country} `(#{new_instance.pk:0X})`. "
        f"(Special={special.name} ATK={new_instance.attack_bonus:+d} HP={new_instance.health_bonus:+d})",
        interaction.client,
    )

    emoji_str = special.emoji or ""
    await interaction.followup.send(
        f"Congratulations! You claimed **{emoji_str} {special.name} {ball.country}** "
        f"collector {settings.collectible_name}!\n"
        f"Added to your collection as `#{new_instance.pk:0X}`.",
        ephemeral=True,
    )


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

    def __init__(self, bot: "BallsDexBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
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

    async def _process(self, interaction: discord.Interaction):
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

            ball = _find_ball_by_name(ball_name)
            if ball is None:
                errors.append(f"`{line}` — {settings.collectible_name} `{ball_name}` not found")
                continue

            special = await _find_special_by_name(special_name)
            if special is None:
                errors.append(f"`{line}` — special `{special_name}` not found")
                continue

            reqs = self.bot.collector_requirements.setdefault(ball.pk, [])
            # Replace existing entry for same ball+special, otherwise append
            for i, r in enumerate(reqs):
                if r["special_id"] == special.pk:
                    reqs[i] = {
                        "ball_id": ball.pk, "ball_name": ball.country,
                        "amount": amount, "special_id": special.pk, "special_name": special.name,
                    }
                    break
            else:
                reqs.append({
                    "ball_id": ball.pk, "ball_name": ball.country,
                    "amount": amount, "special_id": special.pk, "special_name": special.name,
                })
            added.append(f"**{ball.country}** — ≥{amount} → {special.name}")

        if added:
            _save_requirements(self.bot.collector_requirements)

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
            await log_action(
                f"{interaction.user.name} bulk added {len(added)} collector requirement(s). "
                f"Errors: {len(errors)}",
                interaction.client,
            )


# ── /admin collector ──────────────────────────────────────────────────────────

class CollectorAdminGroup(app_commands.Group):
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
        countryball=f"The {settings.collectible_name} to set a requirement for",
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
        reqs = self.bot.collector_requirements.setdefault(ball.pk, [])
        for i, r in enumerate(reqs):
            if r["special_id"] == special.pk:
                reqs[i] = {
                    "ball_id": ball.pk, "ball_name": ball.country,
                    "amount": amount, "special_id": special.pk, "special_name": special.name,
                }
                break
        else:
            reqs.append({
                "ball_id": ball.pk, "ball_name": ball.country,
                "amount": amount, "special_id": special.pk, "special_name": special.name,
            })
        _save_requirements(self.bot.collector_requirements)

        await interaction.response.send_message(
            f"Collector requirement set: **{ball.country}** — ≥**{amount}** → **{special.name}**.",
            ephemeral=True,
        )
        await log_action(
            f"{interaction.user.name} set collector requirement for "
            f"{ball.country} `({ball.pk:0X})`. (Minimum={amount} Special={special.name})",
            interaction.client,
        )

    @app_commands.command(name="bulk", description="Add multiple collector requirements at once")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def collector_bulk(self, interaction: discord.Interaction["BallsDexBot"]):
        await interaction.response.send_modal(BulkAddModal(self.bot))

    @app_commands.command(name="delete", description="Delete a collector requirement")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.describe(
        countryball="The ball whose requirement you want to remove",
        special="Which specific requirement to delete (leave empty to delete all for this ball)",
    )
    async def collector_delete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
        special: str | None = None,
    ):
        ball = countryball
        reqs = self.bot.collector_requirements.get(ball.pk, [])
        if not reqs:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        if special is None:
            # Delete all requirements for this ball
            del self.bot.collector_requirements[ball.pk]
            # Clear all claims for this ball
            keys_to_del = [k for k in self.bot.collector_claimed if k.startswith(f"{ball.pk}:")]
            for k in keys_to_del:
                del self.bot.collector_claimed[k]
            _save_requirements(self.bot.collector_requirements)
            await interaction.response.send_message(
                f"All collector requirements for **{ball.country}** deleted.", ephemeral=True
            )
            await log_action(
                f"{interaction.user.name} deleted all collector requirements for {ball.country}.",
                interaction.client,
            )
            return

        # Delete specific special by name or ID from autocomplete
        special_lower = special.strip().lower()
        new_reqs = [r for r in reqs if r["special_name"].lower() != special_lower and str(r["special_id"]) != special]
        if len(new_reqs) == len(reqs):
            await interaction.response.send_message(
                f"No requirement with special `{special}` found for **{ball.country}**.", ephemeral=True
            )
            return

        removed = [r for r in reqs if r not in new_reqs]
        if new_reqs:
            self.bot.collector_requirements[ball.pk] = new_reqs
        else:
            del self.bot.collector_requirements[ball.pk]

        for r in removed:
            key = _claimed_key(ball.pk, r["special_id"])
            self.bot.collector_claimed.pop(key, None)

        _save_requirements(self.bot.collector_requirements)
        names = ", ".join(r["special_name"] for r in removed)
        await interaction.response.send_message(
            f"Deleted **{ball.country}** — {names}.", ephemeral=True
        )
        await log_action(
            f"{interaction.user.name} deleted collector requirement for "
            f"{ball.country} (Special={names}).",
            interaction.client,
        )

    @collector_delete.autocomplete("special")
    async def delete_special_autocomplete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        current: str,
    ) -> list[app_commands.Choice[str]]:
        # Try to find which ball was selected from the other param
        # We can't easily cross-reference, so show all specials in use
        seen: dict[str, str] = {}
        for reqs in self.bot.collector_requirements.values():
            for r in reqs:
                name = r["special_name"]
                if current.lower() in name.lower():
                    seen[name.lower()] = name
        return [app_commands.Choice(name=n, value=n) for n in list(seen.values())[:25]]

    @app_commands.command(name="view", description="View collector requirements for a ball")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.describe(countryball=f"The {settings.collectible_name} to inspect")
    async def collector_view(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        ball = countryball
        reqs = self.bot.collector_requirements.get(ball.pk, [])
        if not reqs:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        lines = []
        for r in sorted(reqs, key=lambda x: x["amount"]):
            claimed_count = len(self.bot.collector_claimed.get(_claimed_key(ball.pk, r["special_id"]), set()))
            lines.append(
                f"• ≥**{r['amount']}** → **{r['special_name']}** (ID `{r['special_id']}`) — {claimed_count} claimed"
            )

        await interaction.response.send_message(
            f"**Collector Requirements — {ball.country}**\n" + "\n".join(lines),
            ephemeral=True,
        )


# ── Player-facing cog ─────────────────────────────────────────────────────────

class CollectorCog(commands.Cog):
    """Collector package"""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        if not hasattr(bot, "collector_requirements"):
            bot.collector_requirements: dict[int, list[dict]] = _load_requirements()
        if not hasattr(bot, "collector_claimed"):
            # {f"{ball_id}:{special_id}": set(user_ids)}
            bot.collector_claimed: dict[str, set[int]] = {}

    collector_group = app_commands.Group(
        name="collector",
        description="Collector commands",
    )

    # ── /collector claim ──────────────────────────────────────────────────────

    @collector_group.command(name="claim", description="Claim your collector ball reward")
    @app_commands.describe(countryball=f"The {settings.collectible_name} you want to claim")
    async def collector_claim(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
    ):
        await interaction.response.defer(ephemeral=True)

        ball = countryball
        ball_id = ball.pk
        raw = self.bot.collector_requirements.get(ball_id)
        if not raw:
            await interaction.followup.send(
                f"There is no collector requirement set for **{ball.country}**.", ephemeral=True
            )
            return

        reqs: list[dict] = [raw] if isinstance(raw, dict) else raw
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        count = await BallInstance.filter(player=player, ball=ball, deleted=False).count()

        BAR_LEN = 7
        BAR_FILL = "█"
        BAR_EMPTY = "░"

        def make_bar(current: int, required: int) -> str:
            ratio = min(current / required, 1.0)
            filled = round(BAR_LEN * ratio)
            pct = round(100 * current / required)
            return f"[{BAR_FILL * filled}{BAR_EMPTY * (BAR_LEN - filled)}] {current}/{required} {pct}%"

        # Build progress display
        lines = [f"Collector requirements for **{ball.country}**"]
        eligible: list[dict] = []
        already_claimed: list[dict] = []

        for r in sorted(reqs, key=lambda x: x["amount"]):
            bar = make_bar(count, r["amount"])
            claimed = _has_claimed(self.bot, interaction.user.id, ball_id, r["special_id"])
            lines.append(f"{r['special_name']} - {bar}")
            if not claimed and count >= r["amount"]:
                eligible.append(r)
            if claimed:
                already_claimed.append(r)

        progress_text = "\n".join(lines)

        if not eligible:
            if already_claimed and len(already_claimed) == len(reqs):
                await interaction.followup.send(
                    progress_text + "\n\nYou have already claimed all available rewards!",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(progress_text, ephemeral=True)
            return

        if len(eligible) == 1:
            await interaction.followup.send(progress_text, ephemeral=True)
            await _do_claim(self.bot, interaction, ball, player, eligible[0])
        else:
            view = ClaimSelectView(self.bot, interaction, ball, player, count, eligible)
            await interaction.followup.send(
                progress_text + "\n\nYou qualify for multiple rewards! Pick one:",
                view=view,
                ephemeral=True,
            )

    # ── /collector list ───────────────────────────────────────────────────────

    @collector_group.command(name="list", description="List all active collector requirements")
    @app_commands.describe(
        reverse="Reverse the output of the list",
        special="Filter by special name",
    )
    async def collector_list(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        reverse: bool = False,
        special: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)

        requirements = self.bot.collector_requirements
        if not requirements:
            await interaction.followup.send(
                "There are no collector requirements set up yet.", ephemeral=True
            )
            return

        # Flatten all requirements — handle both old dict and new list format
        all_reqs: list[dict] = []
        for reqs in requirements.values():
            if isinstance(reqs, dict):
                reqs = [reqs]
            for r in reqs:
                if special is None or r["special_name"].lower() == special.strip().lower():
                    all_reqs.append(r)

        if not all_reqs:
            await interaction.followup.send(
                f"No requirements found for special `{special}`.", ephemeral=True
            )
            return

        all_reqs.sort(key=lambda r: r["amount"], reverse=reverse)

        # Group by amount
        grouped: dict[int, list[dict]] = defaultdict(list)
        for r in all_reqs:
            grouped[r["amount"]].append(r)

        entries: list[tuple[str, str]] = []
        for amount in grouped:
            reqs_in_group = grouped[amount]
            lines: list[str] = []
            for r in reqs_in_group:
                emoji = _ball_emoji(self.bot, r["ball_id"])
                lines.append(f"* {emoji} {r['ball_name']} → *{r['special_name']}*")

            # Truncate field value to Discord's 1024 char limit
            field_value = "\n".join(lines)
            if len(field_value) > 1020:
                field_value = field_value[:1020] + "\n..."

            entries.append((f"Minimum: {amount}", field_value))

        total_pages = -(-len(entries) // GROUPS_PER_PAGE)
        if special:

        source = FieldPageSource(entries, per_page=GROUPS_PER_PAGE, inline=False)
        source.embed.title = "Collector List"
        source.embed.color = discord.Color.gold()

        pages = Pages(source, interaction=interaction)
        await pages.start(ephemeral=True)

    @collector_list.autocomplete("special")
    async def list_special_autocomplete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        current: str,
    ) -> list[app_commands.Choice[str]]:
        seen: dict[str, str] = {}
        for reqs in self.bot.collector_requirements.values():
            for r in reqs:
                name = r["special_name"]
                if current.lower() in name.lower():
                    seen[name.lower()] = name
        return [app_commands.Choice(name=n, value=n) for n in list(seen.values())[:25]]
