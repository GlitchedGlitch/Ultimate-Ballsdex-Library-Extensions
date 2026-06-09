import json
import os

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from bd_models.models import Ball, Special
from collector_admin.models import CollectorBall

REQUIREMENTS_FILE = "/code/ballsdex/packages/collector/requirements.txt"


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _load() -> dict:
    if not os.path.isfile(REQUIREMENTS_FILE):
        return {}
    try:
        with open(REQUIREMENTS_FILE, "r") as f:
            raw = json.load(f)
        # Normalise: old format had single dict per ball_id, new format has list
        result = {}
        for k, v in raw.items():
            result[str(k)] = [v] if isinstance(v, dict) else v
        return result
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(REQUIREMENTS_FILE), exist_ok=True)
    with open(REQUIREMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _all_reqs() -> list[dict]:
    """Flat list of all requirements across all balls."""
    out = []
    for reqs in _load().values():
        out.extend(reqs)
    return out


# ── Form ──────────────────────────────────────────────────────────────────────

class CollectorRequirementForm(forms.ModelForm):
    """Form shown when adding/editing a collector requirement."""

    amount = forms.IntegerField(
        min_value=1,
        max_value=9999,
        label="Minimum amount",
        help_text="Minimum number of this ball the player must own.",
    )
    reward_special = forms.ModelChoiceField(
        queryset=Special.objects.all(),
        label="Reward special",
        help_text="Special applied to the claimed collector ball.",
    )

    class Meta:
        model = CollectorBall
        fields = ("country",)

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        initial = kwargs.setdefault("initial", {})
        # Pre-fill amount/special when editing an existing requirement
        if instance and instance.pk:
            reqs = _load().get(str(instance.pk), [])
            # If editing via the list view we get the special_id from GET params
            special_id = kwargs.get("data", {}).get("_special_id") if kwargs.get("data") else None
            req = None
            if special_id:
                req = next((r for r in reqs if str(r["special_id"]) == str(special_id)), None)
            if req is None and reqs:
                req = reqs[0]
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


# ── ModelAdmin ────────────────────────────────────────────────────────────────

@admin.register(CollectorBall)
class CollectorBallAdmin(admin.ModelAdmin):
    form = CollectorRequirementForm
    list_display = ("col_emoji", "country", "col_amount", "col_special")
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

    # List view: only show balls that have at least one requirement
    def get_queryset(self, request):
        ids = [int(k) for k in _load().keys()]
        return super().get_queryset(request).filter(pk__in=ids)

    # Add view: show ALL balls so admin can pick a new one
    def add_view(self, request, form_url="", extra_context=None):
        orig = type(self).get_queryset
        type(self).get_queryset = lambda s, r: Ball.objects.all()
        resp = super().add_view(request, form_url, extra_context)
        type(self).get_queryset = orig
        return resp

    # ── List columns ──────────────────────────────────────────────────────────

    def col_emoji(self, obj):
        if obj.emoji_id:
            return format_html(
                '<img src="https://cdn.discordapp.com/emojis/{}.png" '
                'style="height:20px;" title="{}"/>',
                obj.emoji_id, obj.country,
            )
        return "—"
    col_emoji.short_description = ""

    def col_amount(self, obj):
        reqs = _load().get(str(obj.pk), [])
        if not reqs:
            return "—"
        return ", ".join(f"≥{r['amount']}" for r in sorted(reqs, key=lambda r: r["amount"]))
    col_amount.short_description = "Min. amount(s)"

    def col_special(self, obj):
        reqs = _load().get(str(obj.pk), [])
        if not reqs:
            return "—"
        return ", ".join(r["special_name"] for r in sorted(reqs, key=lambda r: r["amount"]))
    col_special.short_description = "Reward special(s)"

    # ── Save: write to requirements.txt ──────────────────────────────────────
    # We do NOT call super().save() — we don't want to touch the Ball row.

    def save_model(self, request, obj, form, change):
        special = form.cleaned_data["reward_special"]
        amount = form.cleaned_data["amount"]
        data = _load()
        key = str(obj.pk)
        reqs = data.setdefault(key, [])

        # Upsert: replace existing entry for same special, otherwise append
        for i, r in enumerate(reqs):
            if r["special_id"] == special.pk:
                reqs[i] = {
                    "ball_id": obj.pk,
                    "ball_name": obj.country,
                    "amount": amount,
                    "special_id": special.pk,
                    "special_name": special.name,
                }
                break
        else:
            reqs.append({
                "ball_id": obj.pk,
                "ball_name": obj.country,
                "amount": amount,
                "special_id": special.pk,
                "special_name": special.name,
            })

        _save(data)
        messages.success(
            request,
            f"Collector requirement for {obj.country} → {special.name} saved. "
            "Reload the collector package on the bot to apply.",
        )

    # ── Delete: remove from requirements.txt ─────────────────────────────────

    def delete_model(self, request, obj):
        data = _load()
        data.pop(str(obj.pk), None)
        _save(data)
        messages.success(request, f"All collector requirements for {obj.country} deleted.")

    def delete_queryset(self, request, queryset):
        data = _load()
        for obj in queryset:
            data.pop(str(obj.pk), None)
        _save(data)
