from django.urls import path

from .views import detail, home

urlpatterns = [
    path("", home, name="home"),
    path("audits/<uuid:audit_id>/", detail, name="audit-detail"),
]
