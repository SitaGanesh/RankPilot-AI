from django.urls import path

from .views import (
    AgentListView,
    AgentRunView,
    AuditCrawlURLView,
    AuditCollectionView,
    AuditReportView,
    AuditStatusView,
)


urlpatterns = [
	path("audits/", AuditCollectionView.as_view(), name="audit-create"),
	path("audits/<str:audit_id>/", AuditStatusView.as_view(), name="audit-status"),
	path("audits/<str:audit_id>/urls/", AuditCrawlURLView.as_view(), name="audit-urls"),
	path("agents/", AgentListView.as_view(), name="agent-list"),
	path("audits/<str:audit_id>/agents/<str:agent_id>/run/", AgentRunView.as_view(), name="agent-run"),
	path("audits/<str:audit_id>/report/", AuditReportView.as_view(), name="audit-report"),
]
