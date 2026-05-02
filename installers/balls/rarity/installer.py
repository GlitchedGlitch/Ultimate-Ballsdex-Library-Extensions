# Change your command group name into your commands name
# like "balls" for ballsdex or "tno" for tnodex you get the point

.eval

COMMAND_GROUP_NAME = "balls"
COMMAND_NAME = "rarity"
COMMAND_DESCRIPTION = "Shows the rarity list"

content = (await message.attachments[0].read()).decode()

namespace = {}
exec(content, globals(), namespace)

callback = namespace["rarity_callback"]

from discord import app_commands

tree = bot.tree

group = None
for cmd in tree.get_commands():
    if isinstance(cmd, app_commands.Group) and cmd.name == COMMAND_GROUP_NAME:
        group = cmd
        break

if group is None:
    group = app_commands.Group(
        name=COMMAND_GROUP_NAME,
        description=f"{COMMAND_GROUP_NAME.title()} commands"
    )
    tree.add_command(group)

try:
    group.remove_command(COMMAND_NAME)
except:
    pass

cmd = app_commands.Command(
    name=COMMAND_NAME,
    description=COMMAND_DESCRIPTION,
    callback=callback
)

group.add_command(cmd)

async def rarity_autocomplete(interaction, current: str):
    try:
        balls = await Ball.all()
    except:
        from asgiref.sync import sync_to_async
        balls = await sync_to_async(list)(Ball.objects.all())

    results = []

    for b in balls:
        if not getattr(b, "enabled", True):
            continue

        name = getattr(b, "collectible_name", None) or getattr(b, "country", "Unknown")

        if current.lower() in name.lower():
            results.append(app_commands.Choice(name=name, value=name))

        if len(results) >= 25:
            break

    return results

cmd.autocomplete("search")(rarity_autocomplete)

await tree.sync()
if message.guild:
    await tree.sync(guild=message.guild)

return f"{COMMAND_NAME} command loaded into /{COMMAND_GROUP_NAME}"
