# NOTE: This eval requires Player ID, not to be confused with discord user ID.
# To get the Player ID check the view Player ID eval in evals/info/players/Player ID.py

.eval await BallInstance.get(id=0xBallIDInCardHere).update(trade_player=await Player.get(id=PlayerIDHere))

# Alternative, remove traded by

.eval
ball = await BallInstance.get(id=0xBallIDInCardHere)
ball.trade_player = None
await ball.save()
