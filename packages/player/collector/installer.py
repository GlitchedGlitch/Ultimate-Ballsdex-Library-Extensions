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


def is_in_config():
    with open(CONFIG, "r") as f:
        return "ballsdex.packages.collector" in f.read()


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


installed = is_installed()

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
    color=discord.Color.gold() if installed else discord.Color.red(),
)
embed.set_footer(text="Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)")


class CollectorInstallerView(View):
    def __init__(self, bot, ctx):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx

    @discord.ui.button(
        label="Install",
        style=discord.ButtonStyle.success,
        emoji="📥",
        disabled=is_installed(),
    )
    async def install_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return
        await interaction.response.defer()
        os.makedirs(PKG, exist_ok=True)
        download_files()
        add_to_config()
        try:
            await self.bot.load_extension("ballsdex.packages.collector")
        except Exception:
            await self.bot.reload_extension("ballsdex.packages.collector")
        embed.description = embed.description.replace("❌ Not installed", "✅ Installed")
        embed.color = discord.Color.gold()
        for child in self.children:
            if child.label == "Install":
                child.disabled = True
            if child.label == "Update":
                child.disabled = False
        await interaction.message.edit(
            content="Collector package installed and loaded!",
            embed=embed,
            view=self,
        )

    @discord.ui.button(
        label="Update",
        style=discord.ButtonStyle.primary,
        emoji="🔄",
        disabled=not is_installed(),
    )
    async def update_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return
        await interaction.response.defer()
        download_files()
        try:
            await self.bot.reload_extension("ballsdex.packages.collector")
        except Exception:
            await self.bot.load_extension("ballsdex.packages.collector")
        await interaction.message.edit(
            content="Collector package updated and reloaded!",
            embed=embed,
            view=self,
        )

    @discord.ui.button(
        label="Delete",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        disabled=not is_installed(),
    )
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.bot.unload_extension("ballsdex.packages.collector")
        except Exception:
            pass
        delete_files()
        remove_from_config()
        # Clear persistent data from bot
        if hasattr(self.bot, "collector_requirements"):
            del self.bot.collector_requirements
        if hasattr(self.bot, "collector_claimed"):
            del self.bot.collector_claimed
        embed.description = embed.description.replace("✅ Installed", "❌ Not installed")
        embed.color = discord.Color.red()
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(
            content="Collector package deleted.",
            embed=embed,
            view=self,
        )


await ctx.send(embed=embed, view=CollectorInstallerView(bot, ctx))
