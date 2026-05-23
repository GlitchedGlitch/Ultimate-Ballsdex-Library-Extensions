from django.apps import AppConfig


class CollectorAppConfig(AppConfig):
    name = "collector_app"

    dpy_package = "collector_app.collector_ext"
