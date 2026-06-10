from django.db import models
from django.utils import timezone

from bd_models.models import Ball, BallInstance, Player, Special


class CollectorRequirement(models.Model):
    """
    A collector requirement: own at least `amount` of `ball` to claim `special`.
    Multiple requirements can exist for the same ball with different specials/amounts.
    """
    ball = models.ForeignKey(
        Ball,
        on_delete=models.CASCADE,
        related_name="collector_requirements",
    )
    special = models.ForeignKey(
        Special,
        on_delete=models.CASCADE,
        related_name="collector_requirements",
    )
    amount = models.PositiveIntegerField(
        help_text="Minimum number of this ball the player must own to claim.",
    )

    class Meta:
        db_table = "collector_requirement"
        unique_together = (("ball", "special"),)
        ordering = ["ball__country", "amount"]
        verbose_name = "Collector Requirement"
        verbose_name_plural = "Collector Requirements"

    def __str__(self) -> str:
        return f"{self.ball.country} — ≥{self.amount} → {self.special.name}"


class CollectorClaim(models.Model):
    """
    Records that a player has claimed a specific collector requirement.
    """
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="collector_claims",
    )
    ball_instance = models.OneToOneField(
        BallInstance,
        on_delete=models.CASCADE,
        related_name="collector_claim",
    )
    requirement = models.ForeignKey(
        CollectorRequirement,
        on_delete=models.CASCADE,
        related_name="claims",
    )
    claimed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "collector_claim"
        ordering = ["-claimed_at"]
        verbose_name = "Collector Claim"
        verbose_name_plural = "Collector Claims"

    def __str__(self) -> str:
        return f"{self.player} claimed {self.requirement}"
