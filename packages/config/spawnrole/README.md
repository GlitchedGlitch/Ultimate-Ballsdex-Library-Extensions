# Spawnrole Package
## What is this?
This package adds a new command `/config spawnrole` that makes the bot ping a role when a ball spawns. Farms boutta increase
## How to install
Run this eval
```py
.eval import base64, requests; code = base64.b64decode(requests.get("https://api.github.com/repos/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions/contents/packages/config/spawnrole/installer.py?ref=v2-main").json()["content"]).decode(); wrapped = "async def __installer(bot, ctx):\n" + "\n".join("    " + l for l in code.splitlines()); globs = {"bot": bot, "ctx": ctx}; exec(wrapped, globs); await globs["__installer"](bot, ctx)
```
