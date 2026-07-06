from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reslasher", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="commandregistry",
            name="subgroup",
            field=models.CharField(
                max_length=32,
                blank=True,
                default="",
                help_text="Nested subgroup name. Empty for 2-word commands.",
            ),
        ),
        migrations.AddField(
            model_name="commandnameoverride",
            name="subgroup",
            field=models.CharField(
                max_length=32,
                blank=True,
                default="",
                help_text="Nested subgroup name.",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="commandregistry",
            unique_together={("group", "subgroup", "command")},
        ),
        migrations.AlterUniqueTogether(
            name="commandnameoverride",
            unique_together={("group", "subgroup", "command")},
        ),
        migrations.AlterModelOptions(
            name="commandregistry",
            options={
                "ordering": ["group", "subgroup", "command"],
                "verbose_name": "Registered Command",
                "verbose_name_plural": "Registered Commands",
            },
        ),
        migrations.AlterModelOptions(
            name="commandnameoverride",
            options={
                "ordering": ["group", "subgroup", "command"],
                "verbose_name": "Command Name Override",
                "verbose_name_plural": "Command Name Overrides",
            },
        ),
    ]
