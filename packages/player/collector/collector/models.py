from django.db import models


class CollectorRequirement(models.Model):
    """
    A single requirement: own at least `amount` of `ball` to claim
    a collector copy with `special` applied.
    Multiple requirements can exist per ball (one per special).
    """

    ball = models.ForeignKey(
        "bd_models.Ball",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name="Collectible",
    )
    special = models.ForeignKey(
        "bd_models.Special",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name="Reward special",
        help_text="The special applied to the claimed collector ball instance.",
    )
    amount = models.PositiveIntegerField(
        help_text="Minimum number of this ball the player must own to claim.",
    )

    class Meta:
        unique_together = [("ball", "special")]
        ordering = ["ball__country", "amount"]
        verbose_name = "Collector Requirement"
        verbose_name_plural = "Collector Requirements"

    def __str__(self) -> str:
        return f"{self.ball.country} ≥{self.amount:,} → {self.special.name}"


class CollectorClaim(models.Model):
    """
    Records that a player has claimed a specific (ball, special) reward.
    Prevents double-claiming. Persists across restarts.
    """

    player = models.ForeignKey(
        "bd_models.Player",
        on_delete=models.CASCADE,
        related_name="collector_claims",
    )
    requirement = models.ForeignKey(
        CollectorRequirement,
        on_delete=models.CASCADE,
        related_name="claims",
    )
    ball_instance = models.OneToOneField(
        "bd_models.BallInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collector_claim",
        help_text="The BallInstance awarded on claim.",
    )
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("player", "requirement")]
        ordering = ["-claimed_at"]
        verbose_name = "Collector Claim"
        verbose_name_plural = "Collector Claims"

    def __str__(self) -> str:
        return f"{self.player} claimed {self.requirement}"
