# Edit Card Special by name
.eval
ball = await BallInstance.get(id=0xBallIDInCardHere)

special = await Special.get(name="Special Name Here")
ball.special = special

await ball.save()

# Edit card special by special ID
.eval
ball = await BallInstance.get(id=0xBallIDInCardHere)

special = await Special.get(id=IDOfSpecialHere)
ball.special = special

await ball.save()

# Remove Special from card
.eval
ball = await BallInstance.get(id=0xBallIDInCardHere)

ball.special = None

await ball.save()
