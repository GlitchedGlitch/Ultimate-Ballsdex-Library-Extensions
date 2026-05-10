# 🔴 DANGEROUS EVAL, PROCEED WITH CAUTION.
# REMEMBER THAT IF THE NEW ID ALREADY EXISTS IT WILL BE DELETED AND OVERWRITTEN

.eval
from tortoise.exceptions import DoesNotExist
from tortoise import Tortoise, connections

old_id=0xBallIDInCardHere
new_id=0xBallIDInCardHere

conn=connections.get("default")

models=Tortoise.apps.get("models",{}).values()

try:
    ball=await BallInstance.get(id=old_id)
except DoesNotExist:
    return f"Ball {hex(old_id)} does not exist"

for model in models:
    for field in model._meta.fields_map.values():
        if getattr(field,"related_model",None)==BallInstance:
            fk=getattr(field,"source_field",None)
            if isinstance(fk,str):
                try:
                    await model.filter(**{fk:new_id}).delete()
                except:
                    pass

try:
    await BallInstance.filter(id=new_id).delete()
except:
    pass

data={}
for field in ball._meta.db_fields:
    if field!="id":
        data[field]=getattr(ball,field)

await BallInstance.create(id=new_id,**data)

for model in models:
    for field in model._meta.fields_map.values():
        if getattr(field,"related_model",None)==BallInstance:
            fk=getattr(field,"source_field",None)
            if isinstance(fk,str):
                try:
                    await model.filter(**{fk:old_id}).update(**{fk:new_id})
                except:
                    pass

await BallInstance.filter(id=old_id).delete()

await conn.execute_query("REINDEX TABLE ballinstance")

return f"Changed {hex(old_id)} into {hex(new_id)}"
