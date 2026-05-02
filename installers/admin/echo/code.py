# Download this file as a txt file and attach it to the eval installer

import discord

async def admin_echo_callback(
    interaction: discord.Interaction,
    message: str = None,
    image: discord.Attachment = None,
    embed: bool = False,
    channel: discord.TextChannel = None,
    edit_message: str = None,
    reply: str = None
):

    target_channel = channel or interaction.channel

    files = []
    if image:
        files.append(await image.to_file())

    if message:
        content = message
    elif image:
        content = None
    else:
        content = "Default message: No input provided."

    edit_msg = None
    if edit_message:
        try:
            parts = edit_message.strip().split("/")
            msg_id = int(parts[-1])
            channel_id = int(parts[-2])

            edit_channel = interaction.client.get_channel(channel_id)
            if edit_channel:
                edit_msg = await edit_channel.fetch_message(msg_id)
        except:
            return await interaction.response.send_message(
                "Invalid message edit, make sure you got the correct message link",
                ephemeral=True
            )

    reply_msg = None
    if reply:
        try:
            parts = reply.strip().split("/")
            msg_id = int(parts[-1])
            channel_id = int(parts[-2])

            reply_channel = interaction.client.get_channel(channel_id)
            if reply_channel:
                reply_msg = await reply_channel.fetch_message(msg_id)
        except:
            pass

    try:
        if edit_msg:
            await edit_msg.edit(
                content=content if not embed else None,
                embed=discord.Embed(description=content) if embed and content else None
            )
        else:
            kwargs = {}

            if embed:
                kwargs["embed"] = discord.Embed(description=content or "")
            else:
                if content is not None:
                    kwargs["content"] = content

            if files:
                kwargs["files"] = files

            if reply_msg:
                kwargs["reference"] = reply_msg
                kwargs["mention_author"] = False

            await target_channel.send(**kwargs)

        await interaction.response.send_message("Message sent!", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(
            f"Error:\n```py\n{e}\n```",
            ephemeral=True
        )


cmd = admin_echo_callback
