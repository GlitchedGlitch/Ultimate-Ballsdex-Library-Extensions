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

log = logging.getLogger("ballsdex.packages.leaveserver")


class LeaveServerCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot


def LeaveServerCommand(bot: "BallsDexBot") -> app_commands.Command:
    @app_commands.command(
        name="leave_server",
        description="Make the bot leave a server by its ID",
    )
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
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
                "Server not found. Make sure you put the correct id.",
                ephemeral=True,
            )
            return

        guild = bot.get_guild(guild_id)
        if guild is None:
            await interaction.followup.send(
                "Server not found. Make sure you put the correct id.",
                ephemeral=True,
            )
            return

        guild_name = guild.name
        await guild.leave()

        log.info(
            "Admin %s (%d) made the bot leave guild %s (%d)",
            interaction.user, interaction.user.id, guild_name, guild_id,
        )
        await log_action(
            f"{interaction.user.name} used leave_server — "
            f"left {guild_name} ({guild_id})",
            interaction.client,
        )

        await interaction.followup.send(
            f"Left the server **{guild_name}** (`{guild_id}`)",
            ephemeral=True,
        )

    leave_server._is_leave_server = True  # type: ignore
    return leave_server
