from django.apps import AppConfig


class BroadcastConfig(AppConfig):
    name = "broadcast"
    verbose_name = "Broadcast"
    default_auto_field = "django.db.models.BigAutoField"
    dpy_package = "broadcast.broadcast"
 
