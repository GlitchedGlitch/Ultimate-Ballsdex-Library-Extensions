# Note: This eval uses Player ID and not discord user ID!
# To get the player id check evals/info/players/Player ID.py
# Put the player id on line 8 and 9

.eval
from ballsdex.core.models import Player

oldPlayer = await Player.filter(discord_id=OldPlayerIDHere).first()
newPlayer = await Player.filter(discord_id=NewPlayerIDHere).first()

if not oldPlayer or not newPlayer:
    return "One of the players does not exist in the database."

balls = BallInstance.filter(player=oldPlayer)

async for ball in balls:
    ball.player = newPlayer
    await ball.save()

return "Inventory transferred successfully."
