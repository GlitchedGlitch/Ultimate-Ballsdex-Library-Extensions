"""
ReSlasher admin page
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import CommandNameOverride, CommandRegistry


class CommandNameOverrideInline(admin.StackedInline):
    """Allows setting overrides directly from inside a CommandRegistry record."""
    model = CommandNameOverride
    extra = 0
    max_num = 1
    can_delete = True


@admin.register(CommandRegistry)
class CommandRegistryAdmin(admin.ModelAdmin):
    """
    Standard native Django Admin page for inspecting registered commands
    and configuring custom overrides without custom templates.
    """
    list_display = ("full_path", "original_breakdown", "active_override_display")
    search_fields = ("group", "subgroup", "command")
    list_filter = ("group",)
    inlines = [CommandNameOverrideInline]

    @admin.display(description="Command Path")
    def full_path(self, obj: CommandRegistry) -> str:
        parts = filter(None, [obj.group, obj.subgroup, obj.command])
        path_str = " / ".join(parts)
        return f"/{path_str}" if path_str else "Root Command"

    @admin.display(description="Original Path Structure")
    def original_breakdown(self, obj: CommandRegistry) -> str:
        return f"Group: {obj.group or '-'} | Subgroup: {obj.subgroup or '-'} | Cmd: {obj.command or '-'}"

    @admin.display(description="Active Override")
    def active_override_display(self, obj: CommandRegistry) -> str:
        if hasattr(obj, "override") and obj.override:
            return format_html(
                '<strong style="color: #2e7d32;">{}</strong>', 
                obj.override.name
            )
        return format_html('<span style="color: #888888;">(Default)</span>')


@admin.register(CommandNameOverride)
class CommandNameOverrideAdmin(admin.ModelAdmin):
    """Direct model admin for reviewing and editing all custom overrides."""
    list_display = ("target_path", "name")
    search_fields = ("name", "registry__group", "registry__subgroup", "registry__command")
    autocomplete_fields = ("registry",)

    @admin.display(description="Target Command Path", ordering="registry")
    def target_path(self, obj: CommandNameOverride) -> str:
        parts = filter(None, [obj.registry.group, obj.registry.subgroup, obj.registry.command])
        return " / ".join(parts)
