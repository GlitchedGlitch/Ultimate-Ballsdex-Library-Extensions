# Put the discord id of the player in line 4

.eval
player = await Player.objects.filter(discord_id=EnterDiscordIDHere).afirst()
return player.id if player else "Player not found"
