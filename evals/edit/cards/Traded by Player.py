# NOTE: This eval requires Player ID, not to be confused with discord user ID.
# To get the Player ID check the view Player ID eval in evals/info/players/Player ID.py

.eval ball=await BallInstance.objects.aget(id=0xBallIDInCardHere); ball.trade_player=await Player.objects.aget(id=PlayerIDHere); await ball.asave()

# Alternative, remove traded by
.eval ball=await BallInstance.objects.aget(id=0xBallIDInCardHere); ball.trade_player=None; await ball.asave()
