from django.contrib import admin
from django.utils.html import format_html

from collector_admin.models import CollectorClaim, CollectorRequirement


# ── Collector Claims inline (shown inside CollectorRequirement) ───────────────

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
    list_display = ("col_emoji", "ball", "special", "amount", "claim_count")
    list_display_links = ("ball",)
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
                '<img src="https://cdn.discordapp.com/emojis/{}.png?size=32" '
                'style="height:24px;" title="{}"/>',
                obj.ball.emoji_id, obj.ball.country,
            )
        return "—"
    col_emoji.short_description = ""

    def claim_count(self, obj):
        return obj.claims.count()
    claim_count.short_description = "Claims"


# ── CollectorClaim admin ──────────────────────────────────────────────────────

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
    readonly_fields = ("player", "ball_instance", "requirement", "claimed_at")
    ordering = ("-claimed_at",)

    def has_add_permission(self, request):
        return False

    def col_ball_instance(self, obj):
        return str(obj.ball_instance)
    col_ball_instance.short_description = "Ball Instance"

    def col_requirement(self, obj):
        return str(obj.requirement)
    col_requirement.short_description = "Requirement"
