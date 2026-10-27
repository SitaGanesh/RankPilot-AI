from django.urls import path
from . import views

urlpatterns = [
    path("runs/", views.start_run, name="marketing_start_run"),
    path("runs/<int:run_id>/", views.get_run, name="marketing_get_run"),
    path("audit/<str:audit_id>/", views.get_run_for_audit, name="marketing_get_run_for_audit"),
]
