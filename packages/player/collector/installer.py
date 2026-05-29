"""
Collector Package Installer — BallsDex v3

Instead of writing files to disk (which fails because /code is read-only and
/code/config is permission-denied at runtime), this installer:

  1. Downloads cog.py and __init__.py from GitHub into /tmp/collector_ext/
  2. Injects a minimal fake Django AppConfig into sys.modules so discord.py's
     load_extension() is satisfied without a real pip-installed package
  3. Calls bot.load_extension() on the in-memory module path
  4. Persists requirements to /tmp/collector_requirements.json
     (survives the session; lost on container restart — acceptable for a
      no-console install; console users should use the proper pip method)

On Delete: unloads the extension and removes the injected modules.
On Update:  re-downloads files and reloads.

For a permanent install that survives restarts, add this to config/extra.toml
or ask your hoster:

  [[ballsdex.packages]]
  location = "git+https://github.com/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions.git@v3"
  path = "collector"
  enabled = true
  editable = false
"""

import base64, importlib, importlib.util, io, os, sys, traceback, types, requests, discord
from discord.ui import View, Button

REPO   = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BRANCH = "v3"
RAW    = "https://raw.githubusercontent.com/{}/{}//packages/player/collector/{}".format(
    REPO, BRANCH, "{}"
)
API    = "https://api.github.com/repos/{}/contents/packages/player/collector/{}?ref={}".format(
    REPO, "{}", BRANCH
)

TMP_DIR      = "/tmp/collector_ext"
EXT_MODULE   = "collector_ext"          # name used for load_extension
APP_MODULE   = "collector_app"          # fake Django app module name
REQ_FILE     = "/tmp/collector_requirements.json"

FOOTER         = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"
BAR_FILLED, BAR_EMPTY, BAR_LEN = "█", "░", 10


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _fetch_file(filename: str) -> str:
    """Fetch a file from GitHub via the API (handles LFS / large files)."""
    resp = requests.get(API.format(filename))
    resp.raise_for_status()
    data = resp.json()
    return base64.b64decode(data["content"]).decode()


def _write_tmp(filename: str, content: str) -> str:
    os.makedirs(TMP_DIR, exist_ok=True)
    path = os.path.join(TMP_DIR, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _download_files():
    """Download cog.py and __init__.py into /tmp/collector_ext/."""
    for fname in ("cog.py", "__init__.py"):
        content = _fetch_file(fname)
        _write_tmp(fname, content)
    # Ensure the directory is a package
    init = os.path.join(TMP_DIR, "__init__.py")
    if not os.path.isfile(init):
        open(init, "w").close()


def _inject_fake_app():
    """
    Load collector_ext from /tmp into sys.modules so that
    bot.load_extension("collector_ext") works without a pip-installed package.

    Order matters:
      1. Ensure /tmp and /code are on sys.path so both the package root and
         ballsdex.* imports resolve correctly.
      2. Register empty stub modules for collector_ext AND collector_ext.cog
         BEFORE executing any source, so that the relative import
         `from .cog import ...` inside __init__.py finds a module object
         already in sys.modules instead of triggering a fresh import cycle.
      3. Execute cog.py first (it has no relative imports of its own).
      4. Execute __init__.py last (its `from .cog import ...` now resolves
         against the already-populated collector_ext.cog stub).
    """
    # 1. Path setup
    for p in ("/tmp", "/code"):
        if p not in sys.path:
            sys.path.insert(0, p)

    # 2. Build specs without executing yet
    pkg_spec = importlib.util.spec_from_file_location(
        EXT_MODULE,
        os.path.join(TMP_DIR, "__init__.py"),
        submodule_search_locations=[TMP_DIR],
    )
    cog_spec = importlib.util.spec_from_file_location(
        f"{EXT_MODULE}.cog",
        os.path.join(TMP_DIR, "cog.py"),
    )

    # Create bare module objects and register them immediately
    pkg_mod = importlib.util.module_from_spec(pkg_spec)
    pkg_mod.__path__    = [TMP_DIR]
    pkg_mod.__package__ = EXT_MODULE
    sys.modules[EXT_MODULE] = pkg_mod

    cog_mod = importlib.util.module_from_spec(cog_spec)
    cog_mod.__package__ = EXT_MODULE
    sys.modules[f"{EXT_MODULE}.cog"] = cog_mod

    # 3. Execute cog.py first — no relative imports, safe to run standalone
    cog_spec.loader.exec_module(cog_mod)

    # 4. Execute __init__.py — `from .cog import ...` now hits the cached stub
    pkg_spec.loader.exec_module(pkg_mod)


def _cleanup_modules():
    """Remove injected modules from sys.modules on unload."""
    for key in list(sys.modules):
        if key == EXT_MODULE or key.startswith(f"{EXT_MODULE}."):
            del sys.modules[key]


def is_loaded(bot) -> bool:
    return EXT_MODULE in bot.extensions


# ── Embeds ────────────────────────────────────────────────────────────────────

def build_main_embed(loaded: bool, color: discord.Color) -> discord.Embed:
    status = "✅ Loaded (session only)" if loaded else "❌ Not loaded"
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
            "⚠️ **This installs for the current session only.** "
            "The package will unload when the bot restarts. "
            "For a permanent install, ask your hoster to add it to "
            "`config/extra.toml` as a `git+https://` package."
        ),
        color=color,
    )
    embed.set_footer(text=FOOTER)
    return embed


def build_confirm_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Unload Collector Package",
        description=(
            "⚠️ **Are you sure you want to unload the Collector package?**\n\n"
            "This will unload the commands for this session.\n"
            "No ball instances will be deleted."
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


# ── Confirm unload view ───────────────────────────────────────────────────────

class ConfirmUnloadView(View):
    def __init__(self, parent: "CollectorInstallerView"):
        super().__init__(timeout=60)
        self.parent = parent

    async def on_timeout(self):
        if not self.parent.done:
            color = discord.Color.gold() if self.parent.loaded else discord.Color.greyple()
            await self.parent.message.edit(
                embed=build_main_embed(self.parent.loaded, color), view=self.parent
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, unload it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        try:
            await self.parent.bot.unload_extension(EXT_MODULE)
            _cleanup_modules()
            for attr in ("collector_requirements", "collector_claimed"):
                if hasattr(self.parent.bot, attr):
                    delattr(self.parent.bot, attr)
            self.parent.loaded = False
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Unloaded",
                    (
                        "The **Collector Package** has been unloaded for this session.\n\n"
                        "Run the installer again to reload it."
                    ),
                    discord.Color.red(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(embed=build_error_embed("unloading", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="unload_error.txt")
            )

    @discord.ui.button(label="No, go back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        color = discord.Color.gold() if self.parent.loaded else discord.Color.greyple()
        await self.parent.message.edit(
            embed=build_main_embed(self.parent.loaded, color), view=self.parent
        )


# ── Main installer view ───────────────────────────────────────────────────────

class CollectorInstallerView(View):
    def __init__(self, bot, ctx, loaded: bool):
        super().__init__(timeout=180)
        self.bot    = bot
        self.ctx    = ctx
        self.loaded = loaded
        self.done   = False
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        for c in self.children:
            if c.label == "Load":
                c.disabled = self.loaded
            elif c.label in ("Update", "Unload"):
                c.disabled = not self.loaded

    async def on_timeout(self):
        if self.done:
            return
        for c in self.children:
            c.disabled = True
        if self.message:
            embed = build_main_embed(self.loaded, discord.Color.dark_grey())
            embed.set_footer(text=FOOTER_TIMEOUT)
            await self.message.edit(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Load", style=discord.ButtonStyle.success, emoji="📥")
    async def load_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        steps = [
            ("Downloading files to /tmp", None),
            ("Injecting module into Python", None),
            ("Loading extension", None),
        ]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.message.edit(
                embed=_progress_embed("Loading Collector Package…", steps, discord.Color.blurple()),
                view=None,
            )

        await self.message.edit(
            embed=_progress_embed("Loading Collector Package…", steps, discord.Color.blurple()),
            view=None,
        )

        try:
            _download_files()
            await update(0)

            _inject_fake_app()
            await update(1)

            await self.bot.load_extension(EXT_MODULE)
            await update(2)

            self.loaded = True
            self._update_buttons()
            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Loaded Successfully",
                    (
                        "The **Collector Package** is loaded for this session.\n\n"
                        "You can now use `collector claim`, `collector list` "
                        "and the `admin collector` commands.\n\n"
                        "⚠️ This will unload when the bot restarts. "
                        "For a permanent install, ask your hoster to add:\n"
                        "```toml\n[[ballsdex.packages]]\n"
                        "location = \"git+https://github.com/GlitchedGlitch/"
                        "Ultimate-Ballsdex-Library-Extensions.git@v3\"\n"
                        "path = \"collector\"\nenabled = true\neditable = false\n```\n"
                        "to `config/extra.toml` and rebuild."
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
            await self.message.edit(embed=build_error_embed("loading", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="load_error.txt")
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
            _download_files()
            _cleanup_modules()
            _inject_fake_app()
            await update(0)

            if EXT_MODULE in self.bot.extensions:
                await self.bot.reload_extension(EXT_MODULE)
            else:
                await self.bot.load_extension(EXT_MODULE)
            await update(1)

            self.done = True
            self.stop()
            await self.message.edit(
                embed=build_result_embed(
                    "Updated Successfully",
                    (
                        "The **Collector Package** has been updated and reloaded.\n\n"
                        "All commands are now running the latest version."
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
            await self.message.edit(embed=build_error_embed("updating", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="update_error.txt")
            )

    @discord.ui.button(label="Unload", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def unload_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_embed(), view=ConfirmUnloadView(self))


# ── Entry point ───────────────────────────────────────────────────────────────

loaded = is_loaded(bot)
view   = CollectorInstallerView(bot, ctx, loaded)
color  = discord.Color.gold() if loaded else discord.Color.greyple()
message = await ctx.send(embed=build_main_embed(loaded, color), view=view)
view.message = message
