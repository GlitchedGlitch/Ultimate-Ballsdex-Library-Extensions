from django import forms
from django.contrib import admin
from bd_models.admin.guild import GuildAdmin
from bd_models.models import GuildConfig
from .models import SpawnRole


class GuildConfigWithSpawnRoleForm(forms.ModelForm):
    """Custom form that includes spawn_role as a native field."""
    
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
                role = self.instance.spawn_role
                self.fields["spawn_role"].initial = str(role.role_id) if role else ""
            except (AttributeError, SpawnRole.DoesNotExist):
                self.fields["spawn_role"].initial = ""
    
    def save(self, commit=True):
        instance = super().save(commit=commit)
        role_id = self.cleaned_data.get("spawn_role")
        if role_id:
            role_id = int(role_id) if role_id else None
        if role_id:
            SpawnRole.objects.update_or_create(guild=instance, defaults={"role_id": role_id})
        else:
            SpawnRole.objects.filter(guild=instance).delete()
        return instance

GuildAdmin.form = GuildConfigWithSpawnRoleForm

if hasattr(GuildAdmin, "fieldsets"):
    new_fieldsets = []
    for title, options in GuildAdmin.fieldsets:
        fields = list(options.get("fields", []))
        if "spawn_channel" in fields and "spawn_role" not in fields:
            idx = fields.index("spawn_channel") + 1
            fields.insert(idx, "spawn_role")
        new_fieldsets.append((title, {**options, "fields": tuple(fields)}))
    GuildAdmin.fieldsets = tuple(new_fieldsets)
else:

    if hasattr(GuildAdmin, "fields"):
        fields = list(GuildAdmin.fields)
        if "spawn_role" not in fields:
            idx = fields.index("spawn_channel") + 1 if "spawn_channel" in fields else len(fields)
            fields.insert(idx, "spawn_role")
        GuildAdmin.fields = tuple(fields)
