import base64, os, requests, discord
from discord.ui import View, Button

REPO = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BASE = "https://api.github.com/repos/{}/contents/packages/player/collector/{}".format(REPO, "{}")
PKG = "/code/ballsdex/packages/collector"
CONFIG = "/code/config.yml"
PACKAGE_ENTRY = "  - ballsdex.packages.collector"
FILES = ("__init__.py", "cog.py")


def is_installed():
    return os.path.isdir(PKG) and os.path.isfile(os.path.join(PKG, "cog.py"))


def download_files():
    for f in FILES:
        response = requests.get(BASE.format(f))
        content = base64.b64decode(response.json()["content"]).decode()
        with open(os.path.join(PKG, f), "w") as file:
            file.write(content)


def add_to_config():
    with open(CONFIG, "r") as f:
        config = f.read()
    if "ballsdex.packages.collector" not in config:
        config = config.replace("packages:", "packages:\n" + PACKAGE_ENTRY)
        with open(CONFIG, "w") as f:
            f.write(config)


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


FOOTER = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch) • Timed out"


def build_main_embed(installed: bool, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(
        title="Collector Package",
        description=(
            "Adds a collector system to your BallsDex instance.\n\n"
            "**Commands**\n"
            "• `/collector claim` — claim a special collector version of a ball\n"
            "• `/collector list` — view all active collector requirements\n"
            "• `/admin collector set` — set a requirement and reward special\n"
            "• `/admin collector delete` — remove a requirement\n"
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
        title="🗑️ Delete Collector Package",
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


def build_installed_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Successfully Installed",
        description=(
            "The **Collector Package** has been installed and loaded.\n\n"
            "You can now use `/collector claim`, `/collector list` "
            "and the `/admin collector` commands.\n\n"
            "Run this installer again if you want to update or remove the package."
        ),
        color=discord.Color.green(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_updated_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Successfully Updated",
        description=(
            "The **Collector Package** has been updated and reloaded.\n\n"
            "All commands are running on the latest version.\n\n"
            "Run this installer again if you want to update or remove the package."
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_deleted_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Successfully Deleted",
        description=(
            "The **Collector Package** has been removed.\n\n"
            "• All package files have been deleted\n"
            "• The entry has been removed from `config.yml`\n"
            "• All active collector requirements have been wiped\n\n"
            "Restart the bot to fully apply the config change.\n\n"
            "Run this installer again if you want to reinstall the package."
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text=FOOTER)
    return embed


class ConfirmDeleteView(View):
    def __init__(self, parent: "CollectorInstallerView"):
        super().__init__(timeout=60)
        self.parent = parent

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        await self.parent.message.edit(
            embed=build_main_embed(
                self.parent.installed,
                discord.Color.gold() if self.parent.installed else discord.Color.greyple(),
            ),
            view=self.parent,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.ctx.author.id:
            await interaction.response.send_message(
                "Only the person who ran this command can use these buttons.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Yes, delete it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        try:
            await self.parent.bot.unload_extension("ballsdex.packages.collector")
        except Exception:
            pass
        delete_files()
        remove_from_config()
        if hasattr(self.parent.bot, "collector_requirements"):
            del self.parent.bot.collector_requirements
        if hasattr(self.parent.bot, "collector_claimed"):
            del self.parent.bot.collector_claimed
        self.stop()
        await self.parent.message.edit(embed=build_deleted_embed(), view=None)

    @discord.ui.button(label="No, go back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.parent.message.edit(
            embed=build_main_embed(
                self.parent.installed,
                discord.Color.gold() if self.parent.installed else discord.Color.greyple(),
            ),
            view=self.parent,
        )


class CollectorInstallerView(View):
    def __init__(self, bot, ctx, installed: bool):
        super().__init__(timeout=180)
        self.bot = bot
        self.ctx = ctx
        self.installed = installed
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        for child in self.children:
            if child.label == "Install":
                child.disabled = self.installed
            elif child.label in ("Update", "Delete"):
                child.disabled = not self.installed

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            embed = build_main_embed(self.installed, discord.Color.dark_grey())
            embed.set_footer(text=FOOTER_TIMEOUT)
            await self.message.edit(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the person who ran this command can use these buttons.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Install", style=discord.ButtonStyle.success, emoji="📥")
    async def install_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        os.makedirs(PKG, exist_ok=True)
        download_files()
        add_to_config()
        try:
            await self.bot.load_extension("ballsdex.packages.collector")
        except Exception:
            await self.bot.reload_extension("ballsdex.packages.collector")
        self.stop()
        await self.message.edit(embed=build_installed_embed(), view=None)

    @discord.ui.button(label="Update", style=discord.ButtonStyle.primary, emoji="🔄")
    async def update_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        download_files()
        try:
            await self.bot.reload_extension("ballsdex.packages.collector")
        except Exception:
            await self.bot.load_extension("ballsdex.packages.collector")
        self.stop()
        await self.message.edit(embed=build_updated_embed(), view=None)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(
            embed=build_confirm_embed(),
            view=ConfirmDeleteView(self),
        )


installed = is_installed()
view = CollectorInstallerView(bot, ctx, installed)
initial_color = discord.Color.gold() if installed else discord.Color.greyple()
message = await ctx.send(embed=build_main_embed(installed, initial_color), view=view)
view.message = message
