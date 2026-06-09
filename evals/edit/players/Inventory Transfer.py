# Put the user id on line 6 and 7

.eval
import asyncio

oldPlayer=await Player.objects.filter(discord_id=OldUserIDHere).afirst()
newPlayer=await Player.objects.filter(discord_id=NewUserIDHere).afirst()

if not oldPlayer or not newPlayer:
 return "One of the players does not exist in the database."

balls=await asyncio.to_thread(lambda:list(BallInstance.objects.filter(player=oldPlayer)))

for ball in balls:
 ball.player=newPlayer
 await ball.asave()

return "Inventory transferred successfully."
