# Put the user id on line 6 and 7

.eval
from ballsdex.core.models import Player

oldPlayer = await Player.filter(discord_id=OldUserIDHere).first()
newPlayer = await Player.filter(discord_id=NewUserIDHere).first()

if not oldPlayer or not newPlayer:
    return "One of the players does not exist in the database."

balls = BallInstance.filter(player=oldPlayer)

async for ball in balls:
    ball.player = newPlayer
    await ball.save()

return "Inventory transferred successfully."
