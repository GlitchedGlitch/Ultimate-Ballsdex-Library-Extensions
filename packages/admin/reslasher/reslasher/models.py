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
        help_text="Parent group name. Empty for top-level ungrouped commands.",
    )
    command = models.CharField(
        max_length=32,
        help_text="Internal command name as registered by the bot.",
    )

    class Meta:
        unique_together = [("group", "command")]
        ordering = ["group", "command"]
        verbose_name = "Registered Command"
        verbose_name_plural = "Registered Commands"

    def __str__(self) -> str:
        return f"/{self.group} {self.command}".strip()


class CommandNameOverride(models.Model):
    """
    Stores a custom display name for a single slash command.
    """

    group = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Parent group name. Empty for top-level ungrouped commands.",
    )
    command = models.CharField(
        max_length=32,
        help_text="Original internal command name as registered by the bot.",
    )
    name = models.CharField(
        max_length=32,
        validators=[slash_name_validator],
        help_text="Override name shown to users in Discord (1–32 chars, a-z 0-9 - _).",
    )

    class Meta:
        unique_together = [("group", "command")]
        ordering = ["group", "command"]
        verbose_name = "Command Name Override"
        verbose_name_plural = "Command Name Overrides"

    def __str__(self) -> str:
        if self.group:
            return f"/{self.group} {self.command} → {self.name}"
        return f"/{self.command} -> {self.name}"
