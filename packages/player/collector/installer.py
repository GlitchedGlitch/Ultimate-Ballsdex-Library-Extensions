import base64, io, json, os, requests, traceback, discord
from discord.ui import View, Button

REPO = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BASE = "https://api.github.com/repos/REPO/contents/packages/player/collector/{}?ref=v2-main".format("{}")
PKG = "/code/ballsdex/packages/collector"
CONFIG = "/code/config.yml"
REQUIREMENTS_FILE = os.path.join(PKG, "requirements.txt")
PACKAGE_ENTRY = "  - ballsdex.packages.collector"
FILES = ("__init__.py", "cog.py")
FOOTER = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"

BAR_FILLED = "█"
BAR_EMPTY  = "░"
BAR_LEN    = 10


def _bar(current: int, total: int) -> str:
    filled = round(BAR_LEN * current / total)
    pct = round(100 * current / total)
    return f"`{BAR_FILLED * filled}{BAR_EMPTY * (BAR_LEN - filled)}` {pct}%"


def _progress_embed(title: str, steps: list, color: discord.Color) -> discord.Embed:
    done_count = sum(1 for _, s in steps if s is True)
    total = len(steps)
    lines = []
    for label, state in steps:
        icon = {None: "⬜", True: "✅", False: "❌"}[state]
        lines.append(f"{icon} {label}")
    embed = discord.Embed(
        title=title,
        description="\n".join(lines) + f"\n\n{_bar(done_count, total)}",
        color=color,
    )
    embed.set_footer(text=FOOTER)
    return embed


def is_installed():
    return os.path.isdir(PKG) and os.path.isfile(os.path.join(PKG, "cog.py"))


def download_files():
    for f in FILES:
        resp = requests.get(BASE.format(f))
        resp.raise_for_status()
        content = base64.b64decode(resp.json()["content"]).decode()
        with open(os.path.join(PKG, f), "w") as fh:
            fh.write(content)


def ensure_requirements_file():
    if not os.path.isfile(REQUIREMENTS_FILE):
        with open(REQUIREMENTS_FILE, "w") as f:
            f.write("{}")


def add_to_config():
    with open(CONFIG, "r") as f:
        lines = f.readlines()
    if any(PACKAGE_ENTRY.strip() in l for l in lines):
        return
    for i, line in enumerate(lines):
        if "ballsdex.packages.trade" in line:
            lines.insert(i + 1, PACKAGE_ENTRY + "\n")
            break
    with open(CONFIG, "w") as f:
        f.writelines(lines)


def remove_from_config():
    with open(CONFIG, "r") as f:
        lines = f.readlines()
    lines = [l for l in lines if "ballsdex.packages.collector" not in l]
    with open(CONFIG, "w") as f:
        f.writelines(lines)


def delete_files():
    import shutil
    if os.path.isdir(PKG):
        shutil.rmtree(PKG)


def build_main_embed(installed: bool, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(
        title="Collector Package",
        description=(
            "Adds a collector system to your BallsDex instance.\n\n"
            "**Commands**\n"
            "• `/collector claim` — claim a collector ball\n"
            "• `/collector list` — view all active requirements\n"
            "• `/admin collector set` — set a requirement and reward\n"
            "• `/admin collector delete` — remove a requirement\n"
            "• `/admin collector bulk` — bulk add requirement\n"
            "• `/admin collector view` — inspect a requirement\n\n"
            "**How it works**\n"
            "Admins configure a minimum ball count and a special reward. "
            "Players who own enough copies of that ball can claim a collector "
            "version with the chosen special applied.\n\n"
            f"**Status:** {'✅ Installed' if installed else '❌ Not installed'}"
        ),
        color=color,
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_confirm_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Delete Collector Package",
        description=(
            "⚠️ **Are you sure you want to delete the Collector package?**\n\n"
            "This will:\n"
            "• Unload the package from the bot\n"
            "• Delete all package files\n"
            "• Remove it from `config.yml`\n"
            "• Wipe all active collector requirements\n\n"
            "This action **cannot be undone** without reinstalling."
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_error_embed(action: str, error: str) -> discord.Embed:
    short = error[:1000] + "..." if len(error) > 1000 else error
    embed = discord.Embed(
        title="An error occurred",
        description=(
            f"An error occurred when **{action}** the package!\n\n"
            f"```\n{short}\n```\n\n"
            "The full error is attached as a `.txt` file below."
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_result_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER)
    return embed


class ConfirmDeleteView(View):
    def __init__(self, parent: "CollectorInstallerView"):
        super().__init__(timeout=60)
        self.parent = parent

    async def on_timeout(self):
        if not self.parent.done:
            color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
            await self.parent.message.edit(
                embed=build_main_embed(self.parent.installed, color), view=self.parent
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, delete it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        DELETE_STEPS = [
            "Unloading extension",
            "Deleting package files",
            "Removing from config.yml",
        ]
        steps = [(s, None) for s in DELETE_STEPS]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.parent.message.edit(
                embed=_progress_embed("🗑️ Deleting Collector Package…", steps, discord.Color.red()),
                view=None,
            )

        await self.parent.message.edit(
            embed=_progress_embed("🗑️ Deleting Collector Package…", steps, discord.Color.red()),
            view=None,
        )

        try:
            try:
                await self.parent.bot.unload_extension("ballsdex.packages.collector")
            except Exception:
                pass
            await update(0)

            delete_files()
            if hasattr(self.parent.bot, "collector_requirements"):
                del self.parent.bot.collector_requirements
            if hasattr(self.parent.bot, "collector_claimed"):
                del self.parent.bot.collector_claimed
            await update(1)

            remove_from_config()
            await update(2)

            self.parent.installed = False
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Successfully Deleted",
                    (
                        "The **Collector Package** has been removed.\n\n"
                        "• All package files deleted\n"
                        "• Removed from `config.yml`\n"
                        "• All requirements wiped\n\n"
                        "Restart the bot to fully apply the config change.\n\n"
                        "Run this installer again to reinstall."
                    ),
                    discord.Color.red(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.parent.done = True
            self.stop()
            for i, (label, state) in enumerate(steps):
                if state is None:
                    steps[i] = (label, False)
                    break
            f = discord.File(io.BytesIO(err.encode()), filename="delete_error.txt")
            await self.parent.message.edit(embed=build_error_embed("deleting", err), view=None)
            await interaction.followup.send(file=f)

    @discord.ui.button(label="No, go back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
        await self.parent.message.edit(
            embed=build_main_embed(self.parent.installed, color), view=self.parent
        )


class CollectorInstallerView(View):
    def __init__(self, bot, ctx, installed: bool):
        super().__init__(timeout=180)
        self.bot = bot
        self.ctx = ctx
        self.installed = installed
        self.done = False
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        for c in self.children:
            if c.label == "Install":
                c.disabled = self.installed
            elif c.label in ("Update", "Delete"):
                c.disabled = not self.installed

    async def on_timeout(self):
        if self.done:
            return
        for c in self.children:
            c.disabled = True
        if self.message:
            embed = build_main_embed(self.installed, discord.Color.dark_grey())
            embed.set_footer(text=FOOTER_TIMEOUT)
            await self.message.edit(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Install", style=discord.ButtonStyle.success, emoji="📥")
    async def install_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        INSTALL_STEPS = [
            "Creating package folder",
            "Downloading files",
            "Creating requirements file",
            "Adding to config.yml",
            "Loading extension",
            "Syncing command tree",
        ]
        steps = [(s, None) for s in INSTALL_STEPS]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.message.edit(
                embed=_progress_embed("Installing Collector Package…", steps, discord.Color.blurple()),
                view=None,
            )

        await self.message.edit(
            embed=_progress_embed("Installing Collector Package…", steps, discord.Color.blurple()),
            view=None,
        )

        try:
            os.makedirs(PKG, exist_ok=True)
            await update(0)

            download_files()
            await update(1)

            ensure_requirements_file()
            await update(2)

            add_to_config()
            await update(3)

            await self.bot.load_extension("ballsdex.packages.collector")
            await update(4)

            from ballsdex.settings import settings
            await self.bot.tree.sync()
            for guild_id in settings.admin_guild_ids:
                await self.bot.tree.sync(guild=discord.Object(id=guild_id))
            await update(5)

            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Installed",
                    (
                        "The **Collector Package** has been installed and loaded.\n\n"
                        "You can now use `/collector claim`, `/collector list` "
                        "and the `/admin collector` commands.\n\n"
                        "Run this installer again to update or remove the package."
                    ),
                    discord.Color.green(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.done = True
            self.stop()
            for i, (label, state) in enumerate(steps):
                if state is None:
                    steps[i] = (label, False)
                    break
            f = discord.File(io.BytesIO(err.encode()), filename="install_error.txt")
            await self.message.edit(embed=build_error_embed("installing", err), view=None)
            await interaction.followup.send(file=f)

    @discord.ui.button(label="Update", style=discord.ButtonStyle.primary, emoji="🔄")
    async def update_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        UPDATE_STEPS = [
            "Downloading latest files",
            "Reloading extension",
            "Syncing command tree",
        ]
        steps = [(s, None) for s in UPDATE_STEPS]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.message.edit(
                embed=_progress_embed("Updating Collector Package…", steps, discord.Color.blurple()),
                view=None,
            )

        await self.message.edit(
            embed=_progress_embed("Updating Collector Package…", steps, discord.Color.blurple()),
            view=None,
        )

        try:
            download_files()
            await update(0)

            loaded = "ballsdex.packages.collector" in self.bot.extensions
            if loaded:
                await self.bot.reload_extension("ballsdex.packages.collector")
            else:
                await self.bot.load_extension("ballsdex.packages.collector")
            await update(1)

            from ballsdex.settings import settings
            await self.bot.tree.sync()
            for guild_id in settings.admin_guild_ids:
                await self.bot.tree.sync(guild=discord.Object(id=guild_id))
            await update(2)

            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Updated",
                    (
                        "The **Collector Package** has been updated and reloaded.\n\n"
                        "All commands are now running the latest version.\n\n"
                        "Run this installer again to update or remove the package."
                    ),
                    discord.Color.blue(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.done = True
            self.stop()
            for i, (label, state) in enumerate(steps):
                if state is None:
                    steps[i] = (label, False)
                    break
            f = discord.File(io.BytesIO(err.encode()), filename="update_error.txt")
            await self.message.edit(embed=build_error_embed("updating", err), view=None)
            await interaction.followup.send(file=f)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_embed(), view=ConfirmDeleteView(self))


installed = is_installed()
view = CollectorInstallerView(bot, ctx, installed)
initial_color = discord.Color.gold() if installed else discord.Color.greyple()
message = await ctx.send(embed=build_main_embed(installed, initial_color), view=view)
view.message = message
