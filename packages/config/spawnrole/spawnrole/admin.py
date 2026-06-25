from django import forms
from django.contrib import admin
from bd_models.admin.guild import GuildAdmin
from bd_models.models import GuildConfig
from .models import SpawnRole

class GuildConfigWithSpawnRoleForm(forms.ModelForm):
    spawn_role = forms.CharField(
        required=False,
        label="Spawn role",
        help_text="Discord role ID that gets mentioned in every spawn",
    )
    
    class Meta:
        model = GuildConfig
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                if hasattr(self.instance, "spawn_role_data") and self.instance.spawn_role_data:
                    self.fields["spawn_role"].initial = str(self.instance.spawn_role_data.role_id)
            except (AttributeError, SpawnRole.DoesNotExist):
                self.fields["spawn_role"].initial = ""
    
    def save(self, commit=True):
        instance = super().save(commit=commit)
        role_id = self.cleaned_data.get("spawn_role")
        
        if role_id:
            try:
                role_id = int(role_id)
                SpawnRole.objects.update_or_create(guild=instance, defaults={"role_id": role_id})
            except (ValueError, TypeError):
                pass
        else:
            SpawnRole.objects.filter(guild=instance).delete()
        
        return instance

GuildAdmin.inlines = tuple(
    inline for inline in getattr(GuildAdmin, "inlines", [])
    if getattr(inline, "model", None) is not SpawnRole
)

def _spawn_role_display(self, obj):
    try:
        if hasattr(obj, "spawn_role_data") and obj.spawn_role_data:
            return str(obj.spawn_role_data.role_id)
    except (AttributeError, SpawnRole.DoesNotExist):
        pass
    return "-"

_spawn_role_display.short_description = "Spawn role"  # type: ignore

GuildAdmin.spawn_role = _spawn_role_display  # type: ignore

GuildAdmin.form = GuildConfigWithSpawnRoleForm

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
