"""
Leave Server Package v3
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils import checks

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.leave")


class LeaveCog(commands.Cog):
    """Leave Server package — admin tools."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot


def LeaveCommand(bot: "BallsDexBot") -> app_commands.Command:
    @app_commands.command(
        name="leave_server",
        description="Make the bot leave a server by its ID",
    )
    @checks.is_staff()
    @app_commands.describe(server="The ID of the server you want the bot to leave")
    async def leave_server(
        interaction: discord.Interaction,
        server: str,
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = int(server.strip())
        except ValueError:
            await interaction.followup.send(
                "Server not found. Make sure you put the correct ID.",
                ephemeral=True,
            )
            return

        guild = bot.get_guild(guild_id)
        if guild is None:
            await interaction.followup.send(
                "Server not found. Make sure you put the correct ID.",
                ephemeral=True,
            )
            return

        guild_name = guild.name
        await guild.leave()

        log.info(
            f"{interaction.user} ({interaction.user.id}) made the bot leave "
            f"{guild_name} ({guild_id})",
            extra={"webhook": True},
        )
        await interaction.followup.send(
            f"Left the server: **{guild_name}** (`{guild_id}`)",
            ephemeral=True,
        )

    leave_server._is_leave_server = True  # type: ignore
    return leave_server
 
