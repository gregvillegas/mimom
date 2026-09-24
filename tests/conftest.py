import os
from pathlib import Path

import django
from django.conf import settings

BASE_DIR = Path(__file__).resolve().parent.parent

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")


def pytest_configure():
    if not settings.configured:
        django.setup()
