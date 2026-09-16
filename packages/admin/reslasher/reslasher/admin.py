"""
ReSlasher admin page
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import CommandNameOverride, CommandRegistry


@admin.register(CommandRegistry)
class CommandRegistryAdmin(admin.ModelAdmin):
    """
    Admin interface for inspecting cataloged commands and viewing active overrides.
    """
    list_display = ("full_path", "group", "subgroup", "command", "active_override")
    search_fields = ("group", "subgroup", "command")
    list_filter = ("group",)

    @admin.display(description="Command Path")
    def full_path(self, obj: CommandRegistry) -> str:
        parts = filter(None, [obj.group, obj.subgroup, obj.command])
        path_str = " / ".join(parts)
        return f"/{path_str}" if path_str else "Root Command"

    @admin.display(description="Active Override")
    def active_override(self, obj: CommandRegistry) -> str:
        override = CommandNameOverride.objects.filter(
            group=obj.group, subgroup=obj.subgroup, command=obj.command
        ).first()
        if override:
            return format_html('<strong style="color: #2e7d32;">{}</strong>', override.name)
        return format_html('<span style="color: #888888;">(Default)</span>')


@admin.register(CommandNameOverride)
class CommandNameOverrideAdmin(admin.ModelAdmin):
    """
    Admin interface for managing custom command name overrides.
    """
    list_display = ("full_target_path", "name")
    search_fields = ("name", "group", "subgroup", "command")
    fields = ("group", "subgroup", "command", "name")

    @admin.display(description="Target Command Path")
    def full_target_path(self, obj: CommandNameOverride) -> str:
        parts = filter(None, [obj.group, obj.subgroup, obj.command])
        path_str = " / ".join(parts)
        return f"/{path_str}" if path_str else "Root Command"
