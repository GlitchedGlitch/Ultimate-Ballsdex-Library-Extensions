# Packages
## What is this?
Here you can find all the packages I create for you guys :D
You can find some packages regarding fun, adminn functions, database and more!

## How to download?
You can simply get these packages by either manually downloading the files (not the installer.py, that's used for eval installing) or running the eval installer provided in that package folder.
Alternatively you can run this eval to browse all the packages directly on discord 😋 
```py
.eval
import base64, requests

url = "https://api.github.com/repos/GlitchedGlitch/Ultimate-Ballsdex-Library-Extensions/contents/packages/browser.py?ref=v3"

code = base64.b64decode(
    requests.get(url).json()["content"]
).decode()

wrapped = "async def __run(bot, ctx):\n" + "\n".join(
    "    " + l for l in code.splitlines()
)

globs = {"bot": bot, "ctx": ctx}
exec(wrapped, globs)
await globs["__run"](bot, ctx)
```
