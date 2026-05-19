# Broadcast Package
## What is this?
This package creates a command to send messages to all configured spawn channels, DMs or both. It's like the echo package but better? Or worse? Idk

## Guidelines
This package must not be used for the following reasons:
* Advertising (major partnerships are allowed)
* Sending questionable stuff (nothing weird please)
* Spam this command (How to kill your dex speedrun any%)

## How to install
Run this eval

```py
.eval import base64, requests; code = base64.b64decode(requests.get("https://api.github.com/repos/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions/contents/packages/admin/broadcast/installer.py").json()["content"]).decode(); wrapped = "async def __installer(bot, ctx):\n" + "\n".join("    " + l for l in code.splitlines()); globs = {"bot": bot, "ctx": ctx}; exec(wrapped, globs); await globs["__installer"](bot, ctx)
```
 
