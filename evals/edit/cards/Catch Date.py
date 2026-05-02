# Put the card ID on line 9 while keeping the 0x
# e.g. 0xD5AB
# Put the timestamp of the date you want on line 10,
# use a discord timestamp generator for this.

.eval
from datetime import datetime

ball = await BallInstance.get(id=0xBallIDInCardHere)
ball.catch_date = datetime.fromtimestamp(TimestampInNumbersHere)
await ball.save()
