from django.db import models
from django.core.validators import RegexValidator

slash_name_validator = RegexValidator(
    regex=r"^[\w-]{1,32}$",
    message="Command names must be 1–32 characters, lowercase letters, numbers, hyphens or underscores.",
)


class CommandRegistry(models.Model):
    """
    Written by the bot's ReSlasherCog on startup.
    """

    group = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Top-level group name. Empty for top-level ungrouped commands.",
    )
    subgroup = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Nested subgroup name. Empty for 2-word commands.",
    )
    command = models.CharField(
        max_length=32,
        help_text="Leaf command name.",
    )

    class Meta:
        unique_together = [("group", "subgroup", "command")]
        ordering = ["group", "subgroup", "command"]
        verbose_name = "Registered Command"
        verbose_name_plural = "Registered Commands"

    def __str__(self) -> str:
        parts = [p for p in (self.group, self.subgroup, self.command) if p]
        return "/" + " ".join(parts)


class CommandNameOverride(models.Model):
    """
    Stores a custom display name for a single slash command.
    """

    group = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Top-level group name.",
    )
    subgroup = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Nested subgroup name.",
    )
    command = models.CharField(
        max_length=32,
        help_text="Original leaf command name.",
    )
    name = models.CharField(
        max_length=32,
        validators=[slash_name_validator],
        help_text="Override name shown to users in Discord (1–32 chars, a-z 0-9 - _).",
    )

    class Meta:
        unique_together = [("group", "subgroup", "command")]
        ordering = ["group", "subgroup", "command"]
        verbose_name = "Command Name Override"
        verbose_name_plural = "Command Name Overrides"

    def __str__(self) -> str:
        parts = [p for p in (self.group, self.subgroup, self.command) if p]
        return f"/{' '.join(parts)} -> {self.name}"
