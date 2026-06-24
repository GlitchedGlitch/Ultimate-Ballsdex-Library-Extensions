import base64, io, os, re, requests, traceback, textwrap, discord
from discord.ui import View, Button

REPO = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BRANCH = "v2-main"
BASE = f"https://api.github.com/repos/{REPO}/contents/packages/config/spawnrole/{{}}?ref={BRANCH}"
PKG = "/code/ballsdex/packages/spawnrole"
CONFIG = "/code/config.yml"
PACKAGE_ENTRY = "  - ballsdex.packages.spawnrole"
BOT_FILES = ("__init__.py", "cog.py", "spawn_patch.py")

MODELS_PATH = "/code/admin_panel/bd_models/models.py"
GUILD_ADMIN_PATH = "/code/admin_panel/bd_models/admin/guild.py"
MIGRATIONS_DIR = "/code/admin_panel/bd_models/migrations"

FOOTER = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"

BAR_FILLED, BAR_EMPTY, BAR_LEN = "█", "░", 10

def _bar(c, t):
    filled = round(BAR_LEN * c / t)
    return f"`{BAR_FILLED * filled}{BAR_EMPTY * (BAR_LEN - filled)}` {round(100*c/t)}%"

def _progress_embed(title, steps, color):
    done = sum(1 for _, s in steps if s is True)
    lines = []
    for l, s in steps:
        icon = {None: "⬜", True: "✅", False: "❌"}[s]
        lines.append(f"{icon} {l}")
    e = discord.Embed(title=title, description="\n".join(lines) + f"\n\n{_bar(done, len(steps))}", color=color)
    e.set_footer(text=FOOTER)
    return e

def is_installed():
    return os.path.isdir(PKG) and os.path.isfile(os.path.join(PKG, "cog.py"))

def download_bot_files():
    for f in BOT_FILES:
        resp = requests.get(BASE.format(f))
        resp.raise_for_status()
        content = base64.b64decode(resp.json()["content"]).decode()
        with open(os.path.join(PKG, f), "w") as fh:
            fh.write(content)

def add_to_config():
    with open(CONFIG, "r") as f:
        lines = f.readlines()
    if any(PACKAGE_ENTRY.strip() in l for l in lines):
        return
    for i, line in enumerate(lines):
        if "ballsdex.packages.config" in line:
            lines.insert(i + 1, PACKAGE_ENTRY + "\n")
            break
    else:
        for i, line in enumerate(lines):
            if "ballsdex.packages.trade" in line:
                lines.insert(i + 1, PACKAGE_ENTRY + "\n")
                break
    with open(CONFIG, "w") as f:
        f.writelines(lines)

def remove_from_config():
    with open(CONFIG, "r") as f:
        lines = f.readlines()
    lines = [l for l in lines if "ballsdex.packages.spawnrole" not in l]
    with open(CONFIG, "w") as f:
        f.writelines(lines)

def patch_models_py():
    """Add spawn_role field to GuildConfig in bd_models/models.py if not already present."""
    with open(MODELS_PATH, "r") as f:
        content = f.read()
    if "spawn_role" in content:
        return  # already patched
    pattern = r'(class GuildConfig\(models\.Model\):\n\s+guild_id = models\.BigIntegerField\(unique=True, help_text="Discord guild ID"\)\n\s+spawn_channel = models\.BigIntegerField\(\n\s+blank=True, null=True, help_text="Discord channel ID where balls will spawn"\n\s+\)\n)'
    replacement = (
        r'\1    spawn_role = models.BigIntegerField(\n'
        r'        blank=True, null=True,\n'
        r'        help_text="Discord role ID that gets mentioned in every spawn",\n'
        r'    )\n'
    )
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise RuntimeError(
            "Could not locate GuildConfig.spawn_channel field pattern in models.py. "
            "Manual edit required — see INSTRUCTIONS.txt."
        )
    with open(MODELS_PATH, "w") as f:
        f.write(new_content)

def unpatch_models_py():
    """Remove spawn_role field from GuildConfig in bd_models/models.py."""
    with open(MODELS_PATH, "r") as f:
        content = f.read()
    if "spawn_role" not in content:
        return

    pattern = r'    spawn_role = models\.BigIntegerField\(\n        blank=True, null=True,\n        help_text="Discord role ID that gets mentioned in every spawn",\n    \)\n'
    new_content, count = re.subn(pattern, "", content)
    if count == 0:

        pattern2 = r'\n    spawn_role = models\.BigIntegerField\([^)]*\)\n'
        new_content, count = re.subn(pattern2, "\n", content, count=1)
    if count == 0:
        raise RuntimeError(
            "Could not locate spawn_role field to remove from models.py. "
            "Manual edit required."
        )
    with open(MODELS_PATH, "w") as f:
        f.write(new_content)

def patch_guild_admin_py():
    """Add spawn_role to GuildAdmin.list_display if not already present."""
    with open(GUILD_ADMIN_PATH, "r") as f:
        content = f.read()
    if "spawn_role" in content:
        return
    pattern = r'list_display = \("guild_id", "spawn_channel", "enabled", "silent", "blacklisted"\)'
    replacement = 'list_display = ("guild_id", "spawn_channel", "spawn_role", "enabled", "silent", "blacklisted")'
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise RuntimeError(
            "Could not locate GuildAdmin.list_display pattern in guild.py. "
            "Manual edit required — see [MANUAL_INSTRUCTIONS.md](https://github.com/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions/blob/v2-main/packages/config/spawnrole/MANUAL_INSTRUCTIONS.md) in my repo."
        )
    with open(GUILD_ADMIN_PATH, "w") as f:
        f.write(new_content)

def unpatch_guild_admin_py():
    """Remove spawn_role from GuildAdmin.list_display."""
    with open(GUILD_ADMIN_PATH, "r") as f:
        content = f.read()
    if "spawn_role" not in content:
        return  # already clean
    pattern = r'list_display = \("guild_id", "spawn_channel", "spawn_role", "enabled", "silent", "blacklisted"\)'
    replacement = 'list_display = ("guild_id", "spawn_channel", "enabled", "silent", "blacklisted")'
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise RuntimeError(
            "Could not locate spawn_role in list_display to remove from guild.py. "
            "Manual edit required."
        )
    with open(GUILD_ADMIN_PATH, "w") as f:
        f.write(new_content)

def get_last_migration_name() -> str:
    files = [
        f[:-3] for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith(".py") and f != "__init__.py" and not f.startswith("__")
    ]
    if not files:
        raise RuntimeError("No existing migrations found in bd_models/migrations.")
    files.sort()
    return files[-1]

def get_next_migration_filename() -> str:
    files = [
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith(".py") and f != "__init__.py"
    ]
    numbers = []
    for f in files:
        m = re.match(r"^(\d+)_", f)
        if m:
            numbers.append(int(m.group(1)))
    next_num = (max(numbers) + 1) if numbers else 1
    return f"{next_num:04d}_guildconfig_spawn_role.py"

def get_migration_filename() -> str | None:
    """Find the spawn_role migration file if it exists."""
    for f in os.listdir(MIGRATIONS_DIR):
        if f.endswith(".py") and "spawn_role" in f and f != "__init__.py":
            return f
    return None

def write_migration():
    """Generate and write the migration file with the correct dependency."""
    last_migration = get_last_migration_name()
    filename = get_next_migration_filename()
    lines = [
        "from django.db import migrations, models",
        "",
        "",
        "class Migration(migrations.Migration):",
        "",
        "    dependencies = [",
        '        ("bd_models", "%s"),' % last_migration,
        "    ]",
        "",
        "    operations = [",
        "        migrations.AddField(",
        '            model_name="guildconfig",',
        '            name="spawn_role",',
        "            field=models.BigIntegerField(",
        "                blank=True,",
        "                null=True,",
        '                help_text="Discord role ID that gets mentioned in every spawn",',
        "            ),",
        "        ),",
        "    ]",
        "",
    ]
    content = "\n".join(lines)
    path = os.path.join(MIGRATIONS_DIR, filename)
    if os.path.isfile(path):
        return  # already written
    with open(path, "w") as f:
        f.write(content)

def delete_migration():
    """Delete the spawn_role migration file."""
    filename = get_migration_filename()
    if filename:
        path = os.path.join(MIGRATIONS_DIR, filename)
        if os.path.isfile(path):
            os.remove(path)

def run_migration():
    import subprocess
    result = subprocess.run(
        ["python", "manage.py", "migrate", "bd_models"],
        cwd="/code/admin_panel", capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Migration failed:\n{result.stdout}\n{result.stderr}")

def delete_files():
    import shutil
    if os.path.isdir(PKG):
        shutil.rmtree(PKG)

def build_main_embed(installed, color):
    e = discord.Embed(
        title="Spawn Role Package",
        description=(
            "Set a role to be mentioned at the end of every spawn message.\n\n"
            "**Commands**\n"
            "• `/config spawnrole` — set or remove the spawn role\n\n"
            "**Admin Panel**\n"
            "• Adds `spawn_role` to the existing Guild Configs section\n\n"
            f"**Status:** {'✅ Installed' if installed else '❌ Not installed'}"
        ),
        color=color,
    )
    e.set_footer(text=FOOTER)
    return e

def build_confirm_embed():
    e = discord.Embed(
        title="Delete Spawn Role Package",
        description="⚠️ This removes the bot package, config entry, model patches, and migration file.\nThe `spawn_role` database column is **kept** to avoid data loss.",
        color=discord.Color.orange(),
    )
    e.set_footer(text=FOOTER)
    return e

def build_error_embed(action, error):
    short = error[:1000] + "..." if len(error) > 1000 else error
    e = discord.Embed(
        title="An error occurred",
        description=f"An error occurred when **{action}** the package!\n\n```\n{short}\n```\n\nFull error attached below.",
        color=discord.Color.red(),
    )
    e.set_footer(text=FOOTER)
    return e

def build_result_embed(title, desc, color):
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text=FOOTER)
    return e

class ConfirmDeleteView(View):
    def __init__(self, parent):
        super().__init__(timeout=60)
        self.parent = parent

    async def on_timeout(self):
        if not self.parent.done:
            c = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
            await self.parent.message.edit(embed=build_main_embed(self.parent.installed, c), view=self.parent)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.parent.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, delete it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction, button):
        await interaction.response.defer()
        try:
            try:
                await self.parent.bot.unload_extension("ballsdex.packages.spawnrole")
            except Exception:
                pass
            delete_files()
            remove_from_config()
            unpatch_models_py()
            unpatch_guild_admin_py()
            delete_migration()
            self.parent.installed = False
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Successfully Deleted",
                    "Removed bot package, config entry, model patches, and migration file.\nDatabase column kept.",
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
    async def cancel_button(self, interaction, button):
        await interaction.response.defer()
        c = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
        await self.parent.message.edit(embed=build_main_embed(self.parent.installed, c), view=self.parent)

class SpawnRoleInstallerView(View):
    def __init__(self, bot, ctx, installed):
        super().__init__(timeout=180)
        self.bot, self.ctx, self.installed = bot, ctx, installed
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
            e = build_main_embed(self.installed, discord.Color.dark_grey())
            e.set_footer(text=FOOTER_TIMEOUT)
            await self.message.edit(embed=e, view=self)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Install", style=discord.ButtonStyle.success, emoji="📥")
    async def install_button(self, interaction, button):
        await interaction.response.defer()
        STEPS = [
            "Creating package folder", "Downloading bot files", "Adding to config.yml",
            "Patching bd_models/models.py", "Patching guild.py admin",
            "Writing migration", "Running migration",
            "Loading bot extension", "Syncing command tree",
        ]
        steps = [(s, None) for s in STEPS]

        async def update(i, ok=True):
            steps[i] = (steps[i][0], ok)
            await self.message.edit(embed=_progress_embed("Installing Spawn Role…", steps, discord.Color.blurple()), view=None)

        await self.message.edit(embed=_progress_embed("Installing Spawn Role…", steps, discord.Color.blurple()), view=None)
        try:
            os.makedirs(PKG, exist_ok=True); await update(0)
            download_bot_files(); await update(1)
            add_to_config(); await update(2)
            patch_models_py(); await update(3)
            patch_guild_admin_py(); await update(4)
            write_migration(); await update(5)
            run_migration(); await update(6)
            await self.bot.load_extension("ballsdex.packages.spawnrole"); await update(7)

            from ballsdex.settings import settings
            import asyncio
            await asyncio.gather(
                self.bot.tree.sync(),
                *[self.bot.tree.sync(guild=discord.Object(id=g)) for g in settings.admin_guild_ids]
            )
            await update(8)

            self.done = True; self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Successfully Installed",
                    "`/config spawnrole` is ready.\nAdmin panel: Guild Configs now shows Spawn Role.\n\nRestart the admin panel container to see the new column.",
                    discord.Color.green(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.done = True; self.stop()
            for i, (l, s) in enumerate(steps):
                if s is None:
                    steps[i] = (l, False); break
            f = discord.File(io.BytesIO(err.encode()), filename="install_error.txt")
            await self.message.edit(embed=build_error_embed("installing", err), view=None)
            await interaction.followup.send(file=f)

    @discord.ui.button(label="Update", style=discord.ButtonStyle.primary, emoji="🔄")
    async def update_button(self, interaction, button):
        await interaction.response.defer()
        STEPS = ["Downloading latest files", "Reloading extension", "Syncing command tree"]
        steps = [(s, None) for s in STEPS]

        async def update(i, ok=True):
            steps[i] = (steps[i][0], ok)
            await self.message.edit(embed=_progress_embed("Updating Spawn Role…", steps, discord.Color.blurple()), view=None)

        await self.message.edit(embed=_progress_embed("Updating Spawn Role…", steps, discord.Color.blurple()), view=None)
        try:
            download_bot_files(); await update(0)
            loaded = "ballsdex.packages.spawnrole" in self.bot.extensions
            if loaded:
                await self.bot.reload_extension("ballsdex.packages.spawnrole")
            else:
                await self.bot.load_extension("ballsdex.packages.spawnrole")
            await update(1)

            from ballsdex.settings import settings
            import asyncio
            await asyncio.gather(
                self.bot.tree.sync(),
                *[self.bot.tree.sync(guild=discord.Object(id=g)) for g in settings.admin_guild_ids]
            )
            await update(2)

            self.done = True; self.stop()
            await self.message.edit(
                embed=build_result_embed("Successfully Updated", "Package updated and reloaded.", discord.Color.blue()),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.done = True; self.stop()
            for i, (l, s) in enumerate(steps):
                if s is None:
                    steps[i] = (l, False); break
            f = discord.File(io.BytesIO(err.encode()), filename="update_error.txt")
            await self.message.edit(embed=build_error_embed("updating", err), view=None)
            await interaction.followup.send(file=f)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction, button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_embed(), view=ConfirmDeleteView(self))

# ── Entry point ───────────────────────────────────────────────────────────────

def _is_v3() -> bool:
    """Detect v3 by checking for Django setup and absence of a ready Tortoise ORM."""
    try:
        from django.apps import apps
        apps.check_apps_ready()
        return True  # Django is up — this is v3
    except Exception:
        pass
    try:
        import tortoise  # noqa: F401
        return False  # Tortoise present, Django not ready — this is v2
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
    view = SpawnRoleInstallerView(bot, ctx, installed)
    color = discord.Color.gold() if installed else discord.Color.greyple()
    message = await ctx.send(embed=build_main_embed(installed, color), view=view)
    view.message = message
