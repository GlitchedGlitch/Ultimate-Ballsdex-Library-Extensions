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
from ballsdex.packages.collector.models import CollectorClaim, CollectorRequirement
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collector")

GROUPS_PER_PAGE = 7

# ── Requirements.txt migration ────────────────────────────────────────────────

REQUIREMENTS_FILE = "/code/ballsdex/packages/collector/requirements.txt"
MIGRATION_MARKER = "/code/ballsdex/packages/collector/.requirements_migrated"

async def _migrate_requirements():
    """
    One-time migration: read requirements.txt JSON, erase existing requirements,
    and import all from the file.
    Expected format:
    {
      "ball_id": [
        {"ball_id": 1, "ball_name": "...", "amount": 3, "special_id": 1, "special_name": "..."},
        ...
      ],
      ...
    }
    Skips if migration already done or if requirements.txt is empty/missing.
    """
    log.info("Checking requirements.txt migration...")

    if os.path.isfile(MIGRATION_MARKER):
        log.info("Migration already completed (marker file exists).")
        return
    if not os.path.isfile(REQUIREMENTS_FILE):
        log.info("No requirements.txt file found at %s", REQUIREMENTS_FILE)
        return

    try:
        with open(REQUIREMENTS_FILE, "r") as f:
            raw = f.read().strip()
        log.info("Read requirements.txt: %s bytes", len(raw))

        if not raw or raw == "{}":
            log.info("requirements.txt is empty, skipping migration.")
            return

        data = json.loads(raw)
        if not data:
            log.info("requirements.txt contains empty JSON, skipping migration.")
            return

        # ── ERASE existing requirements ───────────────────────────────────────
        existing_count = await CollectorRequirement.all().count()
        if existing_count > 0:
            log.info("Erasing %s existing CollectorRequirement entries...", existing_count)
            # Delete all existing requirements (claims will cascade or be orphaned)
            await CollectorRequirement.all().delete()
            log.info("Existing requirements erased.")

        migrated = 0
        errors = 0

        # Expected format: {"ball_id": [{"ball_id": 1, "ball_name": "...", "amount": 3, "special_id": 1, "special_name": "..."}, ...]}
        if isinstance(data, dict):
            for ball_id_str, entries in data.items():
                if not isinstance(entries, list):
                    log.warning("Migration: expected list for ball_id %s, got %s, skipping.", ball_id_str, type(entries).__name__)
                    errors += 1
                    continue

                for entry in entries:
                    if not isinstance(entry, dict):
                        log.warning("Migration: expected dict entry, got %s, skipping.", type(entry).__name__)
                        errors += 1
                        continue

                    ball_id = entry.get("ball_id")
                    special_id = entry.get("special_id")
                    amount = entry.get("amount")

                    # Validate IDs
                    try:
                        ball_id = int(ball_id)
                        special_id = int(special_id)
                        amount = int(amount)
                        if not (1 <= amount <= 9999):
                            raise ValueError
                    except (ValueError, TypeError):
                        log.warning(
                            "Migration: invalid values ball_id=%s special_id=%s amount=%s, skipping.",
                            ball_id, special_id, amount
                        )
                        errors += 1
                        continue

                    # Verify ball exists - try cache first, then DB
                    ball = balls_cache.get(ball_id)
                    if ball is None:
                        # balls_cache might not be populated yet, try direct DB query
                        from ballsdex.core.models import Ball
                        ball = await Ball.get_or_none(pk=ball_id)
                        if ball is not None:
                            # Add to cache for future lookups
                            balls_cache[ball_id] = ball

                    if ball is None:
                        log.warning("Migration: ball_id %s not found in cache or database, skipping.", ball_id)
                        errors += 1
                        continue

                    special = await Special.get_or_none(pk=special_id)
                    if special is None:
                        log.warning("Migration: special_id %s not found in database, skipping.", special_id)
                        errors += 1
                        continue

                    await _upsert_req(ball_id, special_id, amount)
                    migrated += 1
                    log.info("Migrated requirement: ball_id=%s special_id=%s amount=%s", ball_id, special_id, amount)

        # Mark migration as done
        with open(MIGRATION_MARKER, "w") as f:
            f.write(f"Migrated {migrated} requirements. Errors: {errors}.\n")

        log.info("Migration complete: %s requirements migrated, %s errors.", migrated, errors)

    except json.JSONDecodeError as e:
        log.error("Failed to parse requirements.txt as JSON: %s", e)
    except Exception:
        log.exception("Failed to migrate requirements.txt")


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_reqs(ball_id: int) -> list[CollectorRequirement]:
    return await CollectorRequirement.filter(ball_id=ball_id).prefetch_related("special").order_by("amount")


async def _get_all_reqs(special_name: str | None = None) -> list[CollectorRequirement]:
    qs = CollectorRequirement.all().prefetch_related("ball", "special").order_by("ball__country", "amount")
    if special_name:
        reqs = await qs
        return [r for r in reqs if r.special.name.lower() == special_name.strip().lower()]
    return await qs


async def _upsert_req(ball_id: int, special_id: int, amount: int) -> CollectorRequirement:
    req, _ = await CollectorRequirement.get_or_create(
        ball_id=ball_id, special_id=special_id,
        defaults={"amount": amount},
    )
    if req.amount != amount:
        req.amount = amount
        await req.save()
    return req


async def _delete_req(ball_id: int, special_id: int | None = None):
    qs = CollectorRequirement.filter(ball_id=ball_id)
    if special_id:
        qs = qs.filter(special_id=special_id)
    await qs.delete()


async def _has_claimed(user_id: int, ball_id: int, special_id: int) -> bool:
    req = await CollectorRequirement.get_or_none(ball_id=ball_id, special_id=special_id)
    if not req:
        return False
    return await CollectorClaim.filter(
        player__discord_id=user_id,
        requirement_id=req.pk,
    ).exists()


async def _mark_claimed(player, ball_instance, req: CollectorRequirement):
    await CollectorClaim.create(
        player=player,
        ball_instance=ball_instance,
        requirement=req,
    )


# ── Ball emoji helper ─────────────────────────────────────────────────────────

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


# ── Claim helpers ─────────────────────────────────────────────────────────────

async def _do_claim(
    bot: "BallsDexBot",
    interaction: discord.Interaction,
    ball,
    player,
    req: CollectorRequirement,
) -> None:
    if await _has_claimed(interaction.user.id, req.ball_id, req.special_id):
        await interaction.followup.send(
            f"You already claimed **{req.special.name} {ball.country}**!", ephemeral=True
        )
        return

    special = await Special.get_or_none(pk=req.special_id)
    if special is None:
        await interaction.followup.send(
            "The reward special no longer exists. Contact an admin.", ephemeral=True
        )
        return

    new_instance = await BallInstance.create(
        player=player, ball=ball, special=special,
        attack_bonus=0, health_bonus=0, server_id=interaction.guild_id,
    )

    await _mark_claimed(player, new_instance, req)

    log.info("User %s claimed collector %s / special %s (#%X)",
             interaction.user, ball.country, special.name, new_instance.pk)

    emoji_str = special.emoji or ""
    await interaction.followup.send(
        f"Congratulations! You claimed **{emoji_str} {special.name} {ball.country}** "
        f"collector {settings.collectible_name}!\n"
        f"Added to your collection as `#{new_instance.pk:0X}`.",
        ephemeral=True,
    )


class ClaimSelectView(discord.ui.View):
    def __init__(self, bot, interaction, ball, player, eligible):
        super().__init__(timeout=60)
        self.bot = bot
        self.original = interaction
        for req in eligible:
            btn = discord.ui.Button(
                label=f"{req.special.name} — {req.amount}",
                style=discord.ButtonStyle.primary,
            )
            async def callback(itx: discord.Interaction, r=req):
                await itx.response.defer(ephemeral=True)
                await _do_claim(self.bot, itx, ball, player, r)
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

            await _upsert_req(ball.pk, special.pk, amount)
            added.append(f"**{ball.country}** — ≥{amount} -> {special.name}")

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
        await _upsert_req(ball.pk, special.pk, amount)
        await interaction.response.send_message(
            f"Collector requirement set: **{ball.country}** — ≥**{amount}** -> **{special.name}**.",
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
        special="Which specific requirement to delete (leave empty to delete all)",
    )
    async def collector_delete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform,
        special: str | None = None,
    ):
        ball = countryball
        reqs = await _get_reqs(ball.pk)
        if not reqs:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        if special is None:
            await _delete_req(ball.pk)
            await interaction.response.send_message(
                f"All collector requirements for **{ball.country}** deleted.", ephemeral=True
            )
            await log_action(
                f"{interaction.user.name} deleted all collector requirements for {ball.country}.",
                interaction.client,
            )
            return

        special_lower = special.strip().lower()
        target = next((r for r in reqs if r.special.name.lower() == special_lower), None)
        if not target:
            await interaction.response.send_message(
                f"No requirement with special `{special}` found for **{ball.country}**.", ephemeral=True
            )
            return

        await _delete_req(ball.pk, target.special_id)
        await interaction.response.send_message(
            f"Deleted **{ball.country}** — {target.special.name}.", ephemeral=True
        )
        await log_action(
            f"{interaction.user.name} deleted collector requirement for "
            f"{ball.country} (Special={target.special.name}).",
            interaction.client,
        )

    @collector_delete.autocomplete("special")
    async def delete_special_autocomplete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        current: str,
    ) -> list[app_commands.Choice[str]]:
        reqs = await _get_all_reqs()
        seen: dict[str, str] = {}
        for r in reqs:
            name = r.special.name
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
        reqs = await _get_reqs(ball.pk)
        if not reqs:
            await interaction.response.send_message(
                f"No collector requirement exists for **{ball.country}**.", ephemeral=True
            )
            return

        lines = []
        for r in reqs:
            count = await CollectorClaim.filter(requirement=r).count()
            lines.append(f"• ≥**{r.amount}** -> **{r.special.name}** — {count} claimed")

        await interaction.response.send_message(
            f"**Collector Requirements — {ball.country}**\n" + "\n".join(lines),
            ephemeral=True,
        )


# ── Player-facing cog ─────────────────────────────────────────────────────────

class CollectorCog(commands.Cog):
    """Collector package"""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    collector_group = app_commands.Group(
        name="collector",
        description="Collector commands",
    )

    @collector_group.command(name="claim", description="Claim your collector ball reward")
    @app_commands.describe(countryball=f"The {settings.collectible_name} to claim (leave empty to see what you can claim)")
    async def collector_claim(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallTransform | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        if countryball is None:
            all_reqs = await _get_all_reqs()
            if not all_reqs:
                await interaction.followup.send(
                    "There are no collector requirements set up yet.", ephemeral=True
                )
                return

            claimable: list[str] = []
            in_progress: list[str] = []

            for r in all_reqs:
                ball = balls_cache.get(r.ball_id)
                if not ball:
                    continue
                count = await BallInstance.filter(player=player, ball_id=r.ball_id, deleted=False).count()
                emoji = _ball_emoji(self.bot, r.ball_id)
                already = await _has_claimed(interaction.user.id, r.ball_id, r.special_id)
                if already:
                    continue
                if count >= r.amount:
                    claimable.append(f"• {emoji} **{ball.country}** — {r.special.name} ✅ ready")
                else:
                    pct = round(100 * count / r.amount)
                    in_progress.append(f"• {emoji} **{ball.country}** — {r.special.name} ({count}/{r.amount} · {pct}%)")

            if not claimable and not in_progress:
                await interaction.followup.send(
                    "You have already claimed all available collector rewards!", ephemeral=True
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

            lines.append(f"\nUse `/collector claim {settings.collectible_name}:` to claim a specific ball.")
            await interaction.followup.send("\n".join(lines), ephemeral=True)
            return

        ball = countryball
        reqs = await _get_reqs(ball.pk)
        if not reqs:
            await interaction.followup.send(
                f"There is no collector requirement set for **{ball.country}**.", ephemeral=True
            )
            return

        count = await BallInstance.filter(player=player, ball=ball, deleted=False).count()

        BAR_LEN, BAR_FILL, BAR_EMPTY = 7, "█", "░"

        def make_bar(current: int, required: int) -> str:
            ratio = min(current / required, 1.0)
            filled = round(BAR_LEN * ratio)
            pct = round(100 * current / required)
            return f"[{BAR_FILL * filled}{BAR_EMPTY * (BAR_LEN - filled)}] {current}/{required} {pct}%"

        lines = [f"Collector requirements for **{ball.country}**"]
        eligible = []

        for r in reqs:
            bar = make_bar(count, r.amount)
            claimed = await _has_claimed(interaction.user.id, ball.pk, r.special_id)
            lines.append(f"{r.special.name} - {bar}")
            if not claimed and count >= r.amount:
                eligible.append(r)

        progress_text = "\n".join(lines)

        if not eligible:
            await interaction.followup.send(progress_text, ephemeral=True)
            return

        if len(eligible) == 1:
            await interaction.followup.send(progress_text, ephemeral=True)
            await _do_claim(self.bot, interaction, ball, player, eligible[0])
        else:
            view = ClaimSelectView(self.bot, interaction, ball, player, eligible)
            await interaction.followup.send(
                progress_text + "\n\nYou qualify for multiple rewards! Pick one:",
                view=view, ephemeral=True,
            )

    @collector_group.command(name="list", description="List all active collector requirements")
    @app_commands.describe(
        special="Filter by special name",
        reverse="Reverse the output of the list",
    )
    async def collector_list(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        special: str | None = None,
        reverse: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        all_reqs = await _get_all_reqs(special)
        if not all_reqs:
            msg = f"No requirements found for special `{special}`." if special else "There are no collector requirements set up yet."
            await interaction.followup.send(msg, ephemeral=True)
            return

        all_reqs.sort(key=lambda r: r.amount, reverse=reverse)

        grouped: dict[int, list] = defaultdict(list)
        for r in all_reqs:
            grouped[r.amount].append(r)

        entries: list[tuple[str, str]] = []
        for amount in grouped:
            chunk_lines: list[str] = []
            chunk_num = 1
            for r in grouped[amount]:
                emoji = _ball_emoji(self.bot, r.ball_id)
                line = f"* {emoji} {r.ball.country}" if special else f"* {emoji} {r.ball.country} -> *{r.special.name}*"
                if chunk_lines and len("\n".join(chunk_lines + [line])) > 800:
                    header = f"**Minimum: {amount}**" if chunk_num == 1 else "\u200b"
                    entries.append((header, "\n".join(chunk_lines)))
                    chunk_lines = []
                    chunk_num += 1
                chunk_lines.append(line)
            if chunk_lines:
                header = f"**Minimum: {amount}**" if chunk_num == 1 else "\u200b"
                entries.append((header, "\n".join(chunk_lines)))

        source = FieldPageSource(entries, per_page=3, inline=False)
        source.embed.title = f'"{special.strip()}" Collector List' if special else "Collector List"
        source.embed.color = discord.Color.gold()
        pages = Pages(source, interaction=interaction)
        await pages.start(ephemeral=True)

    @collector_list.autocomplete("special")
    async def list_special_autocomplete(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        current: str,
    ) -> list[app_commands.Choice[str]]:
        reqs = await _get_all_reqs()
        seen: dict[str, str] = {}
        for r in reqs:
            name = r.special.name
            if current.lower() in name.lower():
                seen[name.lower()] = name
        return [app_commands.Choice(name=n, value=n) for n in list(seen.values())[:25]]
