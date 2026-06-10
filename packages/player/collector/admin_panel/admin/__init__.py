from django.contrib import admin

_original_get_app_list = admin.site.get_app_list


def _reordered_get_app_list(request, app_label=None):
    """
    Wrap the original get_app_list to move collector_admin after bd_models
    """
    app_list = _original_get_app_list(request, app_label)

    if app_label is not None:
        return app_list

    bd_models_idx = None
    collector_idx = None

    for i, app in enumerate(app_list):
        if app.get("app_label") == "bd_models":
            bd_models_idx = i
        elif app.get("app_label") == "collector_admin":
            collector_idx = i

    if collector_idx is not None and bd_models_idx is not None:

        collector_app = app_list.pop(collector_idx)

        if collector_idx < bd_models_idx:
            bd_models_idx -= 1

        app_list.insert(bd_models_idx + 1, collector_app)

    return app_list

admin.site.get_app_list = _reordered_get_app_list

# Import admin classes to register them
from .collector import CollectorClaimAdmin, CollectorRequirementAdmin
