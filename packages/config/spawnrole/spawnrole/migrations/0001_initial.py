from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SpawnRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("guild_id", models.BigIntegerField(
                    unique=True,
                    help_text="Discord guild ID this spawn role applies to.",
                )),
                ("role_id", models.BigIntegerField(
                    help_text="Discord role ID to mention at the end of every spawn message.",
                )),
            ],
            options={
                "verbose_name": "Spawn Role",
                "verbose_name_plural": "Spawn Roles",
            },
        ),
    ]
