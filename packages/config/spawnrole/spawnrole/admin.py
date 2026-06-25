from django.contrib import admin
from bd_models.admin.guild import GuildAdmin
from bd_models.models import GuildConfig
from .models import SpawnRole

def _get_spawn_role(self):
    try:
        return self.spawn_role_data.role_id
    except (AttributeError, SpawnRole.DoesNotExist):
        return None

def _set_spawn_role(self, value):
    if value is None or value == "":
        SpawnRole.objects.filter(guild=self).delete()
    else:
        try:
            value = int(value)
            SpawnRole.objects.update_or_create(guild=self, defaults={"role_id": value})
        except (ValueError, TypeError):
            pass

if not hasattr(GuildConfig, "_spawn_role_patched"):
    GuildConfig.spawn_role = property(_get_spawn_role, _set_spawn_role)
    GuildConfig._spawn_role_patched = True

GuildAdmin.inlines = tuple(
    inline for inline in getattr(GuildAdmin, "inlines", [])
    if getattr(inline, "model", None) is not SpawnRole
)

GuildAdmin.fieldsets = (
    (None, {
        "fields": (
            "guild_id",
            "spawn_channel",
            "spawn_role",
            "enabled",
            "silent",
        ),
    }),
)

if "spawn_role" not in GuildAdmin.list_display:
    display_list = list(GuildAdmin.list_display)
    if "spawn_channel" in display_list:
        idx = display_list.index("spawn_channel") + 1
        display_list.insert(idx, "spawn_role")
    else:
        display_list.append("spawn_role")
    GuildAdmin.list_display = tuple(display_list)
