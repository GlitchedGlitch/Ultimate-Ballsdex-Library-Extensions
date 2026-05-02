# NOTE: This eval requires Player ID, not to be confused with discord user ID.
# To get the Player ID check the view Player ID eval in evals/view/player/Player ID.py

.eval await BallInstance.get(id=0xBallIDInCardHere).update(trade_player=await Player.get(id=PlayerIDHere))
