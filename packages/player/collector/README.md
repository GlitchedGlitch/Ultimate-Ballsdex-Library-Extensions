# Collector Package
## What is this?
This packages creates 2 commands + 3 admin commands for collector balls!
For admins: Set custom amount requirements to obtain a collector ball. The special event of the card is decided by you!
For players: Reach the minimum amount required of a ball to obtain a special version of that ball! You can only redeem once duh

## How to install

Run this eval
```py
.eval import base64, requests; code = base64.b64decode(requests.get("https://api.github.com/repos/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions/contents/packages/player/collector/installer.py?ref=v3").json()["content"]).decode(); wrapped = "async def __installer(bot, ctx):\n" + "\n".join("    " + l for l in code.splitlines()); globs = {"bot": bot, "ctx": ctx}; exec(wrapped, globs); await globs["__installer"](bot, ctx)
```
Or just paste this in config/extra.toml
```toml
# Collector Package
[[ballsdex.packages]]
location = "git+https://github.com/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions.git@v3#subdirectory=packages/player/collector"
path = "collector"
enabled = true
```
