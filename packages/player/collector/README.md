# How to install

Run this eval

.eval import base64, requests; code = base64.b64decode(requests.get("https://api.github.com/repos/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions/contents/packages/player/collector/installer.py").json()["content"]).decode(); wrapped = "async def __installer(bot, ctx):\n" + "\n".join("    " + l for l in code.splitlines()); globs = {"bot": bot, "ctx": ctx}; exec(wrapped, globs); await globs["__installer"](bot, ctx)
