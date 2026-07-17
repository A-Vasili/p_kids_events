# This file registers the application with Django and names the configuration Django should load
# at startup.
# Startup hooks are kept here so automatic setup happens once, without being mixed into customer
# or staff page code.

from django.apps import AppConfig


# This configuration tells Django how to load the party builder config application and any startup
# hooks it needs.
class PartyBuilderConfig(AppConfig):
    """Application configuration for the custom party builder."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "party_builder"
    verbose_name = "Party Builder"
