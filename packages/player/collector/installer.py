import base64, os, requests

REPO = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BASE = "https://api.github.com/repos/{}/contents/packages/player/collector/{}".format(REPO, "{}")
PKG = "/code/ballsdex/packages/collector"
CONFIG = "/code/config.yml"
PACKAGE_ENTRY = "  - ballsdex.packages.collector"

os.makedirs(PKG, exist_ok=True)

# Download and write the code files
for f in ("__init__.py", "cog.py"):
    content = base64.b64decode(requests.get(BASE.format(f)).json()["content"]).decode()
    open(os.path.join(PKG, f), "w").write(content)

# Add to config.yml if not already present
with open(CONFIG, "r") as f:
    config = f.read()

if "ballsdex.packages.collector" not in config:
    config = config.replace("packages:", "packages:\n" + PACKAGE_ENTRY)
    with open(CONFIG, "w") as f:
        f.write(config)
    await ctx.send("Added collector to config.yml")
else:
    await ctx.send("Collector already in config.yml, skipping")

# Load or reload the extension
try:
    await bot.load_extension("ballsdex.packages.collector")
    await ctx.send("Collector package installed and loaded!")
except Exception:
    await bot.reload_extension("ballsdex.packages.collector")
    await ctx.send("Collector package updated and reloaded!")
