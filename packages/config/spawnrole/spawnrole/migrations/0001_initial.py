from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("bd_models", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SpawnRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role_id", models.BigIntegerField(help_text="Discord role ID to mention at the end of every spawn message.")),
                ("guild", models.OneToOneField(help_text="The guild this spawn role belongs to.", on_delete=django.db.models.deletion.CASCADE, related_name="spawn_role", to="bd_models.guildconfig")),
            ],
            options={
                "verbose_name": "Spawn Role",
                "verbose_name_plural": "Spawn Roles",
            },
        ),
    ]
