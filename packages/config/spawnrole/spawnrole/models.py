from django.db import models


class SpawnRole(models.Model):
    """
    Per-guild spawn role configuration
    """

    guild_id = models.BigIntegerField(
        unique=True,
        help_text="Discord guild ID this spawn role applies to.",
    )
    role_id = models.BigIntegerField(
        help_text="Discord role ID to mention at the end of every spawn message.",
    )

    class Meta:
        verbose_name = "Spawn Role"
        verbose_name_plural = "Spawn Roles"

    def __str__(self) -> str:
        return f"Guild {self.guild_id} → Role {self.role_id}"
