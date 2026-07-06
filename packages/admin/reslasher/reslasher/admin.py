"""
ReSlasher admin page
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path

from .models import CommandNameOverride, CommandRegistry

from django.db import models as dj_models


class CommandNamesSettings(dj_models.Model):
    """Proxy singleton - provides the settings panel entry point."""

    class Meta:
        verbose_name = "Command Names"
        verbose_name_plural = "Command Names"
        managed = False
        app_label = "settings"


def build_command_form(groups: dict[str, list[tuple[str, str, str]]]) -> type[forms.Form]:
    """
    Dynamically build a form with one field per leaf command.
    """
    fields: dict[str, forms.Field] = {}
    for display_group, cmds in groups.items():
        for field_key, current_name, label in cmds:
            fields[field_key] = forms.CharField(
                label=label,
                initial=current_name,
                required=False,
                max_length=32,
                widget=forms.TextInput(attrs={"placeholder": current_name}),
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
                name="reslasher_commandnamessettings_save",
            ),
        ]
        return custom + urls

    def changelist_view(self, request: HttpRequest, extra_context=None):
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect("command-names/")

    def command_names_view(self, request: HttpRequest):
        """Render the command names settings page."""
        groups = self._build_groups()

        form_class = build_command_form(groups)
        form = form_class()

        context = {
            **self.admin_site.each_context(request),
            "title": "Command Names",
            "groups": groups,
            "form": form,
            "opts": self.model._meta,
            "has_permission": True,
        }
        return render(request, "reslasher/command_names.html", context)

    def save_names_view(self, request: HttpRequest):
        """Handle the form submission and save overrides."""
        if request.method != "POST":
            return HttpResponseRedirect("../command-names/")

        groups = self._build_groups()
        form_class = build_command_form(groups)
        form = form_class(request.POST)

        if not form.is_valid():
            context = {
                **self.admin_site.each_context(request),
                "title": "Command Names",
                "groups": groups,
                "form": form,
                "opts": self.model._meta,
                "has_permission": True,
            }
            return render(request, "reslasher/command_names.html", context)

        proposed: dict[tuple[str, str, str], str] = {}
        
        for field_key, value in form.cleaned_data.items():
            parts = field_key.split("__")
            if len(parts) == 3:
                group, subgroup, cmd_internal = parts
            elif len(parts) == 2:
                group, cmd_internal = parts
                subgroup = ""
            else:
                continue
            
            value = value.strip().lower()
            if not value or value == cmd_internal:
                continue
                
            proposed[(group, subgroup, cmd_internal)] = value

        names_by_parent: dict[tuple[str, str], list[str]] = {}
        for (g, sg, c), new_name in proposed.items():
            parent = (g, sg)
            if parent not in names_by_parent:
                names_by_parent[parent] = []
            for other_name in names_by_parent[parent]:
                if other_name == new_name:
                    field_key = f"{g}__{sg}__{c}" if sg else f"{g}__{c}"
                    form.add_error(
                        field_key,
                        f"Name '{new_name}' conflicts with another command in the same group."
                    )
                    break
            else:
                names_by_parent[parent].append(new_name)
                continue
            break

        existing_names: dict[tuple[str, str], set[str]] = {}
        for row in CommandRegistry.objects.all():
            parent = (row.group, row.subgroup)
            if parent not in existing_names:
                existing_names[parent] = set()
            override = proposed.get((row.group, row.subgroup, row.command))
            existing_names[parent].add(override or row.command)

        for (g, sg, c), new_name in proposed.items():
            parent = (g, sg)
            count = sum(1 for name in existing_names.get(parent, []) if name == new_name)
            if count > 1:
                field_key = f"{g}__{sg}__{c}" if sg else f"{g}__{c}"
                form.add_error(
                    field_key,
                    f"Name '{new_name}' already exists in this group. Choose a different name."
                )

        if not form.is_valid():
            context = {
                **self.admin_site.each_context(request),
                "title": "Command Names",
                "groups": groups,
                "form": form,
                "opts": self.model._meta,
                "has_permission": True,
            }
            return render(request, "reslasher/command_names.html", context)

        saved = 0
        cleared = 0
        
        for field_key, value in form.cleaned_data.items():
            parts = field_key.split("__")
            if len(parts) == 3:
                group, subgroup, cmd_internal = parts
            elif len(parts) == 2:
                group, cmd_internal = parts
                subgroup = ""
            else:
                continue

            value = value.strip().lower()

            if not value or value == cmd_internal:
                deleted, _ = CommandNameOverride.objects.filter(
                    group=group, subgroup=subgroup, command=cmd_internal
                ).delete()
                if deleted:
                    cleared += 1
            else:
                _, created = CommandNameOverride.objects.update_or_create(
                    group=group,
                    subgroup=subgroup,
                    command=cmd_internal,
                    defaults={"name": value},
                )
                if not created:
                    saved += 1

        parts = []
        if saved:
            parts.append(f"{saved} override(s) saved")
        if cleared:
            parts.append(f"{cleared} reset to default")
        
        if parts:
            messages.success(request, "Command names updated: " + ", ".join(parts) + ". Restart the bot to apply changes.")
        else:
            messages.info(request, "No changes made.")

        return HttpResponseRedirect("../command-names/")

    def _build_groups(self) -> dict[str, list[tuple[str, str, str, str]]]:
        """
        Build display groups from registry
        """
        overrides = {
            (o.group, o.subgroup, o.command): o.name
            for o in CommandNameOverride.objects.all()
        }

        raw: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
        for row in CommandRegistry.objects.all().order_by("group", "subgroup", "command"):
            key = (row.group, row.subgroup)
            if row.subgroup:
                field_key = f"{row.group}__{row.subgroup}__{row.command}"
                label = f"{row.subgroup.title()} {row.command.title()}"
            elif row.group:
                field_key = f"{row.group}__{row.command}"
                label = row.command.replace("_", " ").title()
            else:
                field_key = f"__{row.command}"
                label = row.command.replace("_", " ").title()

            current = overrides.get((row.group, row.subgroup, row.command), row.command)
            raw.setdefault(key, []).append((field_key, current, label))

        display_groups: dict[str, list[tuple[str, str, str, str]]] = {}
        
        for (group, subgroup), cmds in raw.items():
            if not group:
                display_group = "Top-level Commands"
                for field_key, current, label in cmds:
                    display_groups.setdefault(display_group, []).append(
                        (field_key, current, label, "")
                    )
                continue

            display_group = f"/{group} Group"
            
            if subgroup:
                header = f"{subgroup.title()}"
                for field_key, current, label in cmds:
                    display_groups.setdefault(display_group, []).append(
                        (field_key, current, label, header)
                    )
            else:
                for field_key, current, label in cmds:
                    display_groups.setdefault(display_group, []).append(
                        (field_key, current, label, "")
                    )

        return display_groups

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_module_perms(self, request):
        return True
