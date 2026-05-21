"""
Package Browser for my Ultimate BallsDex Library Extensions repo :D
Fetches the package structure live from GitHub.
New packages appear automatically as they are added to the repo.
"""

import asyncio, base64, io, os, traceback
import requests
import discord
from discord.ui import View, Button

REPO    = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BRANCH  = "v2-main"
API     = "https://api.github.com/repos/{}/contents/{}?ref={}".format(REPO, "{}", BRANCH)
RAW     = "https://raw.githubusercontent.com/{}/{}/{}/{}".format(REPO, BRANCH, "{}", "{}")
FOOTER  = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
TIMEOUT = 300  # 5 minutes

# ── Colour helpers ────────────────────────────────────────────────────────────

C_ROOT    = discord.Color.blurple()
C_CAT     = discord.Color.og_blurple()
C_PKG     = discord.Color.gold()
C_INSTALL = discord.Color.green()
C_UPDATE  = discord.Color.blue()
C_DELETE  = discord.Color.red()
C_ERR     = discord.Color.red()
C_TIMEOUT = discord.Color.dark_grey()

BAR_FILLED = "█"
BAR_EMPTY  = "░"
BAR_LEN    = 10


def _bar(current: int, total: int) -> str:
    filled = round(BAR_LEN * current / total)
    pct    = round(100 * current / total)
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


# ── GitHub helpers ────────────────────────────────────────────────────────────

def gh_ls(path: str) -> list[dict]:
    """List contents of a path in the repo."""
    resp = requests.get(API.format(path))
    resp.raise_for_status()
    return resp.json()


def gh_file(path: str) -> str:
    """Fetch and decode a file from the repo."""
    resp = requests.get(API.format(path))
    resp.raise_for_status()
    return base64.b64decode(resp.json()["content"]).decode()


def get_categories() -> list[str]:
    """Return sorted list of category folder names under /packages/."""
    items = gh_ls("packages")
    return sorted(
        i["name"] for i in items
        if i["type"] == "dir"
    )


def get_packages(category: str) -> list[str]:
    """Return sorted list of package folder names that contain installer.py."""
    items = gh_ls(f"packages/{category}")
    result = []
    for item in items:
        if item["type"] != "dir":
            continue
        # Check installer.py exists
        sub = gh_ls(f"packages/{category}/{item['name']}")
        if any(f["name"] == "installer.py" for f in sub):
            result.append(item["name"])
    return sorted(result)


def pkg_install_path(category: str, pkg: str) -> str:
    """The local filesystem path where a package would be installed."""
    return f"/code/ballsdex/packages/{pkg}"


def is_installed(category: str, pkg: str) -> bool:
    path = pkg_install_path(category, pkg)
    return os.path.isdir(path) and os.path.isfile(os.path.join(path, "cog.py"))


def status_emoji(category: str, pkg: str) -> str:
    return "✅" if is_installed(category, pkg) else "❌"


# ── Embeds ────────────────────────────────────────────────────────────────────

def root_embed(categories: list[str]) -> discord.Embed:
    lines = [f"• 📁 **{c}**" for c in categories]
    embed = discord.Embed(
        title="Package Browser",
        description=(
            "Browse and manage packages for your BallsDex instance.\n\n"
            "**Categories**\n" + "\n".join(lines) + "\n\n"
            "Select a category to view its packages."
        ),
        color=C_ROOT,
    )
    embed.set_footer(text=FOOTER)
    return embed


def category_embed(category: str, packages: list[str]) -> discord.Embed:
    lines = [
        f"• {status_emoji(category, p)} **{p}**"
        for p in packages
    ]
    embed = discord.Embed(
        title=f"📁 {category.capitalize()}",
        description="\n".join(lines) if lines else "No packages found in this category.",
        color=C_CAT,
    )
    embed.set_footer(text=FOOTER)
    return embed


def package_embed(category: str, pkg: str) -> discord.Embed:
    installed = is_installed(category, pkg)
    embed = discord.Embed(
        title=f"{'✅' if installed else '❌'} {pkg}",
        description=(
            f"**Category:** {category}\n"
            f"**Status:** {'✅ Installed' if installed else '❌ Not installed'}\n\n"
            f"Use the buttons below to install, update or delete this package."
        ),
        color=C_PKG if installed else discord.Color.greyple(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def error_embed(action: str, error: str) -> discord.Embed:
    short = error[:1000] + "..." if len(error) > 1000 else error
    embed = discord.Embed(
        title="An error occurred",
        description=(
            f"An error occurred when **{action}**!\n\n"
            f"```\n{short}\n```\n\n"
            "The full error is attached as a `.txt` file below."
        ),
        color=C_ERR,
    )
    embed.set_footer(text=FOOTER)
    return embed


def result_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER)
    return embed


# ── Confirm views ─────────────────────────────────────────────────────────────

class ConfirmDeleteView(View):
    def __init__(self, parent: "PackageView"):
        super().__init__(timeout=60)
        self.parent = parent

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.owner_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        # Restore package view
        await self.parent.message.edit(
            embed=package_embed(self.parent.category, self.parent.pkg),
            view=self.parent,
        )

    @discord.ui.button(label="Yes, delete it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def yes(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.parent._do_delete(interaction)

    @discord.ui.button(label="No, go back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def no(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.parent.message.edit(
            embed=package_embed(self.parent.category, self.parent.pkg),
            view=self.parent,
        )


# ── Package view ──────────────────────────────────────────────────────────────

class PackageView(View):
    """Shows install/update/delete buttons for a single package."""

    def __init__(self, browser: "BrowserView", category: str, pkg: str):
        super().__init__(timeout=TIMEOUT)
        self.browser    = browser
        self.category   = category
        self.pkg        = pkg
        self.owner_id   = browser.owner_id
        self.message    = browser.message
        self._refresh_buttons()

    def _refresh_buttons(self):
        self.clear_items()
        installed = is_installed(self.category, self.pkg)

        install_btn = Button(
            label="Install", style=discord.ButtonStyle.success, emoji="📥",
            disabled=installed,
        )
        install_btn.callback = self._install
        self.add_item(install_btn)

        update_btn = Button(
            label="Update", style=discord.ButtonStyle.primary, emoji="🔄",
            disabled=not installed,
        )
        update_btn.callback = self._update
        self.add_item(update_btn)

        delete_btn = Button(
            label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️",
            disabled=not installed,
        )
        delete_btn.callback = self._confirm_delete
        self.add_item(delete_btn)

        back_btn = Button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
        back_btn.callback = self._back
        self.add_item(back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        embed = package_embed(self.category, self.pkg)
        embed.color = C_TIMEOUT
        embed.set_footer(text=FOOTER + " • Timed out")
        try:
            await self.message.edit(embed=embed, view=self)
        except Exception:
            pass

    async def _back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.browser.show_category(self.category)

    async def _confirm_delete(self, interaction: discord.Interaction):
        await interaction.response.defer()
        confirm_embed = discord.Embed(
            title=f"Delete {self.pkg}?",
            description=(
                f"⚠️ Are you sure you want to delete **{self.pkg}**?\n\n"
                "This will unload, delete files and remove from `config.yml`.\n"
                "This cannot be undone without reinstalling."
            ),
            color=discord.Color.orange(),
        )
        confirm_embed.set_footer(text=FOOTER)
        await self.message.edit(embed=confirm_embed, view=ConfirmDeleteView(self))

    async def _run_installer(self, interaction: discord.Interaction, action: str):
        """
        Fetch installer.py from GitHub and execute the requested action
        (install / update / delete) using its helper functions directly.
        """
        try:
            code = gh_file(f"packages/{self.category}/{self.pkg}/installer.py")
        except Exception:
            err = traceback.format_exc()
            f = io.BytesIO(err.encode())
            await self.message.edit(embed=error_embed("fetching installer", err), view=None)
            await interaction.followup.send(
                file=discord.File(f, filename="fetch_error.txt")
            )
            return

        # Execute installer module in an isolated namespace
        ns: dict = {"bot": self.browser.bot, "ctx": self.browser.ctx}
        try:
            exec(compile(code, f"{self.pkg}/installer.py", "exec"), ns)
        except Exception:
            pass  # installer module sets up functions; top-level ctx.send is skipped

        pkg_name = f"ballsdex.packages.{self.pkg}"

        if action == "install":
            STEPS = [
                "Fetching installer",
                "Creating package folder",
                "Downloading files",
                "Adding to config.yml",
                "Loading extension",
                "Syncing command tree",
            ]
        elif action == "update":
            STEPS = [
                "Fetching installer",
                "Downloading latest files",
                "Reloading extension",
                "Syncing command tree",
            ]
        else:  # delete
            STEPS = [
                "Fetching installer",
                "Unloading extension",
                "Syncing command tree",
                "Deleting package files",
                "Removing from config.yml",
            ]

        steps = [(s, None) for s in STEPS]
        color_map = {"install": C_INSTALL, "update": C_UPDATE, "delete": C_DELETE}
        title_map = {
            "install": f"Installing {self.pkg}…",
            "update":  f"Updating {self.pkg}…",
            "delete":  f"Deleting {self.pkg}…",
        }

        async def upd(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.message.edit(
                embed=_progress_embed(title_map[action], steps, discord.Color.blurple()),
                view=None,
            )

        await self.message.edit(
            embed=_progress_embed(title_map[action], steps, discord.Color.blurple()),
            view=None,
        )

        try:
            # Step 0 — installer fetched (already done above)
            await upd(0)

            if action == "install":
                import importlib, asyncio as _asyncio
                os.makedirs(f"/code/ballsdex/packages/{self.pkg}", exist_ok=True)
                await upd(1)
                ns["download_files"]()
                await upd(2)
                if "ensure_requirements_file" in ns:
                    ns["ensure_requirements_file"]()
                ns["add_to_config"]()
                await upd(3)
                await self.browser.bot.load_extension(pkg_name)
                await upd(4)
                await self._sync(upd, 5)

            elif action == "update":
                ns["download_files"]()
                await upd(1)
                loaded = pkg_name in self.browser.bot.extensions
                if loaded:
                    await self.browser.bot.reload_extension(pkg_name)
                else:
                    await self.browser.bot.load_extension(pkg_name)
                await upd(2)
                await self._sync(upd, 3)

            else:  # delete
                # Remove command from admin/balls group if installer exposes helper
                if "remove_command" in ns:
                    try:
                        ns["remove_command"]()
                    except Exception:
                        pass
                try:
                    await self.browser.bot.unload_extension(pkg_name)
                except Exception:
                    pass
                await upd(1)
                await self._sync(upd, 2)
                ns["delete_files"]()
                await upd(3)
                ns["remove_from_config"]()
                await upd(4)

            result_map = {
                "install": ("Successfully Installed", f"**{self.pkg}** has been installed.", C_INSTALL),
                "update":  ("Successfully Updated",  f"**{self.pkg}** has been updated.",   C_UPDATE),
                "delete":  ("Successfully Deleted",  f"**{self.pkg}** has been removed.",   C_DELETE),
            }
            title, desc, color = result_map[action]
            self._refresh_buttons()
            await self.message.edit(
                embed=result_embed(title, desc + "\n\nPress **Back** to return to the package list.", color),
                view=self,
            )

        except Exception:
            err = traceback.format_exc()
            for i, (label, state) in enumerate(steps):
                if state is None:
                    steps[i] = (label, False)
                    break
            f = io.BytesIO(err.encode())
            self._refresh_buttons()
            await self.message.edit(embed=error_embed(action + "ing", err), view=self)
            await interaction.followup.send(
                file=discord.File(f, filename=f"{action}_error.txt")
            )

    async def _sync(self, upd, step: int):
        from ballsdex.settings import settings
        guild_syncs = [
            self.browser.bot.tree.sync(guild=discord.Object(id=gid))
            for gid in settings.admin_guild_ids
        ]
        await asyncio.gather(self.browser.bot.tree.sync(), *guild_syncs)
        await upd(step)

    async def _install(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._run_installer(interaction, "install")

    async def _update(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._run_installer(interaction, "update")

    async def _do_delete(self, interaction: discord.Interaction):
        await self._run_installer(interaction, "delete")


# ── Category view ─────────────────────────────────────────────────────────────

class CategoryView(View):
    """Shows buttons for each package in a category."""

    def __init__(self, browser: "BrowserView", category: str, packages: list[str]):
        super().__init__(timeout=TIMEOUT)
        self.browser   = browser
        self.category  = category
        self.packages  = packages
        self.owner_id  = browser.owner_id
        self.message   = browser.message
        self._build()

    def _build(self):
        self.clear_items()
        for pkg in self.packages:
            emoji = "✅" if is_installed(self.category, pkg) else "📥"
            btn = Button(
                label=pkg,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
            )
            # Capture pkg in closure
            async def callback(interaction: discord.Interaction, p=pkg):
                await interaction.response.defer()
                view = PackageView(self.browser, self.category, p)
                view.message = self.message
                await self.message.edit(
                    embed=package_embed(self.category, p),
                    view=view,
                )
            btn.callback = callback
            self.add_item(btn)

        back_btn = Button(label="Back", style=discord.ButtonStyle.primary, emoji="↩️")
        back_btn.callback = self._back
        self.add_item(back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        embed = category_embed(self.category, self.packages)
        embed.color = C_TIMEOUT
        embed.set_footer(text=FOOTER + " • Timed out")
        try:
            await self.message.edit(embed=embed, view=self)
        except Exception:
            pass

    async def _back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.browser.show_root()


# ── Root browser view ─────────────────────────────────────────────────────────

class BrowserView(View):
    """Root view — shows category folder buttons."""

    def __init__(self, bot, ctx, categories: list[str]):
        super().__init__(timeout=TIMEOUT)
        self.bot        = bot
        self.ctx        = ctx
        self.owner_id   = ctx.author.id
        self.categories = categories
        self.message    = None
        self._build()

    def _build(self):
        self.clear_items()
        for cat in self.categories:
            btn = Button(
                label=cat.capitalize(),
                emoji="📁",
                style=discord.ButtonStyle.secondary,
            )
            async def callback(interaction: discord.Interaction, c=cat):
                await interaction.response.defer()
                await self.show_category(c)
            btn.callback = callback
            self.add_item(btn)

        refresh_btn = Button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.primary)
        refresh_btn.callback = self._refresh
        self.add_item(refresh_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        embed = root_embed(self.categories)
        embed.color = C_TIMEOUT
        embed.set_footer(text=FOOTER + " • Timed out")
        try:
            await self.message.edit(embed=embed, view=self)
        except Exception:
            pass

    async def _refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            self.categories = get_categories()
            self._build()
            await self.message.edit(embed=root_embed(self.categories), view=self)
        except Exception as e:
            await interaction.followup.send(f"Failed to refresh: ```py\n{e}\n```", ephemeral=True)

    async def show_root(self):
        self._build()
        await self.message.edit(embed=root_embed(self.categories), view=self)

    async def show_category(self, category: str):
        try:
            packages = get_packages(category)
        except Exception as e:
            await self.message.edit(
                embed=error_embed("fetching packages", str(e)),
                view=self,
            )
            return
        view = CategoryView(self, category, packages)
        view.message = self.message
        await self.message.edit(embed=category_embed(category, packages), view=view)


# ── Entry point ───────────────────────────────────────────────────────────────

try:
    categories = get_categories()
except Exception as e:
    await ctx.send(f"Failed to fetch package list from GitHub:\n```py\n{e}\n```")
else:
    view = BrowserView(bot, ctx, categories)
    message = await ctx.send(embed=root_embed(categories), view=view)
    view.message = message
 
