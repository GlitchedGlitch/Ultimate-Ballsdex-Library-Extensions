from django.contrib import admin
from bd_models.admin.guild import GuildAdmin
from .models import SpawnRole


class SpawnRoleInline(admin.StackedInline):
    model = SpawnRole
    can_delete = False
    verbose_name_plural = "Spawn Role"
    fields = ("role_id",)
    extra = 0

if SpawnRoleInline not in getattr(GuildAdmin, "inlines", []):
    GuildAdmin.inlines = list(getattr(GuildAdmin, "inlines", [])) + [SpawnRoleInline]
