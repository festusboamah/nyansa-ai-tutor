from django.apps import AppConfig


class MasteryConfig(AppConfig):
    name = 'mastery'

    def ready(self):
        from . import receivers  # noqa: F401
