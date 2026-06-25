from django.contrib import admin

from .models import SpawnRole


@admin.register(SpawnRole)
class SpawnRoleAdmin(admin.ModelAdmin):
    list_display = ("guild_id", "role_id")
    search_fields = ("guild_id", "role_id")
    ordering = ("guild_id",)
