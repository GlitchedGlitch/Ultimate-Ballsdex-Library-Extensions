"""
Admin panel stuff
"""
import json
import os

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from ballsdex.core.models import Ball, Special

from .models import CollectorBall

REQUIREMENTS_FILE = "/code/ballsdex/packages/collector/requirements.txt"


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _load() -> dict:
    if not os.path.isfile(REQUIREMENTS_FILE):
        return {}
    try:
        with open(REQUIREMENTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(REQUIREMENTS_FILE), exist_ok=True)
    with open(REQUIREMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Form ──────────────────────────────────────────────────────────────────────

class CollectorRequirementForm(forms.ModelForm):
    amount = forms.IntegerField(
        min_value=1,
        max_value=9999,
        label="Minimum amount",
        help_text="Minimum number of this ball the player must own to claim the reward.",
    )
    reward_special = forms.ModelChoiceField(
        queryset=Special.objects.all(),
        label="Reward special",
        help_text="The special event applied to the claimed collector ball.",
    )

    class Meta:
        model = CollectorBall
        fields = ("country",)

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        initial = kwargs.setdefault("initial", {})
        if instance and instance.pk:
            req = _load().get(str(instance.pk))
            if req:
                initial.setdefault("amount", req.get("amount", 1))
                try:
                    initial.setdefault(
                        "reward_special",
                        Special.objects.get(pk=req["special_id"]),
                    )
                except Special.DoesNotExist:
                    pass
        super().__init__(*args, **kwargs)


# ── Admin ─────────────────────────────────────────────────────────────────────

@admin.register(CollectorBall)
class CollectorBallAdmin(admin.ModelAdmin):
    form = CollectorRequirementForm
    list_display = ("country", "col_amount", "col_special", "col_emoji")
    list_display_links = ("country",)
    search_fields = ("country",)
    ordering = ("country",)
    fieldsets = (
        (None, {
            "fields": ("country",),
            "description": "Select the ball this requirement applies to.",
        }),
        ("Requirement", {
            "fields": ("amount", "reward_special"),
        }),
    )

    # Only list balls that have a requirement set
    def get_queryset(self, request):
        ids = [int(k) for k in _load().keys()]
        return super().get_queryset(request).filter(pk__in=ids)

    # For the add view show all balls so admin can pick a new one
    def add_view(self, request, form_url="", extra_context=None):
        orig = self.__class__.get_queryset
        self.__class__.get_queryset = lambda s, r: Ball.objects.all()
        resp = super().add_view(request, form_url, extra_context)
        self.__class__.get_queryset = orig
        return resp

    # ── List columns ──────────────────────────────────────────────────────────

    def col_amount(self, obj):
        req = _load().get(str(obj.pk))
        return req["amount"] if req else "—"
    col_amount.short_description = "Min. amount"

    def col_special(self, obj):
        req = _load().get(str(obj.pk))
        if not req:
            return "—"
        try:
            return Special.objects.get(pk=req["special_id"]).name
        except Special.DoesNotExist:
            return f"[deleted] ID {req['special_id']}"
    col_special.short_description = "Reward special"

    def col_emoji(self, obj):
        if obj.emoji_id:
            return format_html(
                '<img src="https://cdn.discordapp.com/emojis/{}.png" '
                'style="height:20px;" title="{}"/>',
                obj.emoji_id,
                obj.country,
            )
        return "—"
    col_emoji.short_description = "Emoji"

    # ── Save / delete — write to JSON file ───────────────────────────────────

    def save_model(self, request, obj, form, change):
        # Don't call super() — we don't want to modify the Ball row itself
        special = form.cleaned_data["reward_special"]
        reqs = _load()
        reqs[str(obj.pk)] = {
            "ball_id": obj.pk,
            "ball_name": obj.country,
            "amount": form.cleaned_data["amount"],
            "special_id": special.pk,
            "special_name": special.name,
        }
        _save(reqs)
        messages.success(
            request,
            f"Collector requirement for {obj.country} saved. "
            "Reload the collector package on the bot to apply changes.",
        )

    def delete_model(self, request, obj):
        reqs = _load()
        reqs.pop(str(obj.pk), None)
        _save(reqs)
        messages.success(request, f"Collector requirement for {obj.country} deleted.")

    def delete_queryset(self, request, queryset):
        reqs = _load()
        for obj in queryset:
            reqs.pop(str(obj.pk), None)
        _save(reqs)
 
