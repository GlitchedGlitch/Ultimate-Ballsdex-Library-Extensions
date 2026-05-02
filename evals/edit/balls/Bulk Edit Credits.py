# Change the line 8 with the old and new credits,
# you can also put a single name and it only changes that name and not the entire line
# e.g.
# Old name: Glitch ; New name: Stinky
# Old credits: Glitch (spawn) Dingus (card) ; Stinky (spawn) Dingus (card)
# You can put multiple replacement for faster procedure

.eval
import io
from discord import File

replacements = {
    "old name": "new name",
    "old name 2": "new name 2" # (delete this line if you want to change only 1 user credit and the comma on the line above)
}

msg = await message.channel.send("Starting credit update...")

edited = []
count = 0
not_found = set(replacements.keys())

balls = await Ball.all()

for b in balls:
    credits = b.credits or ""
    new_credits = credits

    for old, new in replacements.items():
        if old in new_credits:
            new_credits = new_credits.replace(old, new)
            not_found.discard(old)

    if new_credits != credits:
        b.credits = new_credits
        await b.save()

        entry = f"{b.country} → {credits} → {new_credits}"
        edited.append(entry)
        count += 1

        try:
            await msg.edit(content=f"Updating credits... {count}")
        except:
            pass

if count == 0:
    return "There's no ball with given credits"

buf = io.StringIO("\n".join(edited))
buf.seek(0)

await message.channel.send(
    content=f"Edited {count} balls",
    file=File(io.BytesIO(buf.read().encode()), "edited_credits.txt")
)

if not_found:
    return f"Done. Missing credits: {', '.join(not_found)}"
