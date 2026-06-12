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

def _add_list_to_config(key: str, value: str):
    """
    Append a value to a YAML list in config.yml by text manipulation.
    Handles ALL broken formats including corruption from previous failed installs.
    Preserves comments, formatting, and order.
    """
    with open(CONFIG, "r") as f:
        lines = f.readlines()

    # Find the key line
    key_line = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(key + ":"):
            key_line = i
            break

    if key_line is None:
        # Key doesn't exist at all — append at end as proper list
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(f"{key}:\n")
        lines.append(f"  - {value}\n")
        with open(CONFIG, "w") as f:
            f.writelines(lines)
        return

    # Check if value already exists in a list item UNDER THIS KEY
    value_exists = False
    for i in range(key_line + 1, len(lines)):
        line = lines[i]
        if line.strip().startswith("-"):
            if value.strip() in line:
                value_exists = True
                break
        elif line.strip() and not line.strip().startswith("#"):
            # End of list or new key reached
            break

    # Check if key line is CORRUPTED (has value on same line, e.g., "key: null")
    key_content = lines[key_line].strip()
    if key_content != key + ":":
        # Corrupted key line — extract old value and rebuild
        old_value = key_content[len(key) + 1:].strip()
        old_value = old_value.strip('"').strip("'")
        if old_value.lower() in ("null", "none", "~", ""):
            old_value = ""

        new_lines = [f"{key}:\n"]
        if old_value and not value_exists:
            new_lines.append(f"  - {old_value}\n")
        if not value_exists:
            new_lines.append(f"  - {value}\n")
        lines = lines[:key_line] + new_lines + lines[key_line + 1:]
        with open(CONFIG, "w") as f:
            f.writelines(lines)
        return

    # Key line is clean (just "key:"), check if we need to add value
    if value_exists:
        return

    # Add value to the list under this key
    next_idx = key_line + 1

    # If key is at end of file, just append
    if next_idx >= len(lines):
        lines.append(f"  - {value}\n")
        with open(CONFIG, "w") as f:
            f.writelines(lines)
        return

    next_line = lines[next_idx]
    next_stripped = next_line.strip()

    # Check if next line is a NEW TOP-LEVEL KEY (not indented, contains ':')
    # This means the current key has NO value (empty/null)
    if next_stripped and not next_line.startswith(" ") and not next_line.startswith("\t") and ":" in next_stripped:
        # Empty key — insert our list item before the next key
        lines.insert(next_idx, f"  - {value}\n")
        with open(CONFIG, "w") as f:
            f.writelines(lines)
        return

    # Check if it's already a proper list
    if next_stripped.startswith("-"):
        insert_after = key_line
        for i in range(key_line + 1, len(lines)):
            if lines[i].strip().startswith("-"):
                insert_after = i
            elif lines[i].strip() and not lines[i].strip().startswith("#"):
                break
        lines.insert(insert_after + 1, f"  - {value}\n")
        with open(CONFIG, "w") as f:
            f.writelines(lines)
        return

    # Empty line or comment — insert as first list item
    if not next_stripped or next_stripped.startswith("#"):
        lines.insert(next_idx, f"  - {value}\n")
        with open(CONFIG, "w") as f:
            f.writelines(lines)
        return

    # String value on next line — convert to list
    old_value = next_stripped.strip('"').strip("'")
    if old_value.lower() in ("null", "none", "~"):
        old_value = ""
    new_lines = [f"{key}:\n"]
    if old_value:
        new_lines.append(f"  - {old_value}\n")
    new_lines.append(f"  - {value}\n")
    lines = lines[:key_line] + new_lines + lines[next_idx + 1:]

    with open(CONFIG, "w") as f:
        f.writelines(lines)

def _remove_from_config_list(key: str, value: str):
    """Remove a value from a YAML list in config.yml by text manipulation."""
    with open(CONFIG, "r") as f:
        lines = f.readlines()

    # Find the key
    key_line = None
    for i, line in enumerate(lines):
        if line.strip().startswith(key + ":"):
            key_line = i
            break

    if key_line is None:
        return

    # Find and remove the line containing the value
    new_lines = []
    in_list = False
    for i, line in enumerate(lines):
        if i == key_line:
            in_list = True
            new_lines.append(line)
            continue
        if in_list:
            if line.strip().startswith("-"):
                if value.strip() not in line:
                    new_lines.append(line)
                # else: skip this line (remove it)
            elif line.strip() and not line.strip().startswith("#"):
                # List ended
                in_list = False
                new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(CONFIG, "w") as f:
        f.writelines(new_lines)

def add_django_app_to_config():
    """Add collector_admin to extra-django-apps in config.yml."""
    _add_list_to_config("extra-django-apps", "collector_admin")

def add_tortoise_models_to_config():
    """Add collector models to extra-tortoise-models in config.yml."""
    _add_list_to_config("extra-tortoise-models", "ballsdex.packages.collector.models")

def remove_tortoise_models_from_config():
    """Remove collector models from extra-tortoise-models in config.yml."""
    _remove_from_config_list("extra-tortoise-models", "ballsdex.packages.collector.models")

def remove_django_app_from_config():
    """Remove collector_admin from extra-django-apps in config.yml."""
    _remove_from_config_list("extra-django-apps", "collector_admin")

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
