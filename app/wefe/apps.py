from django.apps import AppConfig


class WefeConfig(AppConfig):
    name = "wefe"

    def ready(self):
        # Load dash apps
        from .dash import dash_app
