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


def build_command_form(fields_data: list[tuple[str, str, str]]) -> type[forms.Form]:
    """
    Dynamically build a form with one field per leaf command
    """
    fields: dict[str, forms.Field] = {}
    for field_key, current_name, label in fields_data:
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
        groups, flat_fields = self._build_groups()

        form_class = build_command_form(flat_fields)
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

        groups, flat_fields = self._build_groups()
        form_class = build_command_form(flat_fields)
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

        names_by_parent: dict[tuple[str, str], dict[str, tuple]] = {}
        for (g, sg, c), new_name in proposed.items():
            parent = (g, sg)
            if parent not in names_by_parent:
                names_by_parent[parent] = {}

            if new_name in names_by_parent[parent]:
                other = names_by_parent[parent][new_name]
                field_key = f"{g}__{sg}__{c}" if sg else f"{g}__{c}"
                form.add_error(
                    field_key,
                    f"Name '{new_name}' conflicts with {'/'.join(filter(None, other))}"
                )
            names_by_parent[parent][new_name] = (g, sg, c)

        existing: dict[tuple[str, str], set[str]] = {}
        for row in CommandRegistry.objects.all():
            parent = (row.group, row.subgroup)
            if parent not in existing:
                existing[parent] = set()
            override = proposed.get((row.group, row.subgroup, row.command))
            existing[parent].add(override or row.command)

        for (g, sg, c), new_name in proposed.items():
            parent = (g, sg)
            count = sum(1 for name in existing.get(parent, []) if name == new_name)
            if count > 1:
                field_key = f"{g}__{sg}__{c}" if sg else f"{g}__{c}"
                form.add_error(
                    field_key,
                    f"Name '{new_name}' already exists in this group."
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

        parts_msg = []
        if saved:
            parts_msg.append(f"{saved} override(s) saved")
        if cleared:
            parts_msg.append(f"{cleared} reset to default")

        if parts_msg:
            messages.success(request, "Command names updated: " + ", ".join(parts_msg) + ". Run b.reloadtree to apply.")
        else:
            messages.info(request, "No changes made.")

        from django.urls import reverse
        return HttpResponseRedirect(reverse("admin:reslasher_commandnamessettings_changelist"))

    def _build_groups(self) -> tuple[dict[str, list], list[tuple[str, str, str]]]:
        """
        Build display groups and flat field list.
        """
        overrides = {
            (o.group, o.subgroup, o.command): o.name
            for o in CommandNameOverride.objects.all()
        }

        by_subgroup: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
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
            by_subgroup.setdefault(key, []).append((field_key, current, label))

        display_groups: dict[str, list] = {}
        flat_fields: list[tuple[str, str, str]] = []

        for (group, subgroup), cmds in by_subgroup.items():
            if not group:
                display_group = "Top-level Commands"
                section = display_groups.setdefault(display_group, [])
                for field_key, current, label in cmds:
                    section.append({
                        "type": "command",
                        "field_key": field_key,
                        "current": current,
                        "label": label,
                    })
                    flat_fields.append((field_key, current, label))
                continue

            display_group = f"/{group} Group"
            section = display_groups.setdefault(display_group, [])

            if subgroup:
                nested = []
                for field_key, current, label in cmds:
                    nested.append({
                        "type": "command",
                        "field_key": field_key,
                        "current": current,
                        "label": label,
                    })
                    flat_fields.append((field_key, current, label))
                section.append({
                    "type": "header",
                    "name": subgroup.title(),
                    "commands": nested,
                })
            else:
                for field_key, current, label in cmds:
                    section.append({
                        "type": "command",
                        "field_key": field_key,
                        "current": current,
                        "label": label,
                    })
                    flat_fields.append((field_key, current, label))

        return display_groups, flat_fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_module_perms(self, request):
        return True
