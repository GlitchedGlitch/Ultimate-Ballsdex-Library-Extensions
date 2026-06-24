"""
Spawn Role Package Installer v3 truth :3
"""

import io, os, re, subprocess, traceback, discord
from discord.ui import View, Button

REPO        = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BRANCH      = "v3"
GIT_URL     = f"git+https://github.com/{REPO}.git@{BRANCH}#subdirectory=packages/config/spawnrole"
APP_PATH    = "spawnrole"
TOML_MARKER = f'path = "{APP_PATH}"'
TOML_ENTRY  = (
    "\n\n# Spawn Role Package\n"
    "[[ballsdex.packages]]\n"
    f'location = "{GIT_URL}"\n'
    f'path = "{APP_PATH}"\n'
    "enabled = true"
)

EXTRA_TOML       = "/code/admin_panel/config/extra.toml"
MODELS_PATH      = "/opt/venv/lib/python3.14/site-packages/bd_models/models.py"
GUILD_ADMIN_PATH = "/opt/venv/lib/python3.14/site-packages/bd_models/admin/guild.py"
MIGRATIONS_DIR   = "/opt/venv/lib/python3.14/site-packages/bd_models/migrations"

FOOTER         = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"
BAR_FILLED, BAR_EMPTY, BAR_LEN = "█", "░", 10


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
        r"\n?# Spawn Role Package\n\[\[ballsdex\.packages\]\][^\[]*path\s*=\s*\"spawnrole\"[^\[]*",
        "", contents, flags=re.DOTALL,
    )
    with open(EXTRA_TOML, "w") as f:
        f.write(cleaned)


def is_installed() -> bool:
    return _toml_has_entry()


# ── models.py patching ────────────────────────────────────────────────────────

def patch_models_py():
    """Add spawn_role field to GuildConfig in bd_models/models.py if not already present."""
    if not os.path.isfile(MODELS_PATH):
        raise RuntimeError(
            f"Could not find {MODELS_PATH}.\n\n"
            "This usually means bd_models is installed at a different path in your "
            "image, or this container has no writable access to the venv's site-packages. "
            "Check your docker-compose.yml `develop.watch` target paths and Python version."
        )

    with open(MODELS_PATH, "r") as f:
        content = f.read()
    if "spawn_role" in content:
        return  # already patched

    pattern = (
        r'(class GuildConfig\(models\.Model\):\n'
        r'\s+guild_id = models\.BigIntegerField\(unique=True, help_text="Discord guild ID"\)\n'
        r'\s+spawn_channel = models\.BigIntegerField\(\s*null=True, help_text="Discord channel ID where balls will spawn"\s*\)\n)'
    )
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
            "The core models.py may have changed — manual edit required."
        )
    with open(MODELS_PATH, "w") as f:
        f.write(new_content)


def unpatch_models_py():
    """Remove spawn_role field from GuildConfig in bd_models/models.py."""
    if not os.path.isfile(MODELS_PATH):
        return

    with open(MODELS_PATH, "r") as f:
        content = f.read()
    if "spawn_role" not in content:
        return

    pattern = (
        r'    spawn_role = models\.BigIntegerField\(\n'
        r'        blank=True, null=True,\n'
        r'        help_text="Discord role ID that gets mentioned in every spawn",\n'
        r'    \)\n'
    )
    new_content, count = re.subn(pattern, "", content)
    if count == 0:
        # Fallback: looser pattern in case formatting drifted
        pattern2 = r'\n    spawn_role = models\.BigIntegerField\([^)]*\)\n'
        new_content, count = re.subn(pattern2, "\n", content, count=1)
    if count == 0:
        raise RuntimeError(
            "Could not locate spawn_role field to remove from models.py. Manual edit required."
        )
    with open(MODELS_PATH, "w") as f:
        f.write(new_content)


# ── admin panel patching ──────────────────────────────────────────────────────

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
            "Could not locate GuildAdmin.list_display pattern in admin/guild.py. "
            "Manual edit required."
        )
    with open(GUILD_ADMIN_PATH, "w") as f:
        f.write(new_content)


def unpatch_guild_admin_py():
    """Remove spawn_role from GuildAdmin.list_display."""
    with open(GUILD_ADMIN_PATH, "r") as f:
        content = f.read()
    if "spawn_role" not in content:
        return

    pattern = r'list_display = \("guild_id", "spawn_channel", "spawn_role", "enabled", "silent", "blacklisted"\)'
    replacement = 'list_display = ("guild_id", "spawn_channel", "enabled", "silent", "blacklisted")'
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise RuntimeError(
            "Could not locate spawn_role in list_display to remove. Manual edit required."
        )
    with open(GUILD_ADMIN_PATH, "w") as f:
        f.write(new_content)


# ── Migration generation ──────────────────────────────────────────────────────

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
    """Generate and write the Django migration file with the correct dependency."""
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
    """Run Django migrations for bd_models inside the admin-panel container's environment."""
    result = subprocess.run(
        ["python3", "-m", "django", "migrate", "bd_models", "--no-input"],
        cwd="/code/admin_panel",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Migration failed:\n{result.stdout}\n{result.stderr}")


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
    status = "✅ Registered in `extra.toml` — rebuild to activate" if installed else "❌ Not installed"
    e = discord.Embed(
        title="Spawn Role Package",
        description=(
            "Set a role to be mentioned at the end of every spawn message.\n\n"
            "**Commands**\n"
            "• `/config spawnrole` — set or remove the spawn role\n\n"
            "**Admin Panel**\n"
            "• Adds `spawn_role` to the existing Guild Configs section\n\n"
            "⚠️ This package patches core files (`bd_models/models.py`, "
            "`bd_models/admin/guild.py`) and generates a database migration. "
            "It is more invasive than typical packages.\n\n"
            f"**Status:** {status}"
        ),
        color=color,
    )
    e.set_footer(text=FOOTER)
    return e


def build_warning_embed() -> discord.Embed:
    e = discord.Embed(
        title="⚠️ Before Installing — Required Setup",
        description=(
            "This installer needs to write to `config/extra.toml` and directly "
            "patch `bd_models/models.py` and `bd_models/admin/guild.py` **inside "
            "this bot container's filesystem**.\n\n"
            "⚠️ **Important limitation:** in a typical multi-container setup, "
            "`bot`, `admin-panel`, and `migration` are **separate containers**, "
            "each with their own copy of `bd_models`. A patch applied from inside "
            "the `bot` container only affects that container — it will **not** "
            "automatically reach `admin-panel` or `migration` unless your "
            "`docker-compose.yml` mounts `./admin_panel` as a shared volume "
            "across all three services.\n\n"
            "**Check your `docker-compose.yml`:** if `admin_panel` (or wherever "
            "`bd_models` lives) is only baked into the image and not bind-mounted "
            "from your host into all three services, you'll need to patch it "
            "manually on the host and rebuild, rather than relying on this "
            "installer's runtime patch.\n\n"
            "**If you do have a shared mount**, make sure it and `config`/`extra` "
            "allow write access (`rw`, not `ro`) across all services, then run:\n"
            "```\ndocker compose down\ndocker compose build --no-cache\ndocker compose up -d\n```\n\n"
            "Once ready, click **Confirm Install** below."
        ),
        color=discord.Color.orange(),
    )
    e.set_footer(text=FOOTER)
    return e


def build_confirm_remove_embed() -> discord.Embed:
    e = discord.Embed(
        title="Remove Spawn Role Package",
        description=(
            "⚠️ **Are you sure?**\n\n"
            "This will:\n"
            "• Remove the entry from `config/extra.toml`\n"
            "• Revert the patch to `bd_models/models.py`\n"
            "• Revert the patch to `bd_models/admin/guild.py`\n"
            "• Delete the generated migration file\n\n"
            "The `spawn_role` database column is **kept** to avoid data loss — "
            "rebuild to apply the code reverts."
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


# ── Warning gate ──────────────────────────────────────────────────────────────

class InstallWarningView(View):
    def __init__(self, parent: "SpawnRoleInstallerView"):
        super().__init__(timeout=120)
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

    @discord.ui.button(label="Confirm Install", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        steps = [
            ("Patching bd_models/models.py", None),
            ("Patching admin/guild.py", None),
            ("Writing migration", None),
            ("Running migration", None),
            ("Writing to config/extra.toml", None),
        ]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.parent.message.edit(
                embed=_progress_embed("Installing Spawn Role Package…", steps, discord.Color.blurple()),
                view=None,
            )

        await self.parent.message.edit(
            embed=_progress_embed("Installing Spawn Role Package…", steps, discord.Color.blurple()),
            view=None,
        )

        try:
            patch_models_py()
            await update(0)

            patch_guild_admin_py()
            await update(1)

            write_migration()
            await update(2)

            run_migration()
            await update(3)

            _write_toml()
            await update(4)

            self.parent.installed = True
            self.parent._update_buttons()
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Entry Added — Rebuild Required",
                    "All patches applied and the migration has been run.\n\n"
                    "Now rebuild and restart your bot to finish the install:\n"
                    "```\ndocker compose build --no-cache\ndocker compose up -d\n```\n"
                    "After the rebuild:\n"
                    "• `/config spawnrole` will be available\n"
                    "• Admin panel → Guild Configs will show the Spawn Role column",
                    discord.Color.green(),
                ),
                view=None,
            )
        except OSError as e:
            self.parent.done = True
            self.stop()
            for i, (label, state) in enumerate(steps):
                if state is None:
                    steps[i] = (label, False)
                    break
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Permission Denied",
                    f"Could not write to a required file (`{e.strerror}`).\n\n"
                    "Make sure `docker-compose.yml` mounts are `rw` and the containers "
                    "were restarted:\n"
                    "```\ndocker compose down\ndocker compose build --no-cache\ndocker compose up -d\n```\n"
                    "Then run the installer eval again.",
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
            await self.parent.message.edit(embed=build_error_embed("installing", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="install_error.txt")
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
        await self.parent.message.edit(
            embed=build_main_embed(self.parent.installed, color), view=self.parent
        )


# ── Confirm remove ────────────────────────────────────────────────────────────

class ConfirmRemoveView(View):
    def __init__(self, parent: "SpawnRoleInstallerView"):
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

        steps = [
            ("Removing from config/extra.toml", None),
            ("Reverting models.py patch", None),
            ("Reverting admin/guild.py patch", None),
            ("Deleting migration file", None),
        ]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.parent.message.edit(
                embed=_progress_embed("Removing Spawn Role Package…", steps, discord.Color.red()),
                view=None,
            )

        await self.parent.message.edit(
            embed=_progress_embed("Removing Spawn Role Package…", steps, discord.Color.red()),
            view=None,
        )

        try:
            _remove_toml()
            await update(0)

            unpatch_models_py()
            await update(1)

            unpatch_guild_admin_py()
            await update(2)

            delete_migration()
            await update(3)

            self.parent.installed = False
            self.parent._update_buttons()
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Entry Removed",
                    "All patches reverted and migration file deleted.\n\n"
                    "The `spawn_role` database column was **kept** to avoid data loss.\n\n"
                    "Rebuild to fully apply:\n"
                    "```\ndocker compose build --no-cache\ndocker compose up -d\n```",
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

class SpawnRoleInstallerView(View):
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
        await self.message.edit(embed=build_warning_embed(), view=InstallWarningView(self))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_remove_embed(), view=ConfirmRemoveView(self))


# ── Entry point ───────────────────────────────────────────────────────────────

def _is_v2() -> bool:
    try:
        from django.apps import apps
        apps.check_apps_ready()
        return False
    except Exception:
        pass
    try:
        import tortoise  # noqa: F401
        return True
    except ImportError:
        pass
    return False

if _is_v2():
    await ctx.send(
        embed=discord.Embed(
            title="Incompatible Version",
            description=(
                "This installer is for **BallsDex v3** only.\n\n"
                "Your instance appears to be running **v2**.\n\n"
                "Please use the **v2 branch** of this package instead, or update "
                "to v3 before installing."
            ),
            color=discord.Color.red(),
        ).set_footer(text=FOOTER)
    )
else:
    installed = is_installed()
    view      = SpawnRoleInstallerView(bot, ctx, installed)
    color     = discord.Color.gold() if installed else discord.Color.greyple()
    message   = await ctx.send(embed=build_main_embed(installed, color), view=view)
    view.message = message
