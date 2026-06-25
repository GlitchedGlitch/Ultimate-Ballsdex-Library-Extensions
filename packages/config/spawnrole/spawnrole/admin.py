from django.contrib import admin
from bd_models.admin.guild import GuildAdmin
from .models import SpawnRole


class SpawnRoleInline(admin.TabularInline):
    model = SpawnRole
    can_delete = True
    verbose_name_plural = "Spawn Role"
    fields = ("role_id",)
    extra = 0
    max_num = 1
    min_num = 0

if SpawnRoleInline not in getattr(GuildAdmin, "inlines", []):
    GuildAdmin.inlines = list(getattr(GuildAdmin, "inlines", [])) + [SpawnRoleInline]
