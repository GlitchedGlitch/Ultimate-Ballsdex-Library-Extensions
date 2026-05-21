"""
Broadcast package for BallsDex.

Commands:
  /admin broadcast send — open the broadcast composer (ephemeral)

Spawn channels are pulled automatically from GuildConfig (every guild that has
a spawn channel configured). Player DMs are sent to every Player row in the
database. No manual channel list is needed.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import GuildConfig, Player
from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings

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
        label=f"Image number to remove (1–{count})",
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
        self.image_urls: list[str] = []           # for display only
        self.image_data: list[tuple[bytes, str]] = []  # (raw_bytes, filename)
        self._awaiting_image: bool = False
        self._rebuild()

    # ── UI builder ────────────────────────────────────────────────────────────

    def _rebuild(self):
        self.clear_items()

        # Row 0 — primary actions
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

        # Row 1 — delivery select
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

        # Row 2 — embed options (only when embed on)
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

        # Row 3 — image controls
        img_count = len(self.image_data)

        add_img_btn = discord.ui.Button(
            label=f"Add Image ({img_count}/5)" if img_count else "Add Image",
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
            desc += f"**Images:** {len(self.image_data)}\n"
            for i, (_, filename) in enumerate(self.image_data, 1):
                desc += f"  {i}. {filename}\n"
        desc += f"\n**Message preview:**\n{snippet}"

        return discord.Embed(
            title="📡 Broadcast Composer",
            description=desc,
            color=self.embed_color if self.use_embed else discord.Color.blurple(),
        )

    def _build_send_payload(self) -> dict:
        """Build the payload dict for sending to a channel."""
        files_note = ""  # attachments are re-uploaded from URLs per-destination
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

    async def _fetch_image_files(self) -> list[discord.File]:
        """Download stored image URLs and return as discord.File objects."""
        import aiohttp
        files = []
        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(self.image_urls):
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            # Guess extension from URL
                            ext = url.split("?")[0].rsplit(".", 1)[-1] or "png"
                            files.append(discord.File(
                                fp=__import__("io").BytesIO(data),
                                filename=f"broadcast_{i + 1}.{ext}",
                            ))
                except Exception:
                    pass
        return files

    async def _refresh(self, interaction: discord.Interaction):
        kw = dict(embed=self._composer_embed(), view=self)
        if interaction.response.is_done():
            await interaction.edit_original_response(**kw)
        else:
            await interaction.response.edit_message(**kw)

    # ── Composer callbacks ────────────────────────────────────────────────────

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
        """Ask the user to send an image in the channel, then capture and delete it."""
        if len(self.image_urls) >= 5:
            await interaction.response.send_message(
                "Maximum of 5 images allowed.", ephemeral=True
            )
            return

        self._awaiting_image = True
        self._rebuild()

        # Acknowledge the button interaction first, then send ephemeral prompt via followup
        await interaction.response.edit_message(embed=self._composer_embed(), view=self)
        prompt = await interaction.followup.send(
            "📎 Please send your image now in this channel. "
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
            msg: discord.Message = await self.bot.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            self._awaiting_image = False
            self._rebuild()
            try:
                await prompt.delete()
            except Exception:
                pass
            await interaction.edit_original_response(
                content="Image upload timed out.", embed=self._composer_embed(), view=self
            )
            return

        # Clean up the prompt and the user's message
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

        # Save the attachment URL (Discord CDN URL — stable enough for reuse during session)
        # Download bytes immediately while the CDN URL is still accessible
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
                            ext = attachment.filename.rsplit(".", 1)[-1] or "png"
                            filename = f"broadcast_{len(self.image_data) + 1}.{ext}"
                            self.image_data.append((data, filename))
                            self.image_urls.append(attachment.filename)  # display label only
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
            "Clear the message content and all images?", view=cv, ephemeral=True
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
        cv = ConfirmView()
        await interaction.response.send_message(
            "Close the broadcast composer?", view=cv, ephemeral=True
        )
        await cv.wait()
        if cv.confirmed:
            await interaction.edit_original_response(content="Composer closed.", view=None)
            await interaction.delete_original_response()
            self.stop()
        else:
            await interaction.edit_original_response(content="Cancelled.", view=None)

    # ── Confirmation step (same message) ──────────────────────────────────────

    async def _confirm(self, interaction: discord.Interaction):
        """Replace composer with preview + confirmation on the same message."""
        await interaction.response.edit_message(
            content=(
                "-# This is a preview of the message. Send now?"
            ),
            embed=self._build_preview_embed(),
            attachments=[],   # clear any old attachments shown
            view=ConfirmSendView(self, interaction),
        )

    def _build_preview_embed(self) -> Optional[discord.Embed]:
        """Return the exact embed the broadcast will send, or a preview container for plain text."""
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

    # ── Actual send ───────────────────────────────────────────────────────────

    async def execute_send(
        self,
        interaction: discord.Interaction,
        original_interaction: discord.Interaction,
    ):
        """
        Called by ConfirmSendView after user confirms.
        Shows live progress bar on the same message, then shows results.
        """
        # ── Count targets first ───────────────────────────────────────────────
        spawn_channel_ids: list[int] = []
        player_discord_ids: list[int] = []

        if self.delivery in ("spawn", "both"):
            spawn_channel_ids = list(
                await GuildConfig.filter(
                    spawn_channel__isnull=False, enabled=True
                ).values_list("spawn_channel", flat=True)
            )

        if self.delivery in ("dms", "both"):
            player_discord_ids = list(
                await Player.all().values_list("discord_id", flat=True)
            )

        total = len(spawn_channel_ids) + len(player_discord_ids)

        if total == 0:
            await original_interaction.edit_original_response(
                content="❌ No targets found. Make sure servers have spawn channels configured.",
                embed=None,
                view=None,
            )
            return

        # Images were already downloaded at capture time — use stored bytes directly
        image_data = self.image_data

        def make_files() -> list[discord.File]:
            import io as _io
            return [discord.File(_io.BytesIO(d), filename=n) for d, n in image_data]

        # ── Progress embed helper ─────────────────────────────────────────────
        sent_ch = failed_ch = sent_dm = failed_dm = 0
        done = 0
        last_edit = 0.0

        def _progress_embed(stage: str) -> discord.Embed:
            lines = [f"**{stage}**\n{_bar(done, total)}\n"]
            if self.delivery in ("spawn", "both"):
                lines.append(f"Channels — ✅ {sent_ch}  ❌ {failed_ch} / {len(spawn_channel_ids)} total")
            if self.delivery in ("dms", "both"):
                lines.append(f"DMs      — ✅ {sent_dm}  ❌ {failed_dm} / {len(player_discord_ids)} total")
            return discord.Embed(
                title="Broadcasting…",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            )

        async def _maybe_update(stage: str):
            nonlocal last_edit
            now = asyncio.get_event_loop().time()
            if now - last_edit >= 1.5:  # throttle edits to avoid rate limits
                last_edit = now
                try:
                    await original_interaction.edit_original_response(
                        content=None, embed=_progress_embed(stage), view=None
                    )
                except Exception:
                    pass

        # Initial progress display
        await original_interaction.edit_original_response(
            content=None, embed=_progress_embed("Starting…"), view=None
        )

        # ── Send to spawn channels ────────────────────────────────────────────
        for channel_id in spawn_channel_ids:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                failed_ch += 1
                done += 1
                await _maybe_update("Sending to channels…")
                continue
            try:
                payload = self._build_send_payload()
                if image_data:
                    payload["files"] = make_files()
                await channel.send(**payload)
                sent_ch += 1
            except Exception:
                failed_ch += 1
            done += 1
            await _maybe_update("Sending to channels…")

        # ── Send to player DMs ────────────────────────────────────────────────
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
                if image_data:
                    payload["files"] = make_files()
                await user.send(**payload)
                sent_dm += 1
            except Exception:
                failed_dm += 1
            done += 1
            await _maybe_update("Sending DMs…")

        # ── Final result ──────────────────────────────────────────────────────
        lines = ["**Broadcast complete!**"]
        if self.delivery in ("spawn", "both"):
            lines.append(f"Channels — ✅ {sent_ch} sent  ❌ {failed_ch} failed")
        if self.delivery in ("dms", "both"):
            lines.append(f"DMs      — ✅ {sent_dm} sent  ❌ {failed_dm} failed")

        result_embed = discord.Embed(
            title="📡 Broadcast Complete",
            description="\n".join(lines) + f"\n\n{_bar(total, total)}",
            color=discord.Color.green(),
        )

        await original_interaction.edit_original_response(
            content=None, embed=result_embed, view=None
        )

        await log_action(
            f"{interaction.user.name} sent a broadcast | "
            f"Delivery: {self.delivery} | "
            f"Embed: {self.use_embed} | "
            f"Images: {len(self.image_urls)} | "
            f"Message: {self.content[:200]!r}",
            self.bot,
        )
        self.stop()


# ── Confirmation view (shown on same message as composer) ─────────────────────

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


# ── Slash command group ───────────────────────────────────────────────────────

def BroadcastAdminCommand(bot: "BallsDexBot") -> app_commands.Group:
    group = app_commands.Group(
        name="broadcast",
        description="Broadcast messages to all spawn channels or all players",
    )
    group._is_broadcast = True  # type: ignore

    @group.command(name="send", description="Open the broadcast composer")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def broadcast_send(interaction: discord.Interaction):
        view = BroadcastView(bot, interaction.user)
        await interaction.response.send_message(
            embed=view._composer_embed(), view=view, ephemeral=True
        )

    return group
