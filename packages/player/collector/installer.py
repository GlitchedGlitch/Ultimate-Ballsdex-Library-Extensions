import base64, io, json, os, subprocess, requests, traceback, discord
from discord.ui import View, Button

REPO = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BRANCH = "v2-main"
BASE = f"https://api.github.com/repos/{REPO}/contents/packages/player/collector/{{}}?ref={BRANCH}"
PKG = "/code/ballsdex/packages/collector"
CONFIG = "/code/config.yml"
REQUIREMENTS_FILE = os.path.join(PKG, "requirements.txt")
PACKAGE_ENTRY = " - ballsdex.packages.collector"

# Admin panel files hosted in the same repo
ADMIN_PANEL_DST = "/code/admin_panel/collector_admin"
ADMIN_FILES = [
    ("admin_panel/__init__.py", f"{ADMIN_PANEL_DST}/__init__.py"),
    ("admin_panel/apps.py", f"{ADMIN_PANEL_DST}/apps.py"),
    ("admin_panel/models.py", f"{ADMIN_PANEL_DST}/models.py"),
    ("admin_panel/admin/__init__.py", f"{ADMIN_PANEL_DST}/admin/__init__.py"),
    ("admin_panel/admin/collector.py", f"{ADMIN_PANEL_DST}/admin/collector.py"),
]

BOT_FILES = ("__init__.py", "cog.py", "models.py")
FOOTER = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"

BAR_FILLED = "█"
BAR_EMPTY = "░"
BAR_LEN = 10

def _bar(current: int, total: int) -> str:
    filled = round(BAR_LEN * current / total)
    pct = round(100 * current / total)
    return f"`{BAR_FILLED * filled}{BAR_EMPTY * (BAR_LEN - filled)}` {pct}%"

def _progress_embed(title: str, steps: list, color: discord.Color) -> discord.Embed:
    done = sum(1 for _, s in steps if s is True)
    lines = []
    for label, state in steps:
        icon = {None: "⬜", True: "✅", False: "❌"}[state]
        lines.append(f"{icon} {label}")
    embed = discord.Embed(
        title=title,
        description="\n".join(lines) + f"\n\n{_bar(done, len(steps))}",
        color=color,
    )
    embed.set_footer(text=FOOTER)
    return embed

# ── File helpers ──────────────────────────────────────────────────────────────

def is_installed():
    return os.path.isdir(PKG) and os.path.isfile(os.path.join(PKG, "cog.py"))

def download_bot_files():
    for f in BOT_FILES:
        resp = requests.get(BASE.format(f))
        resp.raise_for_status()
        content = base64.b64decode(resp.json()["content"]).decode()
        with open(os.path.join(PKG, f), "w") as fh:
            fh.write(content)

def download_admin_files():
    os.makedirs(f"{ADMIN_PANEL_DST}/admin", exist_ok=True)
    for repo_path, dst_path in ADMIN_FILES:
        resp = requests.get(BASE.format(repo_path))
        resp.raise_for_status()
        content = base64.b64decode(resp.json()["content"]).decode()
        with open(dst_path, "w") as fh:
            fh.write(content)

def ensure_requirements_file():
    if not os.path.isfile(REQUIREMENTS_FILE):
        with open(REQUIREMENTS_FILE, "w") as f:
            f.write("{}")

def add_to_config():
    """Add bot package after trade line."""
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

def _yaml_dump_preserve(cfg: dict, path: str):
    """Dump YAML while preserving order and avoiding scrambled output.
    Tries ruamel.yaml first (preserves comments), falls back to pyyaml."""
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.comments import CommentedMap
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.width = 120
        # Convert plain dict to CommentedMap to preserve structure
        with open(path, "r") as f:
            data = yaml.load(f)
        # Update data with cfg values
        for key, value in cfg.items():
            data[key] = value
        with open(path, "w") as f:
            yaml.dump(data, f)
        return
    except ImportError:
        pass
    # Fallback: pyyaml with sort_keys=False
    import yaml
    with open(path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

def add_django_app_to_config():
    """Add collector_admin to extra-django-apps in config.yml."""
    try:
        import yaml
        with open(CONFIG, "r") as f:
            cfg = yaml.safe_load(f)
        apps = cfg.get("extra-django-apps") or []
        if "collector_admin" not in apps:
            apps.append("collector_admin")
        cfg["extra-django-apps"] = apps
        _yaml_dump_preserve(cfg, CONFIG)
    except Exception:
        pass

def add_tortoise_models_to_config():
    """Add collector models to extra-tortoise-models in config.yml."""
    try:
        import yaml
        with open(CONFIG, "r") as f:
            cfg = yaml.safe_load(f) or {}
        models = cfg.get("extra-tortoise-models") or []
        entry = "ballsdex.packages.collector.models"
        if entry not in models:
            models.append(entry)
            cfg["extra-tortoise-models"] = models
            _yaml_dump_preserve(cfg, CONFIG)
    except Exception:
        pass

def remove_tortoise_models_from_config():
    """Remove collector models from extra-tortoise-models in config.yml."""
    try:
        import yaml
        with open(CONFIG, "r") as f:
            cfg = yaml.safe_load(f) or {}
        models = cfg.get("extra-tortoise-models") or []
        entry = "ballsdex.packages.collector.models"
        if entry in models:
            models.remove(entry)
            cfg["extra-tortoise-models"] = models
            _yaml_dump_preserve(cfg, CONFIG)
    except Exception:
        pass

def run_migrations():
    """Run makemigrations + migrate for collector_admin."""
    for cmd in [
        ["python", "manage.py", "makemigrations", "collector_admin"],
        ["python", "manage.py", "migrate", "collector_admin"],
    ]:
        result = subprocess.run(
            cmd, cwd="/code/admin_panel",
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Migration failed:\n{result.stdout}\n{result.stderr}"
            )

def remove_from_config():
    with open(CONFIG, "r") as f:
        lines = f.readlines()
    lines = [l for l in lines if "ballsdex.packages.collector" not in l]
    with open(CONFIG, "w") as f:
        f.writelines(lines)

def remove_django_app_from_config():
    try:
        import yaml
        with open(CONFIG, "r") as f:
            cfg = yaml.safe_load(f)
        apps = cfg.get("extra-django-apps") or []
        if "collector_admin" in apps:
            apps.remove("collector_admin")
        cfg["extra-django-apps"] = apps
        _yaml_dump_preserve(cfg, CONFIG)
    except Exception:
        pass

def delete_files():
    import shutil
    if os.path.isdir(PKG):
        shutil.rmtree(PKG)
    if os.path.isdir(ADMIN_PANEL_DST):
        shutil.rmtree(ADMIN_PANEL_DST)

# ── Embeds ────────────────────────────────────────────────────────────────────

def build_main_embed(installed: bool, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(
        title="Collector Package",
        description=(
            "Adds a collector system to your BallsDex instance.\n\n"
            "**Commands**\n"
            "• `/collector claim` — claim a collector ball\n"
            "• `/collector list` — view all active requirements\n"
            "• `/admin collector set` — set a requirement\n"
            "• `/admin collector bulk` — bulk add requirements\n"
            "• `/admin collector delete` — remove a requirement\n"
            "• `/admin collector view` — inspect a requirement\n\n"
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
            "⚠️ **Are you sure?**\n\n"
            "This will remove the bot package, admin panel app, "
            "and config entries.\n\n"
            "**requirements.txt and claims.txt are kept** so data isn't lost."
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

# ── Confirm delete ────────────────────────────────────────────────────────────

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
            "Unloading bot extension",
            "Deleting package files",
            "Removing from config.yml",
            "Removing Tortoise models",
        ]
        steps = [(s, None) for s in DELETE_STEPS]

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

            remove_tortoise_models_from_config()
            remove_django_app_from_config()
            await update(3)

            self.parent.installed = False
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Successfully Deleted",
                    (
                        "The **Collector Package** has been removed.\n\n"
                        "• Bot package unloaded and files deleted\n"
                        "• Admin panel app removed\n"
                        "• Config entries cleaned up\n"
                        "Restart the bot and admin panel to fully apply."
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

        STEPS = [
            "Creating package folder",
            "Downloading bot files",
            "Creating requirements file",
            "Adding to config.yml",
            "Registering Tortoise models",
            "Downloading admin panel files",
            "Registering admin panel app",
            "Running migrations",
            "Loading bot extension",
            "Syncing command tree",
        ]
        steps = [(s, None) for s in STEPS]

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

            download_bot_files()
            await update(1)

            ensure_requirements_file()
            await update(2)

            add_to_config()
            await update(3)

            add_tortoise_models_to_config()
            await update(4)

            download_admin_files()
            await update(5)

            add_django_app_to_config()
            await update(6)

            run_migrations()
            await update(7)

            await self.bot.load_extension("ballsdex.packages.collector")
            await update(8)

            from ballsdex.settings import settings
            import asyncio
            await asyncio.gather(
                self.bot.tree.sync(),
                *[self.bot.tree.sync(guild=discord.Object(id=gid)) for gid in settings.admin_guild_ids]
            )
            await update(9)

            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Installed",
                    (
                        "The **Collector Package** has been installed.\n\n"
                        "• Bot commands: `/collector claim`, `/collector list`, `/admin collector`\n"
                        "• Admin panel: **Collector Requirements** section at `localhost:8000`\n\n"
                        "Restart the bot and admin panel container to fully apply.\n\n"
                        "Run this installer again to update or remove."
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

        STEPS = [
            "Downloading latest bot files",
            "Downloading latest admin panel files",
            "Registering Tortoise models",
            "Running migrations",
            "Reloading bot extension",
            "Syncing command tree",
        ]
        steps = [(s, None) for s in STEPS]

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
            download_bot_files()
            await update(0)

            download_admin_files()
            add_django_app_to_config()
            await update(1)

            add_tortoise_models_to_config()
            await update(2)

            run_migrations()
            await update(3)

            loaded = "ballsdex.packages.collector" in self.bot.extensions
            if loaded:
                await self.bot.reload_extension("ballsdex.packages.collector")
            else:
                await self.bot.load_extension("ballsdex.packages.collector")
            await update(4)

            from ballsdex.settings import settings
            import asyncio
            await asyncio.gather(
                self.bot.tree.sync(),
                *[self.bot.tree.sync(guild=discord.Object(id=gid)) for gid in settings.admin_guild_ids]
            )
            await update(5)

            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Updated",
                    (
                        "The **Collector Package** has been updated.\n\n"
                        "Restart the admin panel container to apply admin panel changes.\n\n"
                        "Run this installer again to update or remove."
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

# ── Entry point ───────────────────────────────────────────────────────────────

def _is_v3() -> bool:
    """Detect v3 by checking for Django setup and absence of a ready Tortoise ORM."""
    try:
        from django.apps import apps
        apps.check_apps_ready()
        return True
    except Exception:
        pass
    try:
        import tortoise
        return False
    except ImportError:
        pass
    return True

if _is_v3():
    await ctx.send(
        embed=discord.Embed(
            title="Incompatible Version",
            description=(
                "This installer is for **BallsDex v2** only.\n\n"
                "Your instance appears to be running **v3**.\n\n"
                "Please use the **v3 branch** of this package instead, or downgrade "
                "to v2 before installing."
            ),
            color=discord.Color.red(),
        ).set_footer(text=FOOTER)
    )
else:
    installed = is_installed()
    view = CollectorInstallerView(bot, ctx, installed)
    color = discord.Color.gold() if installed else discord.Color.greyple()
    message = await ctx.send(embed=build_main_embed(installed, color), view=view)
    view.message = message
