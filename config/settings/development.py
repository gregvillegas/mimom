from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
INTERNAL_IPS = ["127.0.0.1", "::1"]

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

INSTALLED_APPS += []  # noqa: F405

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
