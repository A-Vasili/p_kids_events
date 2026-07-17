# This file registers the application with Django and names the configuration Django should load
# at startup.
# Startup hooks are kept here so automatic setup happens once, without being mixed into customer
# or staff page code.

from django.apps import AppConfig


# This configuration tells Django how to load the accounts config application and any startup
# hooks it needs.
class AccountsConfig(AppConfig):
    """Configure profile signals and role-group bootstrapping."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    # Django calls this once when the application starts so its automatic setup hooks are
    # registered before requests are handled.
    def ready(self) -> None:
        # Importing signals here ensures they are registered once Django is ready.
        from . import signals  # noqa: F401
