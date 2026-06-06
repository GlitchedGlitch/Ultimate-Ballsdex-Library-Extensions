from django.contrib import admin

from .models import CollectorClaim, CollectorRequirement


class CollectorClaimInline(admin.TabularInline):
    model = CollectorClaim
    extra = 0
    readonly_fields = ["player", "ball_instance", "claimed_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(CollectorRequirement)
class CollectorRequirementAdmin(admin.ModelAdmin):
    list_display = ["ball", "amount", "special", "claim_count"]
    list_filter = ["special"]
    search_fields = ["ball__country", "special__name"]
    ordering = ["ball__country", "amount"]
    autocomplete_fields = ["ball", "special"]
    inlines = [CollectorClaimInline]

    @admin.display(description="Claims")
    def claim_count(self, obj: CollectorRequirement) -> int:
        return obj.claims.count()


@admin.register(CollectorClaim)
class CollectorClaimAdmin(admin.ModelAdmin):
    list_display = ["player", "requirement", "claimed_at"]
    list_filter = ["requirement__special", "claimed_at"]
    search_fields = ["player__discord_id", "requirement__ball__country"]
    ordering = ["-claimed_at"]
    autocomplete_fields = ["player"]
    readonly_fields = ["claimed_at", "ball_instance"]

    def has_change_permission(self, request, obj=None) -> bool:
        return False
