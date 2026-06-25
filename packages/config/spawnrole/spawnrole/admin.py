from django.contrib import admin
from bd_models.admin.guild import GuildConfigAdmin
from .models import SpawnRole


class SpawnRoleInline(admin.StackedInline):
    model = SpawnRole
    can_delete = False
    verbose_name_plural = "Spawn Role"
    fields = ("role_id",)
    extra = 0

if SpawnRoleInline not in getattr(GuildConfigAdmin, "inlines", []):
    GuildConfigAdmin.inlines = list(getattr(GuildConfigAdmin, "inlines", [])) + [SpawnRoleInline]
