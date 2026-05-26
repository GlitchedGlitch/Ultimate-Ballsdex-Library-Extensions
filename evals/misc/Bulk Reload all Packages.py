.eval
import os

msg = await message.channel.send("Reloading all packages...")

success = []
failed = []

packages_path = "./ballsdex/packages"

for pkg in sorted(os.listdir(packages_path)):
    full = os.path.join(packages_path, pkg)

    if not os.path.isdir(full):
        continue

    if not os.path.exists(os.path.join(full, "__init__.py")):
        continue

    try:
        await bot.reload_extension(f"ballsdex.packages.{pkg}")

        success.append(pkg)

        try:
            await msg.edit(
                content=f"Reloading packages...\n"
                        f"Reloaded: {len(success)}\n"
                        f"Failed: {len(failed)}"
            )
        except:
            pass

    except Exception as e:
        failed.append(f"{pkg} -> {type(e).__name__}: {e}")

txt = ""

if success:
    txt += "Reloaded packages:\n"
    txt += "\n".join(success)

if failed:
    txt += "\n\nFailed packages:\n"
    txt += "\n".join(failed)

if len(txt) > 1900:
    import io
    from discord import File

    buf = io.BytesIO(txt.encode())
    buf.seek(0)

    await message.channel.send(
        f"Reloaded {len(success)} packages\n"
        f"Failed {len(failed)} packages",
        file=File(buf, "reload_results.txt")
    )
else:
    await message.channel.send(
        f"Reloaded {len(success)} packages\n"
        f"Failed {len(failed)} packages\n\n```py\n{txt}\n```"
    )
