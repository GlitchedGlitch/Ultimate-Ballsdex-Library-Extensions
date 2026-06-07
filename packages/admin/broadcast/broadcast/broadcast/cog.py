"""
Broadcast package for BallsDex v3
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from bd_models.models import GuildConfig, Player
from ballsdex.core.utils import checks

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.broadcast")

DELIVERY_LABELS = {
    "spawn": "Spawn Channels Only",
    "dms":   "Player DMs Only",
    "both":  "Spawn Channels + DMs",
}

COLOR_MAP = {
    "red":     discord.Color.red(),
    "blue":    discord.Color.blue(),
    "green":   discord.Color.green(),
    "yellow":  discord.Color.gold(),
    "purple":  discord.Color.purple(),
    "pink":    discord.Color.magenta(),
    "orange":  discord.Color.orange(),
    "white":   discord.Color.from_rgb(255, 255, 255),
    "black":   discord.Color.from_rgb(0, 0, 0),
    "gray":    discord.Color.greyple(),
    "grey":    discord.Color.greyple(),
    "cyan":    discord.Color.from_rgb(0, 255, 255),
    "teal":    discord.Color.teal(),
    "blurple": discord.Color.blurple(),
}

BAR_FILLED = "█"
BAR_EMPTY  = "░"
BAR_LEN    = 15


def _bar(current: int, total: int) -> str:
    if total == 0:
        return f"`{'░' * BAR_LEN}` 0%"
    filled = round(BAR_LEN * current / total)
    pct = round(100 * current / total)
    return f"`{BAR_FILLED * filled}{BAR_EMPTY * (BAR_LEN - filled)}` {pct}%"


def _parse_color(raw: str) -> Optional[discord.Color]:
    s = raw.strip().lower()
    if s in COLOR_MAP:
        return COLOR_MAP[s]
    m = re.match(r"^#?([0-9a-f]{6})$", s)
    if m:
        try:
            return discord.Color(int(m.group(1), 16))
        except ValueError:
            pass
    return None


# ── Confirm view ──────────────────────────────────────────────────────────────

class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.confirmed = False

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()
        self.stop()


# ── Image remove modal ────────────────────────────────────────────────────────

def _build_remove_image_modal(parent: "BroadcastView") -> discord.ui.Modal:
    count = len(parent.image_data)
    modal = discord.ui.Modal(title="Remove Image")
    inp = discord.ui.TextInput(
        label=f"File number to remove (1–{count})",
        placeholder=f"Enter a number between 1 and {count}",
        min_length=1,
        max_length=1,
        required=True,
    )
    modal.add_item(inp)

    async def on_submit(mi: discord.Interaction):
        try:
            idx = int(inp.value) - 1
        except ValueError:
            await mi.response.send_message("Please enter a valid number.", ephemeral=True)
            return
        if idx < 0 or idx >= len(parent.image_data):
            await mi.response.send_message(
                f"Invalid number. Choose between 1 and {len(parent.image_data)}.",
                ephemeral=True,
            )
            return
        parent.image_urls.pop(idx)
        parent.image_data.pop(idx)
        parent._rebuild()
        await mi.response.defer()
        await mi.edit_original_response(embed=parent._composer_embed(), view=parent)

    modal.on_submit = on_submit
    return modal


# ── Broadcast composer ────────────────────────────────────────────────────────

class BroadcastView(discord.ui.View):
    def __init__(self, bot: "BallsDexBot", invoker: discord.User):
        super().__init__(timeout=300)
        self.bot = bot
        self.invoker = invoker
        self.content: str = ""
        self.use_embed: bool = False
        self.embed_title: str = "Broadcast"
        self.embed_color: discord.Color = discord.Color.blue()
        self.embed_color_label: str = "blue"
        self.delivery: str = "spawn"
        self.image_urls: list[str] = []
        self.image_data: list[tuple[bytes, str]] = []
        self._awaiting_image: bool = False
        self._rebuild()

    def _rebuild(self):
        self.clear_items()

        send_btn = discord.ui.Button(
            label="Send",
            style=discord.ButtonStyle.success,
            emoji="📢",
            disabled=not self.content and not self.image_data,
            row=0,
        )
        send_btn.callback = self._confirm
        self.add_item(send_btn)

        edit_btn = discord.ui.Button(
            label="Edit Message",
            style=discord.ButtonStyle.primary,
            emoji="✏️",
            row=0,
        )
        edit_btn.callback = self._edit_message
        self.add_item(edit_btn)

        embed_btn = discord.ui.Button(
            label=f"Embed: {'On ✅' if self.use_embed else 'Off ❌'}",
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        embed_btn.callback = self._toggle_embed
        self.add_item(embed_btn)

        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            disabled=not self.content and not self.image_data,
            row=0,
        )
        clear_btn.callback = self._clear
        self.add_item(clear_btn)

        close_btn = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
            emoji="✖️",
            row=0,
        )
        close_btn.callback = self._close
        self.add_item(close_btn)

        sel = discord.ui.Select(
            placeholder=f"Delivery: {DELIVERY_LABELS[self.delivery]}",
            options=[
                discord.SelectOption(
                    label=v,
                    value=k,
                    emoji={"spawn": "📡", "dms": "📬", "both": "🌐"}[k],
                    default=(k == self.delivery),
                )
                for k, v in DELIVERY_LABELS.items()
            ],
            row=1,
        )
        sel.callback = self._set_delivery
        self.add_item(sel)

        if self.use_embed:
            title_btn = discord.ui.Button(
                label=f"Title: {self.embed_title[:18]}{'…' if len(self.embed_title) > 18 else ''}",
                style=discord.ButtonStyle.secondary,
                emoji="📝",
                row=2,
            )
            title_btn.callback = self._set_title
            self.add_item(title_btn)

            color_btn = discord.ui.Button(
                label=f"Color: {self.embed_color_label}",
                style=discord.ButtonStyle.secondary,
                emoji="🎨",
                row=2,
            )
            color_btn.callback = self._set_color
            self.add_item(color_btn)

        img_count = len(self.image_data)
        add_img_btn = discord.ui.Button(
            label=f"Add File ({img_count}/5)" if img_count else "Add Files",
            style=discord.ButtonStyle.secondary,
            emoji="🖼️",
            disabled=img_count >= 5 or self._awaiting_image,
            row=3,
        )
        add_img_btn.callback = self._add_image
        self.add_item(add_img_btn)

        if self.image_data:
            remove_img_btn = discord.ui.Button(
                label="Remove Image",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                row=3,
            )
            remove_img_btn.callback = self._remove_image
            self.add_item(remove_img_btn)

    def _composer_embed(self) -> discord.Embed:
        snippet = (
            f"```\n{self.content[:300]}{'…' if len(self.content) > 300 else ''}\n```"
            if self.content
            else "*No message set yet.*"
        )
        desc = (
            f"**Delivery:** {DELIVERY_LABELS[self.delivery]}\n"
            f"**Embed:** {'✅ On' if self.use_embed else '❌ Off'}\n"
        )
        if self.use_embed:
            desc += f"**Title:** {self.embed_title}\n**Color:** {self.embed_color_label}\n"
        if self.image_data:
            desc += f"**Files:** {len(self.image_data)}\n"
            for i, (_, filename) in enumerate(self.image_data, 1):
                desc += f"  {i}. {filename}\n"
        desc += f"\n**Message preview:**\n{snippet}"
        return discord.Embed(
            title="Broadcast Composer",
            description=desc,
            color=self.embed_color if self.use_embed else discord.Color.blurple(),
        )

    def _build_send_payload(self) -> dict:
        kwargs: dict = {}
        if self.use_embed:
            kwargs["embed"] = discord.Embed(
                title=self.embed_title,
                description=self.content or "",
                color=self.embed_color,
            )
        elif self.content:
            kwargs["content"] = self.content
        return kwargs

    def _make_files(self) -> list[discord.File]:
        import io as _io
        return [discord.File(_io.BytesIO(d), filename=n) for d, n in self.image_data]

    async def _refresh(self, interaction: discord.Interaction):
        kw = dict(embed=self._composer_embed(), view=self)
        if interaction.response.is_done():
            await interaction.edit_original_response(**kw)
        else:
            await interaction.response.edit_message(**kw)

    async def _set_delivery(self, interaction: discord.Interaction):
        self.delivery = interaction.data["values"][0]
        self._rebuild()
        await self._refresh(interaction)

    async def _toggle_embed(self, interaction: discord.Interaction):
        self.use_embed = not self.use_embed
        self._rebuild()
        await self._refresh(interaction)

    async def _edit_message(self, interaction: discord.Interaction):
        modal = discord.ui.Modal(title="Broadcast Message")
        inp = discord.ui.TextInput(
            label="Message content",
            style=discord.TextStyle.long,
            default=self.content or None,
            max_length=4000,
            required=True,
        )
        modal.add_item(inp)

        async def on_submit(mi: discord.Interaction):
            self.content = inp.value
            self._rebuild()
            await mi.response.defer()
            await self._refresh(mi)

        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    async def _set_title(self, interaction: discord.Interaction):
        modal = discord.ui.Modal(title="Set Embed Title")
        inp = discord.ui.TextInput(
            label="Title",
            default=self.embed_title,
            max_length=256,
            required=True,
        )
        modal.add_item(inp)

        async def on_submit(mi: discord.Interaction):
            self.embed_title = inp.value
            self._rebuild()
            await mi.response.defer()
            await self._refresh(mi)

        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    async def _set_color(self, interaction: discord.Interaction):
        modal = discord.ui.Modal(title="Set Embed Color")
        inp = discord.ui.TextInput(
            label="Color name or hex  (e.g. blue, #FF0000)",
            default=self.embed_color_label,
            max_length=7,
            required=True,
        )
        modal.add_item(inp)

        async def on_submit(mi: discord.Interaction):
            c = _parse_color(inp.value)
            if c is None:
                await mi.response.send_message(
                    "Invalid color. Use a name (red, blue, purple…) or hex (#FF0000).",
                    ephemeral=True,
                )
                return
            self.embed_color = c
            self.embed_color_label = inp.value.strip()
            self._rebuild()
            await mi.response.defer()
            await self._refresh(mi)

        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    async def _add_image(self, interaction: discord.Interaction):
        if len(self.image_urls) >= 5:
            await interaction.response.send_message(
                "Maximum of 5 files allowed.", ephemeral=True
            )
            return

        self._awaiting_image = True
        self._rebuild()
        await interaction.response.edit_message(embed=self._composer_embed(), view=self)
        prompt = await interaction.followup.send(
            "Please send your file now in this channel. "
            "It will be deleted immediately after capture. Send `cancel` to abort.",
            ephemeral=True,
            wait=True,
        )

        def check(m: discord.Message) -> bool:
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel_id  # type: ignore
                and (m.attachments or m.content.lower() == "cancel")
            )

        try:
            msg: discord.Message = await self.bot.wait_for(
                "message", check=check, timeout=60
            )
        except asyncio.TimeoutError:
            self._awaiting_image = False
            self._rebuild()
            try:
                await prompt.delete()
            except Exception:
                pass
            await interaction.edit_original_response(
                content="File upload timed out.", embed=self._composer_embed(), view=self
            )
            return

        try:
            await prompt.delete()
        except Exception:
            pass

        if msg.content.lower() == "cancel":
            try:
                await msg.delete()
            except Exception:
                pass
            self._awaiting_image = False
            self._rebuild()
            await interaction.edit_original_response(
                embed=self._composer_embed(), view=self
            )
            return

        import aiohttp
        import io as _io
        async with aiohttp.ClientSession() as session:
            for attachment in msg.attachments:
                if len(self.image_data) >= 5:
                    break
                try:
                    async with session.get(attachment.url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            self.image_data.append((data, attachment.filename))
                            self.image_urls.append(attachment.filename)
                except Exception:
                    pass

        try:
            await msg.delete()
        except Exception:
            pass

        self._awaiting_image = False
        self._rebuild()
        await interaction.edit_original_response(
            embed=self._composer_embed(), view=self
        )

    async def _remove_image(self, interaction: discord.Interaction):
        if not self.image_data:
            await interaction.response.send_message("No images to remove.", ephemeral=True)
            return
        await interaction.response.send_modal(_build_remove_image_modal(self))

    async def _clear(self, interaction: discord.Interaction):
        cv = ConfirmView()
        await interaction.response.send_message(
            "Clear the message content and all files?", view=cv, ephemeral=True
        )
        await cv.wait()
        if cv.confirmed:
            self.content = ""
            self.image_urls = []
            self.image_data = []
            self._rebuild()
        await interaction.edit_original_response(
            content="Cleared." if cv.confirmed else "Cancelled.", view=None
        )
        if cv.confirmed:
            await self._refresh(interaction)

    async def _close(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="Broadcast Composer Closed.", embed=None, view=None
        )
        self.stop()

    async def _confirm(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="-# This is a preview of the message. Send now?",
            embed=self._build_preview_embed(),
            attachments=[],
            view=ConfirmSendView(self, interaction),
        )

    def _build_preview_embed(self) -> discord.Embed:
        if self.use_embed:
            e = discord.Embed(
                title=self.embed_title,
                description=self.content or "",
                color=self.embed_color,
            )
            if self.image_data:
                e.set_footer(text=f"+ {len(self.image_data)} image(s) attached")
            return e
        e = discord.Embed(
            description=self.content or "*[no text]*",
            color=discord.Color.dark_grey(),
        )
        if self.image_data:
            e.set_footer(text=f"+ {len(self.image_data)} image(s) attached")
        return e

    async def execute_send(
        self,
        interaction: discord.Interaction,
        original_interaction: discord.Interaction,
    ):
        # ── Collect targets using Django ORM ──────────────────────────────────
        spawn_channel_ids: list[int] = []
        player_discord_ids: list[int] = []

        if self.delivery in ("spawn", "both"):
            spawn_channel_ids = [
                x async for x in
                GuildConfig.objects.filter(
                    spawn_channel__isnull=False, enabled=True
                ).values_list("spawn_channel", flat=True).aiterator()
            ]

        if self.delivery in ("dms", "both"):
            player_discord_ids = [
                x async for x in
                Player.objects.values_list("discord_id", flat=True).aiterator()
            ]

        total = len(spawn_channel_ids) + len(player_discord_ids)
        if total == 0:
            await original_interaction.edit_original_response(
                content="No targets found. Make sure servers have spawn channels configured.",
                embed=None,
                view=None,
            )
            return

        sent_ch = failed_ch = sent_dm = failed_dm = 0
        done = 0
        last_edit = 0.0

        def _progress_embed(stage: str) -> discord.Embed:
            lines = [f"**{stage}**\n{_bar(done, total)}\n"]
            if self.delivery in ("spawn", "both"):
                lines.append(
                    f"Channels — ✅ {sent_ch}  ❌ {failed_ch} / {len(spawn_channel_ids)} total"
                )
            if self.delivery in ("dms", "both"):
                lines.append(
                    f"DMs      — ✅ {sent_dm}  ❌ {failed_dm} / {len(player_discord_ids)} total"
                )
            return discord.Embed(
                title="Broadcasting…",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            )

        async def _maybe_update(stage: str):
            nonlocal last_edit
            now = asyncio.get_event_loop().time()
            if now - last_edit >= 1.5:
                last_edit = now
                try:
                    await original_interaction.edit_original_response(
                        content=None, embed=_progress_embed(stage), view=None
                    )
                except Exception:
                    pass

        await original_interaction.edit_original_response(
            content=None, embed=_progress_embed("Starting…"), view=None
        )

        for channel_id in spawn_channel_ids:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                failed_ch += 1
                done += 1
                await _maybe_update("Sending to channels…")
                continue
            try:
                payload = self._build_send_payload()
                if self.image_data:
                    payload["files"] = self._make_files()
                await channel.send(**payload)
                sent_ch += 1
            except Exception:
                failed_ch += 1
            done += 1
            await _maybe_update("Sending to channels…")

        for discord_id in player_discord_ids:
            user = self.bot.get_user(discord_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(discord_id)
                except Exception:
                    failed_dm += 1
                    done += 1
                    await _maybe_update("Sending DMs…")
                    continue
            try:
                payload = self._build_send_payload()
                if self.image_data:
                    payload["files"] = self._make_files()
                await user.send(**payload)
                sent_dm += 1
            except Exception:
                failed_dm += 1
            done += 1
            await _maybe_update("Sending DMs…")

        lines = ["**Broadcast complete!**"]
        if self.delivery in ("spawn", "both"):
            lines.append(f"Channels — ✅ {sent_ch} sent  ❌ {failed_ch} failed")
        if self.delivery in ("dms", "both"):
            lines.append(f"DMs      — ✅ {sent_dm} sent  ❌ {failed_dm} failed")

        await original_interaction.edit_original_response(
            content=None,
            embed=discord.Embed(
                title="Broadcast Complete",
                description="\n".join(lines) + f"\n\n{_bar(total, total)}",
                color=discord.Color.green(),
            ),
            view=None,
        )
        log.info(
            f"{interaction.user} sent a broadcast | "
            f"Delivery: {self.delivery} | "
            f"Embed: {self.use_embed} | "
            f"Files: {len(self.image_data)} | "
            f"Message: {self.content[:200]!r}",
            extra={"webhook": True},
        )
        self.stop()


# ── Confirm send view ─────────────────────────────────────────────────────────

class ConfirmSendView(discord.ui.View):
    def __init__(self, parent: BroadcastView, original_interaction: discord.Interaction):
        super().__init__(timeout=120)
        self.parent = parent
        self.original_interaction = original_interaction

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, emoji="📢", row=0)
    async def send_confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()
        await self.parent.execute_send(interaction, self.original_interaction)
        self.stop()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=0)
    async def go_back(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.parent._rebuild()
        await interaction.response.edit_message(
            content=None,
            embed=self.parent._composer_embed(),
            view=self.parent,
        )
        self.stop()


# ── Cog ───────────────────────────────────────────────────────────────────────

class BroadcastCog(commands.Cog):
    """Broadcast package — admin mass-message tools."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot


# ── /admin broadcast command ──────────────────────────────────────────────────

@commands.hybrid_command(name="broadcast", description="Open the broadcast composer")
@checks.is_staff()
async def broadcast(ctx: commands.Context["BallsDexBot"]):
    """Open the broadcast composer."""
    bot = ctx.bot
    invoker = ctx.author
    view = BroadcastView(bot, invoker)  # type: ignore
    if ctx.interaction:
        await ctx.interaction.response.send_message(
            embed=view._composer_embed(), view=view, ephemeral=True
        )
    else:
        await ctx.send(embed=view._composer_embed(), view=view)
