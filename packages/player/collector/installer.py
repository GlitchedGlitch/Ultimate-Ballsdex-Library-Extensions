import base64, os, requests

REPO = "GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions"
BASE = "https://api.github.com/repos/{}/contents/packages/player/collector/{}".format(REPO, "{}")
PKG = os.path.join(os.path.dirname(__file__), "ballsdex", "packages", "collector")

os.makedirs(PKG, exist_ok=True)

for f in ("__init__.py", "cog.py"):
    content = base64.b64decode(requests.get(BASE.format(f)).json()["content"]).decode()
    open(os.path.join(PKG, f), "w").write(content)

await bot.load_extension("ballsdex.packages.collector")
await ctx.send("Collector package installed and loaded!")
