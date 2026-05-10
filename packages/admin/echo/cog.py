"""
Echo package for BallsDex (v2.30 compatible).

Commands:
  /admin <name> — send, edit, delete or reply to messages as the bot (admin only)

Channel parameter accepts a channel ID or mention string so cross-server
channels work. Discord's native TextChannel type only resolves within the
current guild, so we handle resolution manually via bot.get_channel().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.echo")


def _parse_message_link(link: str) -> tuple[int, int] | None:
    try:
        parts = link.strip().rstrip("/").split("/")
        return int(parts[-2]), int(parts[-1])
    except (ValueError, IndexError):
        return None


def _parse_channel(bot: "BallsDexBot", value: str) -> discord.TextChannel | None:
    """
    Resolve a channel from a string. Accepts:
      - Raw channel ID:  123456789012345678
      - Channel mention: <#123456789012345678>
    Works across servers as long as the bot can see the channel.
    """
    raw = value.strip().lstrip("<#").rstrip(">")
    try:
        channel_id = int(raw)
    except ValueError:
        return None
    channel = bot.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


async def _fetch_message(
    bot: "BallsDexBot", link: str
) -> tuple[discord.Message | None, str | None]:
    parsed = _parse_message_link(link)
    if not parsed:
        return None, "Invalid message link. Copy it via **Copy Message Link** in Discord."
    channel_id, message_id = parsed
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None, (
            "Could not find the channel from the message link. "
            "Make sure the bot has access to it."
        )
    try:
        msg = await channel.fetch_message(message_id)
        return msg, None
    except discord.NotFound:
        return None, "Could not find the message. Make sure the link is correct."


class EchoCog(commands.Cog):
    """Echo package — admin message tools."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot


def EchoAdminCommand(bot: "BallsDexBot", name: str = "echo") -> app_commands.Command:
    @app_commands.command(
        name=name,
        description="Send, edit, delete or reply to messages as the bot",
    )
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.describe(
        message="The text content to send or use when editing",
        image="An image to attach",
        embed="Wrap the message text in an embed",
        channel="Channel ID or <#mention> to send to — works cross-server (default: current channel)",
        edit_message="Message link to edit instead of sending a new message",
        reply="Message link to reply to when sending",
        delete_message="Message link of the bot message to delete",
    )
    async def echo(
        interaction: discord.Interaction,
        message: str | None = None,
        image: discord.Attachment | None = None,
        embed: bool = False,
        channel: str | None = None,
        edit_message: str | None = None,
        reply: str | None = None,
        delete_message: str | None = None,
    ):
        if not message and not image and not edit_message and not delete_message:
            await interaction.response.send_message(
                "You must provide at least a `message`, an `image`, "
                "an `edit_message` link, or a `delete_message` link.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # ── Delete mode ───────────────────────────────────────────────────────
        if delete_message:
            del_msg, err = await _fetch_message(bot, delete_message)
            if err:
                await interaction.followup.send(err, ephemeral=True)
                return

            if del_msg.author.id != bot.user.id:  # type: ignore
                await interaction.followup.send(
                    "I can only delete my own messages.", ephemeral=True
                )
                return

            try:
                jump_url = del_msg.jump_url
                channel_info = f"#{del_msg.channel}"  # type: ignore
                preview = (del_msg.content or "[no text content]")[:100]
                await del_msg.delete()
                await interaction.followup.send("Message deleted!", ephemeral=True)
                await log_action(
                    f"{interaction.user.name} deleted a message in "
                    f"{channel_info} {jump_url} | "
                    f"Message: {preview!r}",
                    bot,
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "Missing permissions to delete that message.", ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(f"Error:\n```py\n{e}\n```", ephemeral=True)
            return

        # ── Resolve channel ───────────────────────────────────────────────────
        if channel is not None:
            target = _parse_channel(bot, channel)
            if target is None:
                await interaction.followup.send(
                    "Could not find that channel. Make sure you're using a valid channel ID "
                    "or `<#mention>` and that the bot has access to it.",
                    ephemeral=True,
                )
                return
        else:
            target: discord.TextChannel = interaction.channel  # type: ignore

        # ── Edit mode ─────────────────────────────────────────────────────────
        if edit_message:
            if not message:
                await interaction.followup.send(
                    "You must provide `message` with the new content when editing.",
                    ephemeral=True,
                )
                return

            edit_msg, err = await _fetch_message(bot, edit_message)
            if err:
                await interaction.followup.send(err, ephemeral=True)
                return

            if edit_msg.author.id != bot.user.id:  # type: ignore
                await interaction.followup.send(
                    "I can only edit my own messages.", ephemeral=True
                )
                return

            try:
                if embed:
                    await edit_msg.edit(
                        content=None,
                        embed=discord.Embed(description=message),
                    )
                else:
                    await edit_msg.edit(content=message, embed=None)

                await interaction.followup.send("Message edited!", ephemeral=True)
                parts = [
                    f"{interaction.user.name} edited a message in "
                    f"#{edit_msg.channel} {edit_msg.jump_url}",  # type: ignore
                    f"Message: {message!r}",
                ]
                if embed:
                    parts.append("Embed: True")
                prev = (edit_msg.content or "[no text content]")[:200]
                parts.append(f"Previous message: {prev!r}")
                await log_action(" | ".join(parts), bot)
            except discord.Forbidden:
                await interaction.followup.send(
                    "Missing permissions to edit that message.", ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(f"Error:\n```py\n{e}\n```", ephemeral=True)
            return

        # ── Send mode ─────────────────────────────────────────────────────────
        reply_msg: discord.Message | None = None
        if reply:
            reply_msg, err = await _fetch_message(bot, reply)
            if err:
                await interaction.followup.send(err, ephemeral=True)
                return

        kwargs: dict = {}
        if embed:
            kwargs["embed"] = discord.Embed(description=message or "")
        elif message:
            kwargs["content"] = message

        if image:
            kwargs["files"] = [await image.to_file()]

        if reply_msg:
            kwargs["reference"] = reply_msg
            kwargs["mention_author"] = False

        try:
            sent_msg = await target.send(**kwargs)
            await interaction.followup.send("Message sent!", ephemeral=True)

            parts = [
                    f"{interaction.user.name} sent a message in "
                    f"#{target} {sent_msg.jump_url}",
                    f"Message: {message!r}" if message else "Message: [image only]",
                ]
                if image:
                    parts.append(f"Image: {image.filename} {image.url}")
                if embed:
                    parts.append("Embed: True")
                if reply_msg:
                    parts.append(f"Replied to: {reply_msg.jump_url}")
                await log_action(" | ".join(parts), bot)

        except discord.Forbidden:
            await interaction.followup.send(
                f"Missing permissions to send in {target.mention}.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Error:\n```py\n{e}\n```", ephemeral=True)

    echo._is_echo = True  # type: ignore
    return echo
