
.eval
import io,zipfile,aiohttp
from discord import File

balls = await Ball.all()

total = len(balls)
msg = await message.channel.send("Starting download...")

buf = io.BytesIO()
z = zipfile.ZipFile(buf,"w")

count = 0
skipped = 0

async with aiohttp.ClientSession() as s:
    for b in balls:
        eid = getattr(b,"emoji_id",None)

        emoji = bot.get_emoji(int(eid)) if eid else None

        if not emoji:
            skipped += 1
            continue

        success = False
        for ext in ("gif","png"):
            url=f"https://cdn.discordapp.com/emojis/{eid}.{ext}?quality=lossless"
            async with s.get(url) as r:
                if r.status==200:
                    z.writestr(f"{b.country}_{eid}.{ext}",await r.read())
                    count+=1
                    success = True
                    break

        if not success:
            skipped += 1

        if (count+skipped)%10==0 or (count+skipped)==total:
            pct=int(((count+skipped)/total)*100)
            txt=f"Downloading emojis... {count}/{total} ({pct}%)"
            if skipped:
                txt+=f" | Skipped {skipped}"
            try: await msg.edit(content=txt)
            except: pass

z.close()
buf.seek(0)

final=f"Downloaded {count} emojis"
if skipped:
    final+=f"\nSkipped {skipped} balls with missing/inaccessible emojis"

await message.channel.send(content=final,file=File(buf,"emojis.zip")) 
