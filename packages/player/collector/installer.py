"""
Collector Package Installer — BallsDex v3 :DD

"""

import base64, io, os, re, requests, traceback, discord
from discord.ui import View, Button

REPO       = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BRANCH     = "v3"
GIT_URL    = f"git+https://github.com/{REPO}.git@{BRANCH}"
APP_PATH   = "collector_app"
TOML_MARKER = f'path = "{APP_PATH}"'
TOML_ENTRY = (
    "\n[[ballsdex.packages]]\n"
    f'location = "{GIT_URL}"\n'
    f'path = "{APP_PATH}"\n'
    "enabled = true\n"
    "editable = false\n"
)

EXTRA_TOML = "/code/config/extra.toml"

FOOTER         = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"
BAR_FILLED, BAR_EMPTY, BAR_LEN = "█", "░", 10

RO_WARNING = (
    "\n\n⚠️ **Before rebuilding**, make sure your `docker-compose.yml` has "
    "`rw` (not `ro`) on these two lines:\n"
    "```yaml\n"
    "- \"./config:/code/config:rw\"\n"
    "- \"./extra:/code/extra:rw\"\n"
    "```\n"
    "Then rebuild with:\n"
    "```\ndocker compose build\ndocker compose up -d\n```"
)


# ── extra.toml helpers ────────────────────────────────────────────────────────

def _toml_has_entry() -> bool:
    try:
        if not os.path.isfile(EXTRA_TOML):
            return False
        with open(EXTRA_TOML) as f:
            return TOML_MARKER in f.read()
    except OSError:
        return False


def _write_toml():
    os.makedirs(os.path.dirname(EXTRA_TOML), exist_ok=True)
    if os.path.isfile(EXTRA_TOML):
        with open(EXTRA_TOML) as f:
            contents = f.read()
        if TOML_MARKER in contents:
            return
        with open(EXTRA_TOML, "a") as f:
            f.write(TOML_ENTRY)
    else:
        with open(EXTRA_TOML, "w") as f:
            f.write(TOML_ENTRY.lstrip())


def _remove_toml():
    if not os.path.isfile(EXTRA_TOML):
        return
    with open(EXTRA_TOML) as f:
        contents = f.read()
    cleaned = re.sub(
        r"\n?\[\[ballsdex\.packages\]\][^\[]*path\s*=\s*\"collector_app\"[^\[]*",
        "", contents, flags=re.DOTALL,
    )
    with open(EXTRA_TOML, "w") as f:
        f.write(cleaned)


def is_installed() -> bool:
    return _toml_has_entry()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar(current: int, total: int) -> str:
    filled = round(BAR_LEN * current / total)
    return f"`{BAR_FILLED * filled}{BAR_EMPTY * (BAR_LEN - filled)}` {round(100 * current / total)}%"


def _progress_embed(title: str, steps: list, color: discord.Color) -> discord.Embed:
    done  = sum(1 for _, s in steps if s is True)
    icons = {None: "⬜", True: "✅", False: "❌"}
    lines = [f"{icons[s]} {label}" for label, s in steps]
    e = discord.Embed(title=title, description="\n".join(lines) + f"\n\n{_bar(done, len(steps))}", color=color)
    e.set_footer(text=FOOTER)
    return e


# ── Embeds ────────────────────────────────────────────────────────────────────

def build_main_embed(installed: bool, color: discord.Color) -> discord.Embed:
    status = "Registered in `extra.toml` — rebuild to activate" if installed else "❌ Not installed"
    e = discord.Embed(
        title="Collector Package",
        description=(
            "Adds a collector system to your BallsDex instance.\n\n"
            "**Commands**\n"
            "• `collector claim` — claim a collector ball\n"
            "• `collector list` — view all active requirements\n"
            "• `admin collector set` — set a requirement and reward\n"
            "• `admin collector delete` — remove a requirement\n"
            "• `admin collector view` — inspect a requirement\n\n"
            f"**Status:** {status}"
        ),
        color=color,
    )
    e.set_footer(text=FOOTER)
    return e


def build_confirm_embed() -> discord.Embed:
    e = discord.Embed(
        title="Remove Collector Package",
        description=(
            "⚠️ **Are you sure?**\n\n"
            "This will remove the entry from `config/extra.toml`.\n"
            "The package will stop loading after the next rebuild.\n\n"
            "No ball instances will be deleted."
        ),
        color=discord.Color.orange(),
    )
    e.set_footer(text=FOOTER)
    return e


def build_error_embed(action: str, error: str) -> discord.Embed:
    short = error[:1000] + "..." if len(error) > 1000 else error
    e = discord.Embed(
        title="An error occurred",
        description=f"An error occurred when **{action}** the package!\n\n```\n{short}\n```\n\nFull error attached below.",
        color=discord.Color.red(),
    )
    e.set_footer(text=FOOTER)
    return e


def build_result_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.set_footer(text=FOOTER)
    return e


# ── Confirm remove ────────────────────────────────────────────────────────────

class ConfirmRemoveView(View):
    def __init__(self, parent: "CollectorInstallerView"):
        super().__init__(timeout=60)
        self.parent = parent

    async def on_timeout(self):
        if not self.parent.done:
            color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
            await self.parent.message.edit(embed=build_main_embed(self.parent.installed, color), view=self.parent)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, remove it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        try:
            _remove_toml()
            self.parent.installed = False
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Entry Removed",
                    "Removed from `config/extra.toml`.\n\n"
                    "The package will stop loading after the next rebuild.\n"
                    "No ball instances were deleted." + RO_WARNING,
                    discord.Color.red(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(embed=build_error_embed("removing", err), view=None)
            await interaction.followup.send(file=discord.File(io.BytesIO(err.encode()), filename="remove_error.txt"))

    @discord.ui.button(label="No, go back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
        await self.parent.message.edit(embed=build_main_embed(self.parent.installed, color), view=self.parent)


# ── Main installer view ───────────────────────────────────────────────────────

class CollectorInstallerView(View):
    def __init__(self, bot, ctx, installed: bool):
        super().__init__(timeout=180)
        self.bot = bot; self.ctx = ctx
        self.installed = installed
        self.done = False; self.message = None
        self._update_buttons()

    def _update_buttons(self):
        for c in self.children:
            if c.label == "Install":
                c.disabled = self.installed
            elif c.label == "Remove":
                c.disabled = not self.installed

    async def on_timeout(self):
        if self.done: return
        for c in self.children: c.disabled = True
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
        steps = [("Writing to config/extra.toml", None)]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.message.edit(embed=_progress_embed("Installing Collector Package…", steps, discord.Color.blurple()), view=None)

        await self.message.edit(embed=_progress_embed("Installing Collector Package…", steps, discord.Color.blurple()), view=None)

        try:
            _write_toml()
            await update(0)
            self.installed = True
            self._update_buttons()
            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Entry Added — Rebuild Required",
                    f"Added to `config/extra.toml`.\n\n"
                    f"The package installs automatically on rebuild and will appear "
                    f"in the packages loaded log as `collector_app`.\n\n"
                    f"**Commands after rebuild:**\n"
                    f"• `collector claim`\n• `collector list`\n• `admin collector set/delete/view`\n\n"
                    + RO_WARNING,
                    discord.Color.green(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.done = True; self.stop()
            steps[0] = (steps[0][0], False)
            await self.message.edit(embed=build_error_embed("installing", err), view=None)
            await interaction.followup.send(file=discord.File(io.BytesIO(err.encode()), filename="install_error.txt"))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_embed(), view=ConfirmRemoveView(self))


# ── Entry point ───────────────────────────────────────────────────────────────

installed = is_installed()
view      = CollectorInstallerView(bot, ctx, installed)
color     = discord.Color.gold() if installed else discord.Color.greyple()
message   = await ctx.send(embed=build_main_embed(installed, color), view=view)
view.message = message
