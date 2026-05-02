# Put the discord id of the player in line 2

.eval
player = await Player.filter(discord_id=DiscordIdHere).first()
return player.id if player else "Player not found"
