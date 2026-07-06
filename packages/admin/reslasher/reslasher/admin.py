"""
ReSlasher admin page
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path

from .models import CommandNameOverride
from .models import CommandRegistry
from django.db import models as dj_models


class CommandNamesSettings(dj_models.Model):
    """Proxy singleton - provides the settings panel entry point."""

    class Meta:
        verbose_name = "Command Names"
        verbose_name_plural = "Command Names"
        managed = False
        app_label = "settings"

def build_command_form(groups: dict[str, list[tuple[str, str]]]) -> type[forms.Form]:
    """
    Dynamically build a form with one field per leaf command
    """
    fields: dict[str, forms.Field] = {}
    for group, cmds in groups.items():
        for cmd_name, current_name in cmds:
            field_key = f"{group}__{cmd_name}" if group else f"__{cmd_name}"
            fields[field_key] = forms.CharField(
                label=cmd_name.replace("_", " ").title(),
                initial=current_name,
                required=False,
                max_length=32,
                widget=forms.TextInput(attrs={"placeholder": cmd_name}),
                help_text=f"Currently: {current_name}",
                validators=[
                    lambda v: re.match(r"^[\w-]{0,32}$", v) or (_ for _ in ()).throw(
                        forms.ValidationError(
                            "Must be 1–32 chars, lowercase letters, numbers, hyphens or underscores."
                        )
                    )
                ],
            )
    form_class = type("CommandNamesForm", (forms.Form,), fields)
    return form_class

@admin.register(CommandNamesSettings)
class CommandNamesAdmin(admin.ModelAdmin):
    """
    Settings page that renders all registered slash commands grouped by their
    parent group, letting admins set a custom display name for each one.
    """

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "command-names/",
                self.admin_site.admin_view(self.command_names_view),
                name="reslasher_commandnamessettings_changelist",
            ),
            path(
                "command-names/save/",
                self.admin_site.admin_view(self.save_names_view),
                name="reslasher_commandnamessettings_change",
            ),
        ]
        return custom + urls

    def changelist_view(self, request: HttpRequest, extra_context=None):
        return self.command_names_view(request)

    def command_names_view(self, request: HttpRequest):
        """Render the command names settings page."""
        groups = _collect_commands()
        overrides = {
            (o.group, o.command): o.name
            for o in CommandNameOverride.objects.all()
        }

        resolved: dict[str, list[tuple[str, str]]] = {}
        for group in sorted(groups.keys()):
            cmds = []
            for cmd_internal in sorted(groups[group]):
                current = overrides.get((group, cmd_internal), cmd_internal)
                cmds.append((cmd_internal, current))
            resolved[group] = cmds

        form_class = build_command_form(resolved)
        form = form_class()

        context = {
            **self.admin_site.each_context(request),
            "title": "Command Names",
            "groups": resolved,
            "form": form,
            "opts": self.model._meta,
            "has_permission": True,
        }
        return render(request, "reslasher/command_names.html", context)

    def save_names_view(self, request: HttpRequest):
        """Handle the form submission and save overrides."""
        if request.method != "POST":
            return HttpResponseRedirect("../")

        groups = _collect_commands()
        overrides = {
            (o.group, o.command): o
            for o in CommandNameOverride.objects.all()
        }

        resolved: dict[str, list[tuple[str, str]]] = {}
        for group in sorted(groups.keys()):
            cmds = []
            for cmd_internal in sorted(groups[group]):
                current_override = overrides.get((group, cmd_internal))
                current = current_override.name if current_override else cmd_internal
                cmds.append((cmd_internal, current))
            resolved[group] = cmds

        form_class = build_command_form(resolved)
        form = form_class(request.POST)

        if not form.is_valid():
            context = {
                **self.admin_site.each_context(request),
                "title": "Command Names",
                "groups": resolved,
                "form": form,
                "opts": self.model._meta,
                "has_permission": True,
            }
            return render(request, "reslasher/command_names.html", context)

        saved = 0
        cleared = 0
        for field_key, value in form.cleaned_data.items():
            if "__" not in field_key:
                continue
            parts = field_key.split("__", 1)
            group, cmd_internal = parts[0], parts[1]
            value = value.strip().lower()

            if not value or value == cmd_internal:
                deleted, _ = CommandNameOverride.objects.filter(
                    group=group, command=cmd_internal
                ).delete()
                if deleted:
                    cleared += 1
            else:
                _, created = CommandNameOverride.objects.update_or_create(
                    group=group,
                    command=cmd_internal,
                    defaults={"name": value},
                )
                saved += 1

        parts = []
        if saved:
            parts.append(f"{saved} override(s) saved")
        if cleared:
            parts.append(f"{cleared} reset to default")
        if parts:
            messages.success(request, "Command names updated: " + ", ".join(parts) + ".")
        else:
            messages.info(request, "No changes made.")

        return HttpResponseRedirect("../")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_module_perms(self, request):
        return True


def _collect_commands() -> dict[str, list[str]]:
    """
    Return { group_name: [cmd_internal_name, ...] } from the CommandRegistry
    """
    
    result: dict[str, list[str]] = {}
    for row in CommandRegistry.objects.all().order_by("group", "command"):
        result.setdefault(row.group, []).append(row.command)
    return result
