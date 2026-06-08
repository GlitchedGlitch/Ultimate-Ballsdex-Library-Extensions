from django.apps import AppConfig


class RarityConfig(AppConfig):
    name = "rarity"
    verbose_name = "Rarity"
    default_auto_field = "django.db.models.BigAutoField"
    dpy_package = "rarity.rarity"
