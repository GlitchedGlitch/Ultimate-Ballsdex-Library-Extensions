from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CommandRegistry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group", models.CharField(blank=True, default="", help_text="Parent group name. Empty for top-level ungrouped commands.", max_length=32)),
                ("command", models.CharField(help_text="Internal command name as registered by the bot.", max_length=32)),
            ],
            options={
                "verbose_name": "Registered Command",
                "verbose_name_plural": "Registered Commands",
                "ordering": ["group", "command"],
                "unique_together": {("group", "command")},
            },
        ),
        migrations.CreateModel(
            name="CommandNameOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group", models.CharField(blank=True, default="", help_text="Parent group name. Empty for top-level ungrouped commands.", max_length=32)),
                ("command", models.CharField(help_text="Original internal command name as registered by the bot.", max_length=32)),
                ("name", models.CharField(
                    help_text="Override name shown to users in Discord (1–32 chars, a-z 0-9 - _).",
                    max_length=32,
                    validators=[django.core.validators.RegexValidator(
                        regex=r"^[\w-]{1,32}$",
                        message="Command names must be 1–32 characters, lowercase letters, numbers, hyphens or underscores.",
                    )],
                )),
            ],
            options={
                "verbose_name": "Command Name Override",
                "verbose_name_plural": "Command Name Overrides",
                "ordering": ["group", "command"],
                "unique_together": {("group", "command")},
            },
        ),
    ]
