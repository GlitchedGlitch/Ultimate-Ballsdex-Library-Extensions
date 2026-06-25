from django.db import models
from bd_models.models import GuildConfig


class SpawnRole(models.Model):
    guild = models.OneToOneField(
        GuildConfig,
        on_delete=models.CASCADE,
        related_name="spawn_role_data",
        help_text="The guild this spawn role belongs to.",
    )
    role_id = models.BigIntegerField(
        help_text="Discord role ID to mention at the end of every spawn message.",
    )

    class Meta:
        verbose_name = "Spawn Role"
        verbose_name_plural = "Spawn Roles"

    def __str__(self) -> str:
        return f"Guild {self.guild.guild_id} → Role {self.role_id}"
