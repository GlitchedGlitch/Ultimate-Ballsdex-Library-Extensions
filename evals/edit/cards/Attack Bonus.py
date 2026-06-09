# Insert the card ID and health bonus

.eval

ball = await BallInstance.get(id=0xBallIDInCardHere)
ball.attack_bonus = InsertAttackBonus
await ball.save() 
