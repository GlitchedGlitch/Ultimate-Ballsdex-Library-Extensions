"""
Collector Package Installer

"""

import base64, io, os, requests, traceback, discord
from discord.ui import View, Button

REPO   = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BRANCH = "v3"
API    = "https://api.github.com/repos/{}/contents/packages/player/collector/{}?ref={}".format(
    REPO, "{}", BRANCH
)

PKG     = "/code/ballsdex/packages/collector"
EXT     = "ballsdex.packages.collector"
FILES   = ("__init__.py", "cog.py")

FOOTER         = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"
BAR_FILLED, BAR_EMPTY, BAR_LEN = "█", "░", 10


def _bar(current: int, total: int) -> str:
    filled = round(BAR_LEN * current / total)
    pct    = round(100 * current / total)
    return f"`{BAR_FILLED * filled}{BAR_EMPTY * (BAR_LEN - filled)}` {pct}%"


def _progress_embed(title: str, steps: list, color: discord.Color) -> discord.Embed:
    done  = sum(1 for _, s in steps if s is True)
    icons = {None: "⬜", True: "✅", False: "❌"}
    lines = [f"{icons[s]} {label}" for label, s in steps]
    embed = discord.Embed(
        title=title,
        description="\n".join(lines) + f"\n\n{_bar(done, len(steps))}",
        color=color,
    )
    embed.set_footer(text=FOOTER)
    return embed


def _fetch(filename: str) -> str:
    resp = requests.get(API.format(filename))
    resp.raise_for_status()
    return base64.b64decode(resp.json()["content"]).decode()


def is_installed() -> bool:
    return os.path.isfile(os.path.join(PKG, "cog.py"))


def download_files():
    os.makedirs(PKG, exist_ok=True)
    for fname in FILES:
        content = _fetch(fname)
        with open(os.path.join(PKG, fname), "w") as f:
            f.write(content)


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
            "• `collector claim` — claim a collector ball\n"
            "• `collector list` — view all active requirements\n"
            "• `admin collector set` — set a requirement and reward\n"
            "• `admin collector delete` — remove a requirement\n"
            "• `admin collector view` — inspect a requirement\n\n"
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
            "**Are you sure you want to delete the Collector package?**\n\n"
            "This will:\n"
            "• Unload the extension\n"
            "• Delete all package files from `ballsdex/packages/collector/`\n\n"
            "No ball instances will be deleted.\n"
            "This action cannot be undone without reinstalling."
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

        steps = [("Unloading extension", None), ("Deleting package files", None)]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.parent.message.edit(
                embed=_progress_embed("Deleting Collector Package…", steps, discord.Color.red()),
                view=None,
            )

        await self.parent.message.edit(
            embed=_progress_embed("Deleting Collector Package…", steps, discord.Color.red()),
            view=None,
        )

        try:
            try:
                await self.parent.bot.unload_extension(EXT)
            except Exception:
                pass
            await update(0)

            delete_files()
            for attr in ("collector_requirements", "collector_claimed"):
                if hasattr(self.parent.bot, attr):
                    delattr(self.parent.bot, attr)
            await update(1)

            self.parent.installed = False
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Successfully Deleted",
                    "The **Collector Package** has been unloaded and its files deleted.\n\n"
                    "No ball instances were removed.\n"
                    "Run this installer again to reinstall.",
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
            await self.parent.message.edit(embed=build_error_embed("deleting", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="delete_error.txt")
            )

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
        self.bot       = bot
        self.ctx       = ctx
        self.installed = installed
        self.done      = False
        self.message   = None
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

        steps = [
            ("Creating package folder", None),
            ("Downloading files", None),
            ("Loading extension", None),
        ]

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

            await self.bot.load_extension(EXT)
            await update(2)

            self.installed = True
            self._update_buttons()
            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Installed",
                    "The **Collector Package** has been installed and loaded.\n\n"
                    "Commands available:\n"
                    "• `collector claim`\n"
                    "• `collector list`\n"
                    "• `admin collector set/delete/view`\n\n"
                    "Run this installer again to update or remove the package.",
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
            await self.message.edit(embed=build_error_embed("installing", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="install_error.txt")
            )

    @discord.ui.button(label="Update", style=discord.ButtonStyle.primary, emoji="🔄")
    async def update_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        steps = [
            ("Downloading latest files", None),
            ("Reloading extension", None),
        ]

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

            if EXT in self.bot.extensions:
                await self.bot.reload_extension(EXT)
            else:
                await self.bot.load_extension(EXT)
            await update(1)

            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Updated",
                    "The **Collector Package** has been updated and reloaded.\n\n"
                    "All commands are now running the latest version.",
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
            await self.message.edit(embed=build_error_embed("updating", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="update_error.txt")
            )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_embed(), view=ConfirmDeleteView(self))


# ── Entry point ───────────────────────────────────────────────────────────────

installed = is_installed()
view      = CollectorInstallerView(bot, ctx, installed)
color     = discord.Color.gold() if installed else discord.Color.greyple()
message   = await ctx.send(embed=build_main_embed(installed, color), view=view)
view.message = message
