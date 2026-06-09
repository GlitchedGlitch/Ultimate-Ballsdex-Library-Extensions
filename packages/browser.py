"""
Package Browser for Ultimate BallsDex Library Extensions :3333
"""

import base64, io, os, re, traceback
import requests
import discord
from discord.ui import View, Button

REPO   = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BRANCH = "v3"
API    = f"https://api.github.com/repos/{REPO}/contents/{{}}?ref={BRANCH}"
FOOTER = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
TIMEOUT = 300

EXTRA_TOML = "/code/admin_panel/config/extra.toml"


# ── GitHub helpers ────────────────────────────────────────────────────────────

def gh_ls(path: str) -> list[dict]:
    resp = requests.get(API.format(path))
    resp.raise_for_status()
    return resp.json()


def gh_file(path: str) -> str:
    resp = requests.get(API.format(path))
    resp.raise_for_status()
    return base64.b64decode(resp.json()["content"]).decode()


def get_categories() -> list[str]:
    return sorted(i["name"] for i in gh_ls("packages") if i["type"] == "dir")


def get_packages(category: str) -> list[str]:
    items = gh_ls(f"packages/{category}")
    result = []
    for item in items:
        if item["type"] != "dir":
            continue
        sub = gh_ls(f"packages/{category}/{item['name']}")
        if any(f["name"] == "installer.py" for f in sub):
            result.append(item["name"])
    return sorted(result)


def is_installed(pkg: str) -> bool:
    """Check if a package is registered in extra.toml."""
    try:
        if not os.path.isfile(EXTRA_TOML):
            return False
        with open(EXTRA_TOML) as f:
            contents = f.read()
        # Match path = "pkg" anywhere in the file
        return bool(re.search(rf'path\s*=\s*"{re.escape(pkg)}"', contents))
    except OSError:
        return False


# ── Embeds ────────────────────────────────────────────────────────────────────

def root_embed(categories: list[str]) -> discord.Embed:
    lines = [f"• 📁 **{c}**" for c in categories]
    embed = discord.Embed(
        title="Package Browser",
        description=(
            "Browse and install packages for your BallsDex instance.\n\n"
            "**Categories**\n" + "\n".join(lines) + "\n\n"
            "Select a category below to view its packages."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def category_embed(category: str, packages: list[str]) -> discord.Embed:
    lines = [
        f"• {'✅' if is_installed(p) else '❌'} **{p}**"
        for p in packages
    ]
    embed = discord.Embed(
        title=f"📁 {category.capitalize()}",
        description="\n".join(lines) if lines else "No packages found.",
        color=discord.Color.og_blurple(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def timeout_embed(embed: discord.Embed) -> discord.Embed:
    embed.color = discord.Color.dark_grey()
    embed.set_footer(text=FOOTER + " • Timed out")
    return embed


# ── Back button injection ─────────────────────────────────────────────────────

def inject_back_button(view: View, browser: "BrowserView", category: str) -> View:
    back_btn = Button(
        label="Back to list",
        style=discord.ButtonStyle.secondary,
        emoji="↩️",
        row=4,
    )

    async def back_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        browser.locked = False
        await browser.show_category(category)

    back_btn.callback = back_callback
    view.add_item(back_btn)
    return view


# ── Run installer.py in context ───────────────────────────────────────────────

async def run_package_installer(
    browser: "BrowserView",
    category: str,
    pkg: str,
):
    browser.locked = True

    try:
        code = gh_file(f"packages/{category}/{pkg}/installer.py")
    except Exception:
        err = traceback.format_exc()
        f = discord.File(io.BytesIO(err.encode()), filename="fetch_error.txt")
        embed = discord.Embed(
            title="Failed to fetch installer",
            description=f"```\n{err[:1000]}\n```",
            color=discord.Color.red(),
        )
        embed.set_footer(text=FOOTER)
        err_view = View(timeout=None)
        inject_back_button(err_view, browser, category)
        await browser.message.edit(embed=embed, view=err_view)
        await browser.ctx.send(file=f)
        return

    class InterceptCtx:
        """Wraps ctx so installer's `await ctx.send(...)` edits the browser message."""
        author = browser.ctx.author

        async def send(self, *args, **kwargs):
            view = kwargs.get("view")
            embed = kwargs.get("embed")
            if view is not None:
                inject_back_button(view, browser, category)
                view.timeout = None
            await browser.message.edit(embed=embed, view=view)
            return browser.message

    fake_ctx = InterceptCtx()
    globs = {"bot": browser.bot, "ctx": fake_ctx}
    lines = ["async def __installer(bot, ctx):"]
    for line in code.splitlines():
        lines.append("    " + line)
    wrapped = "\n".join(lines)

    try:
        exec(compile(wrapped, f"{pkg}/installer.py", "exec"), globs)
        await globs["__installer"](browser.bot, fake_ctx)
    except Exception:
        err = traceback.format_exc()
        f = discord.File(io.BytesIO(err.encode()), filename="installer_error.txt")
        embed = discord.Embed(
            title="Installer error",
            description=f"```\n{err[:1000]}\n```\nFull error attached.",
            color=discord.Color.red(),
        )
        embed.set_footer(text=FOOTER)
        err_view = View(timeout=None)
        inject_back_button(err_view, browser, category)
        await browser.message.edit(embed=embed, view=err_view)
        await browser.ctx.send(file=f)


# ── Category view ─────────────────────────────────────────────────────────────

class CategoryView(View):
    def __init__(self, browser: "BrowserView", category: str, packages: list[str]):
        super().__init__(timeout=TIMEOUT)
        self.browser  = browser
        self.category = category
        self.packages = packages
        self._build()

    def _build(self):
        self.clear_items()
        for pkg in self.packages:
            emoji = "✅" if is_installed(pkg) else "❌"
            btn = Button(label=pkg, emoji=emoji, style=discord.ButtonStyle.secondary)

            async def cb(interaction: discord.Interaction, p=pkg):
                await interaction.response.defer()
                await run_package_installer(self.browser, self.category, p)

            btn.callback = cb
            self.add_item(btn)

        back_btn = Button(label="Back", style=discord.ButtonStyle.primary, emoji="↩️")
        back_btn.callback = self._back
        self.add_item(back_btn)

    async def _back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.browser.show_root()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.browser.owner_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.browser.locked:
            return
        for c in self.children:
            c.disabled = True
        try:
            await self.browser.message.edit(
                embed=timeout_embed(category_embed(self.category, self.packages)),
                view=self,
            )
        except Exception:
            pass


# ── Root browser view ─────────────────────────────────────────────────────────

class BrowserView(View):
    def __init__(self, bot, ctx, categories: list[str]):
        super().__init__(timeout=TIMEOUT)
        self.bot        = bot
        self.ctx        = ctx
        self.owner_id   = ctx.author.id
        self.categories = categories
        self.message    = None
        self.locked     = False
        self._build()

    def _build(self):
        self.clear_items()
        for cat in self.categories:
            btn = Button(label=cat.capitalize(), emoji="📁", style=discord.ButtonStyle.secondary)

            async def cb(interaction: discord.Interaction, c=cat):
                await interaction.response.defer()
                await self.show_category(c)

            btn.callback = cb
            self.add_item(btn)

        refresh_btn = Button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.primary)
        refresh_btn.callback = self._refresh
        self.add_item(refresh_btn)

    async def _refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            self.categories = get_categories()
            self._build()
            await self.message.edit(embed=root_embed(self.categories), view=self)
        except Exception as e:
            await interaction.followup.send(
                f"Failed to refresh:\n```py\n{e}\n```", ephemeral=True
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.locked:
            return
        for c in self.children:
            c.disabled = True
        try:
            await self.message.edit(
                embed=timeout_embed(root_embed(self.categories)),
                view=self,
            )
        except Exception:
            pass

    async def show_root(self):
        self.locked = False
        self._build()
        await self.message.edit(embed=root_embed(self.categories), view=self)

    async def show_category(self, category: str):
        self.locked = False
        try:
            packages = get_packages(category)
        except Exception as e:
            await self.message.edit(
                embed=discord.Embed(
                    title="Failed to fetch packages",
                    description=f"```py\n{e}\n```",
                    color=discord.Color.red(),
                ),
                view=self,
            )
            return
        view = CategoryView(self, category, packages)
        view.browser.message = self.message
        await self.message.edit(
            embed=category_embed(category, packages),
            view=view,
        )


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
                "This browser menu is for **BallsDex v3** only.\n\n"
                "Your instance appears to be running **v2**.\n\n"
                "Please use the **v2 branch** of the browser instead, or update "
                "to v3 before scrolling."
            ),
            color=discord.Color.red(),
        ).set_footer(text=FOOTER)
    )
else:
    categories = get_categories()
    view = BrowserView(bot, ctx, categories)
    message = await ctx.send(embed=root_embed(categories), view=view)
    view.message = message
