# Edit the catch speed by putting the ball id in the right place
# and the catch speed in milliseconds

.eval
from datetime import timedelta; ball=await BallInstance.objects.aget(id=0xBallIdInCardHere); ball.spawned_time=ball.catch_date-timedelta(milliseconds=TimeInMilliseconds); await ball.asave()
