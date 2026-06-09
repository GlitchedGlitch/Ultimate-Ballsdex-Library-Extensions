# Edit card special by name
.eval
ball=await BallInstance.get(id=0xBallIDInCardHere); ball.special=await Special.get(name="SpecialNameHere"); await ball.save() 

# Edit card special by special ID
.eval
ball=await BallInstance.objects.aget(id=0xBallIDInCardHere); ball.special=await Special.objects.aget(id=IDOfSpecialHere); await ball.asave() 

# Remove Special
.eval
ball=await BallInstance.objects.aget(id=0xBallIDInCardHere); ball.special=None; await ball.asave() 
