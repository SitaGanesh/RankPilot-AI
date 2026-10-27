"""Celery application for durable SEO audit execution."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "seo_main.settings")

app = Celery("seo_main")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
