# 🔴 DANGEROUS EVAL, PROCEED WITH CAUTION.
# REMEMBER THAT IF THE NEW ID ALREADY EXISTS IT WILL BE DELETED AND OVERWRITTEN

.eval
from django.apps import apps

old_id=0xBallIDInCardHere
new_id=0xNewId

if await BallInstance.objects.filter(id=new_id).aexists(): await BallInstance.objects.filter(id=new_id).adelete()

q=BallInstance.objects.filter(id=old_id)
if not await q.aexists(): return f"Unable to change id, asset with id {hex(old_id)} does not exist"

ball=await q.aget()

data={f.attname:getattr(ball,f.attname) for f in ball._meta.concrete_fields if f.name!="id"}

await BallInstance(id=new_id,**data).asave(force_insert=True)

for model in apps.get_models():
 for field in model._meta.fields:
  rel=getattr(field,"related_model",None)
  if rel is BallInstance:
   try: await model.objects.filter(**{field.attname:old_id}).aupdate(**{field.attname:new_id})
   except: pass

await ball.adelete()

return f"Changed {hex(old_id)} -> {hex(new_id)}"
