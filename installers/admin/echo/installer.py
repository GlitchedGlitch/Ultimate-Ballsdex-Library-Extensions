# IMPORTANT: Put your admin role id on line 29 and also attach the code txt file with this eval

.eval
content=(await message.attachments[0].read()).decode()
ns={}
exec(content,globals(),ns)

import discord
from discord import app_commands

tree=bot.tree

group=None
for c in tree.get_commands():
    if isinstance(c,app_commands.Group) and c.name=="admin":
        group=c
        break

if not group:
    group=app_commands.Group(name="admin",description="Admin commands")
    tree.add_command(group)

try:
    group.remove_command("echo")
except:
    pass

base=ns["admin_echo_callback"]
ROLE_ID=INPUT ADMIN ROLE ID HERE

async def safe_callback(
    interaction:discord.Interaction,
    message:str=None,
    image:discord.Attachment=None,
    embed:bool=False,
    channel:discord.TextChannel=None,
    edit_message:str=None,
    reply:str=None
):
    try:
        role=interaction.guild.get_role(ROLE_ID)

        if not role or role not in interaction.user.roles:
            return await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )

        return await base(
            interaction,
            message=message,
            image=image,
            embed=embed,
            channel=channel,
            edit_message=edit_message,
            reply=reply
        )

    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Error:\n```py\n{e}\n```",ephemeral=True)
        else:
            await interaction.followup.send(f"Error:\n```py\n{e}\n```",ephemeral=True)

cmd=app_commands.Command(
    name="echo",
    description="Admin echo command",
    callback=safe_callback
)

group.add_command(cmd)

await bot.tree.sync()
if message.guild:
    await bot.tree.sync(guild=message.guild)

return "Database successfully nuked- jkjk admin echo successfully installed :3"
