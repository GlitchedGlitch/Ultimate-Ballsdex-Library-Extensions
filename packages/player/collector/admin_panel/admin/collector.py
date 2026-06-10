from django import forms
from django.contrib import admin
from django.utils.html import format_html

from collector_admin.models import CollectorClaim, CollectorRequirement


# ── Collector Claims inline ───────────────

class CollectorClaimInline(admin.TabularInline):
    model = CollectorClaim
    extra = 0
    readonly_fields = ("player", "ball_instance", "claimed_at")
    fields = ("player", "ball_instance", "claimed_at")
    can_delete = True
    show_change_link = True
    verbose_name = "Claim"
    verbose_name_plural = "Collector Claims"

    def has_add_permission(self, request, obj=None):
        return False


# ── CollectorRequirement admin ────────────────────────────────────────────────

@admin.register(CollectorRequirement)
class CollectorRequirementAdmin(admin.ModelAdmin):
    list_display = ("col_emoji", "col_ball", "amount", "col_special", "claim_count")
    list_display_links = ("col_ball",)
    list_filter = ("special", "ball__enabled")
    search_fields = ("ball__country", "special__name")
    ordering = ("ball__country", "amount")
    autocomplete_fields = ("ball", "special")
    inlines = (CollectorClaimInline,)

    fieldsets = (
        (None, {
            "fields": ("ball", "special", "amount"),
        }),
    )

    def col_emoji(self, obj):
        if obj.ball.emoji_id:
            return format_html(
                '<img src="https://cdn.discordapp.com/emojis/{}.png" width="20" height="20" alt="{}">',
                obj.ball.emoji_id, obj.ball.country
            )
        return "—"
    col_emoji.short_description = ""

    def col_ball(self, obj):
        return obj.ball.country
    col_ball.short_description = "Collectible"

    def col_special(self, obj):
        return obj.special.name
    col_special.short_description = "Reward Special"

    def claim_count(self, obj):
        return obj.claims.count()
    claim_count.short_description = "Claims"


# ── CollectorClaim admin ──────────────────────────────────────────────────────

class CollectorClaimAddForm(forms.ModelForm):
    """Custom form for adding CollectorClaim with dropdowns."""

    class Meta:
        model = CollectorClaim
        fields = ("player", "requirement")


@admin.register(CollectorClaim)
class CollectorClaimAdmin(admin.ModelAdmin):
    list_display = ("player", "col_ball_instance", "col_requirement", "claimed_at")
    list_display_links = ("player",)
    list_filter = ("requirement__ball", "requirement__special", "claimed_at")
    search_fields = (
        "player__discord_id",
        "requirement__ball__country",
        "requirement__special__name",
    )
    readonly_fields = ("ball_instance", "claimed_at")
    ordering = ("-claimed_at",)


    form = CollectorClaimAddForm
    add_form = CollectorClaimAddForm

    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):

        return False

    def has_delete_permission(self, request, obj=None):
        return True

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:

            return ("player", "requirement")

        return ("player", "ball_instance", "requirement", "claimed_at")

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if not change:

            from bd_models.models import BallInstance
            from django.utils import timezone
            req = obj.requirement
            ball_instance = BallInstance.objects.create(
                player=obj.player,
                ball=req.ball,
                special=req.special,
                attack_bonus=0,
                health_bonus=0,
                catch_date=timezone.now(),
                favorite=False,
                tradeable=True,
                server_id=None,
            )
            obj.ball_instance = ball_instance
        super().save_model(request, obj, form, change)

    def col_ball_instance(self, obj):
        return str(obj.ball_instance)
    col_ball_instance.short_description = "Ball Instance"

    def col_requirement(self, obj):
        return str(obj.requirement)
    col_requirement.short_description = "Requirement"
