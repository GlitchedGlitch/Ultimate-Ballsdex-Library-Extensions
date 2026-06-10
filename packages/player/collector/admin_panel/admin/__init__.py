from django.contrib import admin


_original_get_app_list = None


def _patch_admin_app_list():
    """Monkey-patch admin.site.get_app_list to place collector_admin after bd_models"""
    global _original_get_app_list

    if _original_get_app_list is not None:
        return  

    _original_get_app_list = admin.site.get_app_list

    def _reordered_get_app_list(request, app_label=None):
        app_list = _original_get_app_list(request, app_label)
        if app_label is not None:
            return app_list

        bd_models_idx = None
        collector_idx = None

        for i, app in enumerate(app_list):
            if app["app_label"] == "bd_models":
                bd_models_idx = i
            elif app["app_label"] == "collector_admin":
                collector_idx = i

        if collector_idx is not None and bd_models_idx is not None:

            collector_app = app_list.pop(collector_idx)

            if collector_idx < bd_models_idx:
                bd_models_idx -= 1

            app_list.insert(bd_models_idx + 1, collector_app)

        return app_list

    admin.site.get_app_list = _reordered_get_app_list

from django.apps import apps

if apps.ready:
    _patch_admin_app_list()
else:

    from django.core.signals import setting_changed
    from django.dispatch import receiver

    @receiver(setting_changed)
    def _on_setting_changed(sender, **kwargs):
        if apps.ready and _original_get_app_list is None:
            _patch_admin_app_list()
