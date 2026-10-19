from django.contrib import admin

from .models import AgentRun, Audit, AuditReport, EvidenceSnapshot, StageEvent

admin.site.register(Audit)
admin.site.register(StageEvent)
admin.site.register(EvidenceSnapshot)
admin.site.register(AgentRun)
admin.site.register(AuditReport)
