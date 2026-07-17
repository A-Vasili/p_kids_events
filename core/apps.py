# This file registers the application with Django and names the configuration Django should load
# at startup.
# Startup hooks are kept here so automatic setup happens once, without being mixed into customer
# or staff page code.

from django.apps import AppConfig


# This configuration tells Django how to load the core config application and any startup hooks it
# needs.
class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
