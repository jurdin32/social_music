from django.apps import AppConfig


class UsuarioConfig(AppConfig):
    name = 'Usuario'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        import Usuario.signals  # noqa: F401
