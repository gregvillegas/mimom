from django.apps import AppConfig


class ActionItemsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.action_items"
    verbose_name = "Action Items"

    def ready(self):
        from apps.action_items import signals  # noqa: F401
