from django.apps import AppConfig


class SalesUpdatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sales_updates"
    verbose_name = "Sales Updates"

    def ready(self):
        from apps.sales_updates import signals  # noqa: F401
