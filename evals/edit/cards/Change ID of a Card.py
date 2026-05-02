# 🔴 DANGEROUS EVAL, PROCEED WITH CAUTION.
# REMEMBER THAT IF THE NEW ID ALREADY EXISTS IT WILL BE DELETED AND OVERWRITTEN

.eval
from tortoise.exceptions import DoesNotExist
from tortoise import Tortoise, connections

old_id = 0xBallIDInCardHere
new_id = 0xBaNewIDHere

conn = connections.get("default")

await conn.execute_query(f"DELETE FROM ballinstance WHERE id = {new_id}")
await conn.execute_query("REINDEX TABLE ballinstance")


try:
    ball = await BallInstance.get(id=old_id)
except DoesNotExist:
    return f"Unable to change id, asset with id {hex(old_id)} does not exist"

data = {}
for field in ball._meta.db_fields:
    if field == "id":
        continue
    data[field] = getattr(ball, field)

await BallInstance.create(id=new_id, **data)

for model in Tortoise.apps.get("models", {}).values():
    for field in model._meta.fields_map.values():
        if getattr(field, "related_model", None) == BallInstance:
            fk_field = getattr(field, "source_field", None)
            if isinstance(fk_field, str):
                try:
                    await model.filter(**{fk_field: old_id}).update(**{fk_field: new_id})
                except:
                    pass
await BallInstance.delete(ball)
print(f"Successfully changed {old_id} into {new_id}!")
