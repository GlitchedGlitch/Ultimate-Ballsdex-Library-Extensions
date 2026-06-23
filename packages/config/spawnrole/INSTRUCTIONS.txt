MANUAL EDITS REQUIRED IN bd_models (run once, then never touch again)
======================================================================

1. admin_panel/bd_models/models.py
   Find the GuildConfig class and add this line inside it:

       spawn_role = models.BigIntegerField(
           blank=True, null=True,
           help_text="Discord role ID that gets mentioned in every spawn",
       )

   Full class should look like:

       class GuildConfig(models.Model):
           guild_id = models.BigIntegerField(unique=True, help_text="Discord guild ID")
           spawn_channel = models.BigIntegerField(
               blank=True, null=True, help_text="Discord channel ID where balls will spawn"
           )
           spawn_role = models.BigIntegerField(
               blank=True, null=True,
               help_text="Discord role ID that gets mentioned in every spawn",
           )
           enabled = models.BooleanField(
               help_text="Whether the bot will spawn countryballs in this guild"
           )
           silent = models.BooleanField()
           ...


2. admin_panel/bd_models/admin/guild.py
   In GuildAdmin, change:

       list_display = ("guild_id", "spawn_channel", "enabled", "silent", "blacklisted")

   to:

       list_display = ("guild_id", "spawn_channel", "spawn_role", "enabled", "silent", "blacklisted")


3. Copy 0099_guildconfig_spawn_role.py into admin_panel/bd_models/migrations/
   Rename it to match the next sequential number in that folder
   (e.g. if the last migration is 0007_xxx.py, rename this to 0008_guildconfig_spawn_role.py)
   Open the file and set the "dependencies" tuple to point at that 0007_xxx migration name.

4. Run:
   docker compose exec admin-panel python manage.py migrate bd_models

This is the ONLY package that needs to touch bd_models directly, since spawn_role
belongs conceptually on GuildConfig itself (same table BallsDex already uses for
spawn_channel, enabled, silent). It is not duplicated into a separate app/table.
