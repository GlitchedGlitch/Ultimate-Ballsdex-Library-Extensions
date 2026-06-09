# Insert the card ID and health bonus

.eval

ball = await BallInstance.get(id=0xBallIDInCardHere)
ball.health_bonus = InsertHealthBonus
await ball.save()
