from django.contrib import admin
from django.contrib.admin import AdminSite


class ReorderedAdminSite(AdminSite):
    """Custom admin site that reorders apps to place collector between bd_models and social_django"""

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
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

admin.site = ReorderedAdminSite()
admin.sites.site = admin.site
