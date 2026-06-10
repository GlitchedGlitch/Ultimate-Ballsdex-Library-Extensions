from tortoise import fields
from tortoise.models import Model

class CollectorRequirement(Model):
    id = fields.IntField(pk=True)
    ball = fields.ForeignKeyField("models.Ball", related_name="collector_requirements")
    special = fields.ForeignKeyField("models.Special", related_name="collector_requirements")
    amount = fields.IntField()

    class Meta:
        table = "collector_requirement"

class CollectorClaim(Model):
    id = fields.IntField(pk=True)
    player = fields.ForeignKeyField("models.Player", related_name="collector_claims")
    ball_instance = fields.ForeignKeyField(
        "models.BallInstance", related_name="collector_claim", unique=True
    )
    requirement = fields.ForeignKeyField(
        "models.CollectorRequirement", related_name="claims"
    )
    claimed_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "collector_claim"
