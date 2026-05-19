"""
Broadcast package for BallsDex.

Commands:
  /admin broadcast send        — open the broadcast composer (ephemeral)
  /admin broadcast add_channel — add a spawn channel to the broadcast list
  /admin broadcast rm_channel  — remove a spawn channel from the broadcast list
  /admin broadcast channels    — list all configured channels in this server
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

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


# ── Broadcast composer ────────────────────────────────────────────────────────

class BroadcastView(discord.ui.View):
    def __init__(self, cog: "BroadcastCog", invoker: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.invoker = invoker
        self.content: str = ""
        self.use_embed: bool = False
        self.embed_title: str = "Broadcast"
        self.embed_color: discord.Color = discord.Color.blue()
        self.embed_color_label: str = "blue"
        self.delivery: str = "spawn"
        self._rebuild()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _rebuild(self):
        self.clear_items()

        send_btn = discord.ui.Button(
            label="Send",
            style=discord.ButtonStyle.success,
            emoji="📢",
            disabled=not self.content,
            row=0,
        )
        send_btn.callback = self._send
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
            disabled=not self.content,
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

        # Delivery select — row 1
        sel = discord.ui.Select(
            placeholder=f"Delivery: {DELIVERY_LABELS[self.delivery]}",
            options=[
                discord.SelectOption(
                    label=v, value=k,
                    emoji={"spawn": "📡", "dms": "📬", "both": "🌐"}[k],
                    default=(k == self.delivery),
                )
                for k, v in DELIVERY_LABELS.items()
            ],
            row=1,
        )
        sel.callback = self._set_delivery
        self.add_item(sel)

        # Embed options — row 2 (only when embed is on)
        if self.use_embed:
            title_btn = discord.ui.Button(
                label=f"Title: {self.embed_title[:20]}{'…' if len(self.embed_title) > 20 else ''}",
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

    def _status_embed(self) -> discord.Embed:
        snippet = (
            f"```\n{self.content[:300]}{'…' if len(self.content) > 300 else ''}\n```"
            if self.content else "*No message set yet.*"
        )
        desc = (
            f"**Delivery:** {DELIVERY_LABELS[self.delivery]}\n"
            f"**Embed:** {'✅ On' if self.use_embed else '❌ Off'}\n"
        )
        if self.use_embed:
            desc += f"**Title:** {self.embed_title}\n**Color:** {self.embed_color_label}\n"
        desc += f"\n**Message preview:**\n{snippet}"

        embed = discord.Embed(
            title="Broadcast Composer",
            description=desc,
            color=self.embed_color if self.use_embed else discord.Color.blurple(),
        )
        return embed

    def _build_send_payload(self) -> dict:
        if self.use_embed:
            return {"embed": discord.Embed(
                title=self.embed_title,
                description=self.content,
                color=self.embed_color,
            )}
        return {"content": self.content}

    async def _refresh(self, interaction: discord.Interaction):
        kw = dict(embed=self._status_embed(), view=self)
        if interaction.response.is_done():
            await interaction.edit_original_response(**kw)
        else:
            await interaction.response.edit_message(**kw)

    # ── callbacks ─────────────────────────────────────────────────────────────

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

    async def _clear(self, interaction: discord.Interaction):
        cv = ConfirmView()
        await interaction.response.send_message(
            "Clear the message content?", view=cv, ephemeral=True
        )
        await cv.wait()
        if cv.confirmed:
            self.content = ""
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

    async def _send(self, interaction: discord.Interaction):
        if not self.content:
            await interaction.response.send_message("No message content set.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        payload = self._build_send_payload()

        sent_ch = failed_ch = sent_dm = failed_dm = 0

        if self.delivery in ("spawn", "both"):
            for ch_id in self.cog.get_all_spawn_channels():
                ch = self.cog.bot.get_channel(ch_id)
                if not isinstance(ch, discord.TextChannel):
                    failed_ch += 1
                    continue
                try:
                    await ch.send(**payload)
                    sent_ch += 1
                except Exception:
                    failed_ch += 1

        if self.delivery in ("dms", "both"):
            for user_id in self.cog.player_ids:
                user = self.cog.bot.get_user(user_id)
                if user is None:
                    try:
                        user = await self.cog.bot.fetch_user(user_id)
                    except Exception:
                        failed_dm += 1
                        continue
                try:
                    await user.send(**payload)
                    sent_dm += 1
                except Exception:
                    failed_dm += 1

        lines = ["**Broadcast complete!**"]
        if self.delivery in ("spawn", "both"):
            lines.append(f"📡 Channels — ✅ {sent_ch} sent  ❌ {failed_ch} failed")
        if self.delivery in ("dms", "both"):
            lines.append(f"📬 DMs      — ✅ {sent_dm} sent  ❌ {failed_dm} failed")

        result = "\n".join(lines)
        await interaction.followup.send(result, ephemeral=True)
        await log_action(
            f"{interaction.user.name} sent a broadcast | "
            f"Delivery: {self.delivery} | "
            f"Embed: {self.use_embed} | "
            f"Message: {self.content[:200]!r}",
            self.cog.bot,
        )


# ── Cog ───────────────────────────────────────────────────────────────────────

class BroadcastCog(commands.Cog):
    """Broadcast package — admin mass-message tools."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.spawn_channels: dict[int, list[int]] = {}  # guild_id -> [channel_ids]
        self.player_ids: list[int] = []                 # populate from your player DB

    def get_all_spawn_channels(self) -> list[int]:
        out: list[int] = []
        for ids in self.spawn_channels.values():
            out.extend(ids)
        return out


# ── Slash command group ───────────────────────────────────────────────────────

def BroadcastAdminCommand(bot: "BallsDexBot") -> app_commands.Group:
    group = app_commands.Group(name="broadcast", description="Broadcast messages to channels or players")
    group._is_broadcast = True  # type: ignore

    @group.command(name="send", description="Open the broadcast composer")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def broadcast_send(interaction: discord.Interaction):
        cog: BroadcastCog = bot.get_cog("BroadcastCog")  # type: ignore
        view = BroadcastView(cog, interaction.user)
        await interaction.response.send_message(
            embed=view._status_embed(), view=view, ephemeral=True
        )

    @group.command(name="add_channel", description="Add a channel to the spawn broadcast list")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.describe(channel="Channel to add")
    async def broadcast_add(interaction: discord.Interaction, channel: discord.TextChannel):
        cog: BroadcastCog = bot.get_cog("BroadcastCog")  # type: ignore
        cog.spawn_channels.setdefault(interaction.guild_id, [])
        if channel.id not in cog.spawn_channels[interaction.guild_id]:
            cog.spawn_channels[interaction.guild_id].append(channel.id)
        await interaction.response.send_message(
            f"Added {channel.mention} to the broadcast list.", ephemeral=True
        )

    @group.command(name="rm_channel", description="Remove a channel from the spawn broadcast list")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.describe(channel="Channel to remove")
    async def broadcast_remove(interaction: discord.Interaction, channel: discord.TextChannel):
        cog: BroadcastCog = bot.get_cog("BroadcastCog")  # type: ignore
        lst = cog.spawn_channels.get(interaction.guild_id, [])
        if channel.id in lst:
            lst.remove(channel.id)
            await interaction.response.send_message(
                f"Removed {channel.mention} from the broadcast list.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{channel.mention} is not in the broadcast list.", ephemeral=True
            )

    @group.command(name="channels", description="List configured broadcast channels in this server")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def broadcast_list(interaction: discord.Interaction):
        cog: BroadcastCog = bot.get_cog("BroadcastCog")  # type: ignore
        ids = cog.spawn_channels.get(interaction.guild_id, [])
        if not ids:
            await interaction.response.send_message(
                "No broadcast channels configured in this server.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title="Broadcast Channels",
            description="\n".join(f"<#{i}>" for i in ids),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    return group
