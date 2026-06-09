from bd_models.models import Ball


class CollectorBall(Ball):
    """
    Proxy model for Ball used only to power the Collector admin section
    """

    class Meta:
        proxy = True
        verbose_name = "Collector Requirement"
        verbose_name_plural = "Collector Requirements"
        app_label = "collector_admin"
