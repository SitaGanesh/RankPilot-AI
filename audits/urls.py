from django.urls import re_path

from .views import (
    AgentListView,
    AgentRunView,
    AuditCrawlURLView,
    AuditCollectionView,
    AuditReportView,
    AuditStatusView,
    BusinessReportView,
    AuditBatchCancelView,
    AuditBatchCollectionView,
    AuditBatchDetailView,
    AuditBatchResumeView,
    AuditBatchRetryView,
    AuditBatchReportView,
    AuditBatchExportView,
    AuditBatchTargetReportView,
    ProviderStatusView,
    AuditResourceGraphView,
)


urlpatterns = [
    re_path(r"^audits/?$", AuditCollectionView.as_view(), name="audit-create"),
    re_path(r"^batches/?$", AuditBatchCollectionView.as_view(), name="batch-create"),
    re_path(r"^batches/(?P<batch_id>[^/]+)/?$", AuditBatchDetailView.as_view(), name="batch-detail"),
    re_path(r"^batches/(?P<batch_id>[^/]+)/report/?$", AuditBatchReportView.as_view(), name="batch-report"),
    re_path(r"^batches/(?P<batch_id>[^/]+)/export/?$", AuditBatchExportView.as_view(), name="batch-export"),
    re_path(r"^batches/(?P<batch_id>[^/]+)/targets/(?P<target_id>\d+)/report/?$", AuditBatchTargetReportView.as_view(), name="batch-target-report"),
    re_path(r"^batches/(?P<batch_id>[^/]+)/resume/?$", AuditBatchResumeView.as_view(), name="batch-resume"),
    re_path(r"^batches/(?P<batch_id>[^/]+)/retry/?$", AuditBatchRetryView.as_view(), name="batch-retry"),
    re_path(r"^batches/(?P<batch_id>[^/]+)/cancel/?$", AuditBatchCancelView.as_view(), name="batch-cancel"),
    re_path(r"^audits/(?P<audit_id>[^/]+)/?$", AuditStatusView.as_view(), name="audit-status"),
    re_path(r"^audits/(?P<audit_id>[^/]+)/urls/?$", AuditCrawlURLView.as_view(), name="audit-urls"),
    re_path(r"^audits/(?P<audit_id>[^/]+)/graph/?$", AuditResourceGraphView.as_view(), name="audit-graph"),
    re_path(r"^agents/?$", AgentListView.as_view(), name="agent-list"),
    re_path(r"^providers/status/?$", ProviderStatusView.as_view(), name="provider-status"),
    re_path(r"^audits/(?P<audit_id>[^/]+)/agents/(?P<agent_id>[^/]+)/run/?$", AgentRunView.as_view(), name="agent-run"),
    re_path(r"^audits/(?P<audit_id>[^/]+)/report/?$", AuditReportView.as_view(), name="audit-report"),
    re_path(r"^audits/(?P<audit_id>[^/]+)/business-report/?$", BusinessReportView.as_view(), name="business-report"),
    re_path(r"^audits/(?P<audit_id>[^/]+)/evaluation/?$", BusinessReportView.as_view(), name="evaluation-report"),
]
