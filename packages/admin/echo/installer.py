import base64, io, os, requests, traceback, discord
from discord.ui import View, Button, Modal, TextInput

REPO = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BASE = "https://api.github.com/repos/{}/contents/packages/admin/echo/{}".format(REPO, "{}")
PKG = "/code/ballsdex/packages/echo"
CONFIG = "/code/config.yml"
NAME_FILE = os.path.join(PKG, "name.txt")
PACKAGE_ENTRY = "  - ballsdex.packages.echo"
FILES = ("__init__.py", "cog.py")
FOOTER = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"
DEFAULT_NAME = "echo"


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_installed():
    return os.path.isdir(PKG) and os.path.isfile(os.path.join(PKG, "cog.py"))


def get_command_name() -> str:
    try:
        with open(NAME_FILE, "r") as f:
            name = f.read().strip()
            return name if name else DEFAULT_NAME
    except FileNotFoundError:
        return DEFAULT_NAME


def save_command_name(name: str):
    with open(NAME_FILE, "w") as f:
        f.write(name.strip())


def download_files():
    for f in FILES:
        resp = requests.get(BASE.format(f))
        resp.raise_for_status()
        content = base64.b64decode(resp.json()["content"]).decode()
        with open(os.path.join(PKG, f), "w") as fh:
            fh.write(content)


def add_to_config():
    with open(CONFIG, "r") as f:
        config = f.read()
    if "ballsdex.packages.echo" not in config:
        config = config.replace("packages:", "packages:\n" + PACKAGE_ENTRY)
        with open(CONFIG, "w") as f:
            f.write(config)


def remove_from_config():
    with open(CONFIG, "r") as f:
        lines = f.readlines()
    lines = [l for l in lines if "ballsdex.packages.echo" not in l]
    with open(CONFIG, "w") as f:
        f.writelines(lines)


def delete_files():
    import shutil
    if os.path.isdir(PKG):
        shutil.rmtree(PKG)


# ── Embeds ────────────────────────────────────────────────────────────────────

def build_main_embed(installed: bool, color: discord.Color, cmd_name: str) -> discord.Embed:
    embed = discord.Embed(
        title="Echo Package",
        description=(
            "Adds an admin echo command to your BallsDex instance.\n\n"
            "**Commands**\n"
            f"• `/admin {cmd_name}` — send, edit or reply to messages as the bot\n\n"
            "**Parameters**\n"
            "• `message` — text content to send or edit with\n"
            "• `image` — file attachment to include\n"
            "• `embed` — wrap message in an embed\n"
            "• `channel` — target channel (works cross-server)\n"
            "• `edit_message` — message link to edit instead of sending\n"
            "• `reply` — message link to reply to\n\n"
            f"**Command name:** `/admin {cmd_name}`\n"
            f"**Status:** {'✅ Installed' if installed else '❌ Not installed'}"
        ),
        color=color,
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_name_embed(cmd_name: str) -> discord.Embed:
    embed = discord.Embed(
        title="Set Command Name",
        description=(
            "Choose a name for the command.\n\n"
            f"Current name: `/admin {cmd_name}`\n\n"
            "The group will always be `/admin`. "
            "Only lowercase letters, numbers and hyphens are allowed.\n\n"
            "Type the new name in the box below and confirm, "
            "or press **Cancel** to go back."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_confirm_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🗑️ Delete Echo Package",
        description=(
            "⚠️ **Are you sure you want to delete the Echo package?**\n\n"
            "This will:\n"
            "• Unload the package from the bot\n"
            "• Delete all package files\n"
            "• Remove it from `config.yml`\n\n"
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


# ── Name modal ────────────────────────────────────────────────────────────────

class CommandNameModal(Modal, title="Set Echo Command Name"):
    name_input = TextInput(
        label="Command name (group is always /admin)",
        placeholder="echo",
        min_length=1,
        max_length=32,
        required=True,
    )

    def __init__(self, parent: "EchoInstallerView"):
        super().__init__()
        self.parent = parent
        self.name_input.default = self.parent.cmd_name

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.name_input.value.strip().lower().replace(" ", "-")
        # Validate: only lowercase letters, digits, hyphens
        import re
        if not re.match(r"^[a-z0-9\-]{1,32}$", raw):
            await interaction.response.send_message(
                "Invalid name. Use only lowercase letters, numbers and hyphens.",
                ephemeral=True,
            )
            return

        self.parent.cmd_name = raw

        # If already installed, save and reload immediately
        if self.parent.installed:
            save_command_name(raw)
            try:
                await self.parent.bot.reload_extension("ballsdex.packages.echo")
                await interaction.response.edit_message(
                    embed=build_main_embed(True, discord.Color.gold(), raw),
                    view=self.parent,
                )
                await interaction.followup.send(
                    f"Command renamed to `/admin {raw}` and reloaded!",
                    ephemeral=True,
                )
            except Exception as e:
                await interaction.response.send_message(
                    f"Saved name but failed to reload:\n```py\n{e}\n```",
                    ephemeral=True,
                )
        else:
            # Just update the embed preview before installing
            await interaction.response.edit_message(
                embed=build_main_embed(False, discord.Color.greyple(), raw),
                view=self.parent,
            )


# ── Confirm delete ────────────────────────────────────────────────────────────

class ConfirmDeleteView(View):
    def __init__(self, parent: "EchoInstallerView"):
        super().__init__(timeout=60)
        self.parent = parent

    async def on_timeout(self):
        if not self.parent.done:
            color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
            await self.parent.message.edit(
                embed=build_main_embed(self.parent.installed, color, self.parent.cmd_name),
                view=self.parent,
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, delete it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        try:
            await self.parent.bot.unload_extension("ballsdex.packages.echo")
        except Exception:
            pass
        try:
            delete_files()
            remove_from_config()
            self.parent.installed = False
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Successfully Deleted",
                    (
                        "The **Echo Package** has been removed.\n\n"
                        "• All package files deleted\n"
                        "• Removed from `config.yml`\n\n"
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
            f = discord.File(io.BytesIO(err.encode()), filename="delete_error.txt")
            await self.parent.message.edit(embed=build_error_embed("deleting", err), view=None)
            await interaction.followup.send(file=f)

    @discord.ui.button(label="No, go back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
        await self.parent.message.edit(
            embed=build_main_embed(self.parent.installed, color, self.parent.cmd_name),
            view=self.parent,
        )


# ── Main installer view ───────────────────────────────────────────────────────

class EchoInstallerView(View):
    def __init__(self, bot, ctx, installed: bool, cmd_name: str):
        super().__init__(timeout=180)
        self.bot = bot
        self.ctx = ctx
        self.installed = installed
        self.cmd_name = cmd_name
        self.done = False
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        for c in self.children:
            if c.label == "Install":
                c.disabled = self.installed
            elif c.label in ("Update", "Delete"):
                c.disabled = not self.installed
            # Rename is always enabled when installed or not

    async def on_timeout(self):
        if self.done:
            return
        for c in self.children:
            c.disabled = True
        if self.message:
            embed = build_main_embed(self.installed, discord.Color.dark_grey(), self.cmd_name)
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
            os.makedirs(PKG, exist_ok=True)
            download_files()
            save_command_name(self.cmd_name)
            add_to_config()
            await self.bot.load_extension("ballsdex.packages.echo")
            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Installed",
                    (
                        f"The **Echo Package** has been installed as `/admin {self.cmd_name}`.\n\n"
                        "Run this installer again to update, rename or remove the package."
                    ),
                    discord.Color.green(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.done = True
            self.stop()
            f = discord.File(io.BytesIO(err.encode()), filename="install_error.txt")
            await self.message.edit(embed=build_error_embed("installing", err), view=None)
            await interaction.followup.send(file=f)

    @discord.ui.button(label="Update", style=discord.ButtonStyle.primary, emoji="🔄")
    async def update_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        try:
            download_files()
            loaded = "ballsdex.packages.echo" in self.bot.extensions
            if loaded:
                await self.bot.reload_extension("ballsdex.packages.echo")
            else:
                await self.bot.load_extension("ballsdex.packages.echo")
            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Updated",
                    (
                        "The **Echo Package** has been updated and reloaded.\n\n"
                        "Run this installer again to update, rename or remove the package."
                    ),
                    discord.Color.blue(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.done = True
            self.stop()
            f = discord.File(io.BytesIO(err.encode()), filename="update_error.txt")
            await self.message.edit(embed=build_error_embed("updating", err), view=None)
            await interaction.followup.send(file=f)

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def rename_button(self, interaction: discord.Interaction, button: Button):
        # Open a modal — no defer needed, modal is the response
        await interaction.response.send_modal(CommandNameModal(self))

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_embed(), view=ConfirmDeleteView(self))


# ── Entry point ───────────────────────────────────────────────────────────────

installed = is_installed()
cmd_name = get_command_name() if installed else DEFAULT_NAME
view = EchoInstallerView(bot, ctx, installed, cmd_name)
initial_color = discord.Color.gold() if installed else discord.Color.greyple()
message = await ctx.send(embed=build_main_embed(installed, initial_color, cmd_name), view=view)
view.message = message
