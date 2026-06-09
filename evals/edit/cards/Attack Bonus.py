# Insert your card ID and attack bonus

.eval
ball=await BallInstance.objects.aget(id=0xBallIDInCardHere); ball.attack_bonus=InsertAttackBonus; await ball.asave()
