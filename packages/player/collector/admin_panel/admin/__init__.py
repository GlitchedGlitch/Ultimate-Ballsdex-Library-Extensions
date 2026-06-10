from django.contrib import admin


_original_get_app_list = admin.site.get_app_list


def _reordered_get_app_list(request, app_label=None):
    """Monkey-patch that places collector_admin between bd_models and everything else."""
    app_list = _original_get_app_list(request, app_label)
    if app_label is not None:
        return app_list

    bd_models = None
    collector_admin = None
    others = []

    for app in app_list:
        if app["app_label"] == "bd_models":
            bd_models = app
        elif app["app_label"] == "collector_admin":
            collector_admin = app
        else:
            others.append(app)

    ordered = []
    if bd_models:
        ordered.append(bd_models)
    if collector_admin:
        ordered.append(collector_admin)
    ordered.extend(others)

    return ordered

admin.site.get_app_list = _reordered_get_app_list
