# This file gathers the project-wide settings that control how Popadoo starts and behaves.
# It connects the installed applications, templates, database, security rules, static files, and
# environment-specific values.
# Sensitive deployment choices remain outside page code so every feature uses one consistent
# source of configuration.

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Read a conventional true/false environment value.
def env_flag(name: str, default: bool = False) -> bool:
    """Read a conventional true/false environment value."""

    return os.environ.get(name, str(default)).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# Development defaults keep local setup simple. Production deployments must
# provide a strong secret key and explicit host names through environment values.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-development-only-change-before-deployment",
)

DEBUG = env_flag("DJANGO_DEBUG", True)

if not DEBUG and SECRET_KEY.startswith("django-insecure-development-only"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a strong private value in production."
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost",
    ).split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# Render provides its public hostname automatically. Adding it here means the
# deployed site accepts its real HTTPS address without placing a temporary
# service name directly in the source code. Custom domains can still be added
# through the normal environment variables.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

    render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)


# Application definition

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'accounts.apps.AccountsConfig',
    'party_builder.apps.PartyBuilderConfig',
    'operations.apps.OperationsConfig',
    'communications.apps.CommunicationsConfig',
]

# Middleware runs around each request to provide security, sessions, authentication, and other shared behaviour.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise lets the production web process serve the collected CSS, JavaScript,
    # and bundled images without requiring a separate static-file server.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'core.middleware.PopadooSecurityHeadersMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.permissions.role_context",
                "communications.context_processors.chat_navigation_context",
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# Local work keeps using SQLite so the project remains easy to open on a
# personal computer. Render supplies DATABASE_URL, which switches the same
# application to PostgreSQL without changing any booking or catalogue logic.
database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Europe/Athens'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
# Deployment collects all static files into this folder. WhiteNoise creates
# compressed production copies without rewriting vendor source-map references,
# while local development keeps Django's familiar direct file behavior.
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedStaticFilesStorage"
        ),
    },
}

MEDIA_URL = "/media/"
# A deployment can point uploads at a persistent disk without changing where
# local copies are stored. The separate flag keeps production media serving an
# explicit choice rather than accidentally exposing a folder.
MEDIA_ROOT = Path(
    os.environ.get("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media"))
)

# This setting decides whether Django may serve owner-uploaded images.
# It stays enabled during local development and can be explicitly controlled
# by the hosting environment after deployment.
SERVE_MEDIA_FILES = env_flag("DJANGO_SERVE_MEDIA", DEBUG)

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cookie and browser security defaults. Secure cookies are enabled automatically
# when DEBUG is disabled for a deployed HTTPS environment.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Authentication routes used by Django's LoginRequiredMixin and safe redirects.
LOGIN_URL = "accounts:accounts_sign_in"
LOGIN_REDIRECT_URL = "accounts:accounts_customer_dashboard"
LOGOUT_REDIRECT_URL = "core:core_home"


# Browser and transport hardening.
# These values are safe for local development; production-only HTTPS features
# are enabled automatically when DEBUG is false or through environment flags.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_SSL_REDIRECT = env_flag("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = int(
    os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_flag(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    False,
)
SECURE_HSTS_PRELOAD = env_flag("DJANGO_SECURE_HSTS_PRELOAD", False)

# Trust this header only when the application is behind a known HTTPS proxy.
# Enabling it on a directly exposed server would let clients spoof the scheme.
if env_flag("DJANGO_TRUST_PROXY_SSL_HEADER", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Conservative request limits reduce abuse without affecting normal booking forms.
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 500

# Public pages use only local scripts and styles. Data images are allowed
# because the bundled Bootstrap stylesheet contains small embedded SVG icons.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
