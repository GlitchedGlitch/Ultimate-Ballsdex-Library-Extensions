from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("bd_models", "0014_alter_ball_options_alter_ballinstance_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectorRequirement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.PositiveIntegerField(help_text="Minimum number of this ball the player must own to claim.")),
                ("ball", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="collector_requirements", to="bd_models.ball", verbose_name="Collectible")),
                ("special", models.ForeignKey(help_text="The special applied to the claimed collector ball instance.", on_delete=django.db.models.deletion.CASCADE, related_name="collector_requirements", to="bd_models.special", verbose_name="Reward special")),
            ],
            options={
                "verbose_name": "Collector Requirement",
                "verbose_name_plural": "Collector Requirements",
                "ordering": ["ball__country", "amount"],
                "unique_together": {("ball", "special")},
            },
        ),
        migrations.CreateModel(
            name="CollectorClaim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("claimed_at", models.DateTimeField(auto_now_add=True)),
                ("ball_instance", models.OneToOneField(blank=True, help_text="The BallInstance awarded on claim.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="collector_claim", to="bd_models.ballinstance")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="collector_claims", to="bd_models.player")),
                ("requirement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="claims", to="collector.collectorrequirement")),
            ],
            options={
                "verbose_name": "Collector Claim",
                "verbose_name_plural": "Collector Claims",
                "ordering": ["-claimed_at"],
                "unique_together": {("player", "requirement")},
            },
        ),
    ]
