from django.apps import AppConfig


class LeaveConfig(AppConfig):
    name = "leave"
    verbose_name = "Leave Server"
    default_auto_field = "django.db.models.BigAutoField"
    dpy_package = "leave.leave"

