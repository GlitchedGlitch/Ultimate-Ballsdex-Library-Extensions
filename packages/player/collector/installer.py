"""
Collector Package Installer — BallsDex v3

V3 packages are pip-installed via git+https in config/extra.toml and require
a `docker compose build` to take effect. This installer:

  Install — writes the [[ballsdex.packages]] entry to config/extra.toml
             and prompts the user to rebuild.
  Remove  — removes the entry from config/extra.toml
             and prompts the user to rebuild.

"""

import io, os, re, traceback, discord
from discord.ui import View, Button

REPO_URL   = "git+https://github.com/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions.git@v3"
APP_PATH   = "collector"          # the `path` field in extra.toml
EXTRA_TOML = "/code/config/extra.toml"
TOML_MARKER = f'path = "{APP_PATH}"'
TOML_BLOCK = (
    "\n[[ballsdex.packages]]\n"
    f'location = "{REPO_URL}"\n'
    f'path = "{APP_PATH}"\n'
    "enabled = true\n"
    "editable = false\n"
)

FOOTER         = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"


# ── extra.toml helpers ────────────────────────────────────────────────────────

def _toml_has_entry() -> bool:
    if not os.path.isfile(EXTRA_TOML):
        return False
    with open(EXTRA_TOML, "r") as f:
        return TOML_MARKER in f.read()


def _add_to_toml():
    os.makedirs(os.path.dirname(EXTRA_TOML), exist_ok=True)
    if os.path.isfile(EXTRA_TOML):
        with open(EXTRA_TOML, "r") as f:
            contents = f.read()
        if TOML_MARKER in contents:
            return  # already present
        with open(EXTRA_TOML, "a") as f:
            f.write(TOML_BLOCK)
    else:
        with open(EXTRA_TOML, "w") as f:
            f.write(TOML_BLOCK.lstrip())


def _remove_from_toml():
    if not os.path.isfile(EXTRA_TOML):
        return
    with open(EXTRA_TOML, "r") as f:
        contents = f.read()
    cleaned = re.sub(
        r"\n?\[\[ballsdex\.packages\]\][^\[]*path\s*=\s*\"collector\"[^\[]*",
        "",
        contents,
        flags=re.DOTALL,
    )
    with open(EXTRA_TOML, "w") as f:
        f.write(cleaned)


def is_installed() -> bool:
    """True if the package entry exists in extra.toml."""
    return _toml_has_entry()


# ── Embeds ────────────────────────────────────────────────────────────────────

def build_main_embed(installed: bool, color: discord.Color) -> discord.Embed:
    status = "✅ Registered in `config/extra.toml`" if installed else "❌ Not installed"
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
            "**How it works**\n"
            "Admins configure a minimum ball count and a special reward. "
            "Players who own enough copies of that ball can claim a collector "
            "version with the chosen special applied.\n\n"
            f"**Status:** {status}\n\n"
            "⚠️ **v3 note:** After installing or removing, you must run "
            "`docker compose build && docker compose up -d` to apply changes."
        ),
        color=color,
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_confirm_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Remove Collector Package",
        description=(
            "⚠️ **Are you sure you want to remove the Collector package?**\n\n"
            "This will remove the entry from `config/extra.toml`.\n\n"
            "You will need to run:\n"
            "```\ndocker compose build\ndocker compose up -d\n```\n"
            "to fully uninstall the package.\n\n"
            "This does **not** delete any ball instances already created."
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


# ── Confirm remove view ───────────────────────────────────────────────────────

class ConfirmRemoveView(View):
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

    @discord.ui.button(label="Yes, remove it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        try:
            _remove_from_toml()
            self.parent.installed = False
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Entry Removed",
                    (
                        "The **Collector Package** entry has been removed from "
                        "`config/extra.toml`.\n\n"
                        "Run the following to fully uninstall:\n"
                        "```\ndocker compose build\ndocker compose up -d\n```"
                    ),
                    discord.Color.red(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(embed=build_error_embed("removing", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="remove_error.txt")
            )

    @discord.ui.button(label="No, go back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
        await self.parent.message.edit(
            embed=build_main_embed(self.parent.installed, color), view=self.parent
        )


# ── Main installer view ───────────────────────────────────────────────────────

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
            elif c.label == "Remove":
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
        try:
            _add_to_toml()
            self.installed = True
            self._update_buttons()
            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Entry Added — Rebuild Required",
                    (
                        "The **Collector Package** has been added to "
                        "`config/extra.toml`.\n\n"
                        "To finish installation, run:\n"
                        "```\ndocker compose build\ndocker compose up -d\n```\n"
                        "After the rebuild, `collector` will appear in the "
                        "packages loaded log and all commands will be available."
                    ),
                    discord.Color.green(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.done = True
            self.stop()
            await self.message.edit(embed=build_error_embed("installing", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="install_error.txt")
            )

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_embed(), view=ConfirmRemoveView(self))


# ── Entry point ───────────────────────────────────────────────────────────────

installed = is_installed()
view = CollectorInstallerView(bot, ctx, installed)
initial_color = discord.Color.gold() if installed else discord.Color.greyple()
message = await ctx.send(embed=build_main_embed(installed, initial_color), view=view)
view.message = message
