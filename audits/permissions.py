"""Authentication, ownership and rate-limit helpers for audit endpoints."""

from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.throttling import ScopedRateThrottle


class AuditAccessPermission(BasePermission):
    """Require authentication only when the deployment opts in.

    ``SEO_REQUIRE_AUTH`` defaults to ``False`` so local development and the
    existing test suite keep working without accounts.  Any shared or
    production deployment must set it to ``True``; audit records are then
    scoped to their owner.
    """

    message = "Authentication is required to create or read audits."

    def has_permission(self, request, view) -> bool:
        if getattr(settings, "SEO_REQUIRE_AUTH", False):
            return bool(request.user and request.user.is_authenticated)
        return True


class AuditCreateThrottle(ScopedRateThrottle):
    scope = "audit_create"


class BatchCreateThrottle(ScopedRateThrottle):
    scope = "batch_create"


class InvestigationCreateThrottle(ScopedRateThrottle):
    scope = "investigation_create"


class ReadThrottle(ScopedRateThrottle):
    scope = "read"


def audits_for(request):
    """Return the audit queryset visible to this request.

    When authentication is required, only the owner's audits are visible.  In
    open local development, anonymous records and the caller's own records are
    visible, but another user's audits are still hidden.
    """

    from django.db.models import Q

    from .models import Audit

    queryset = Audit.objects.all()
    if getattr(settings, "SEO_REQUIRE_AUTH", False):
        if not request.user or not request.user.is_authenticated:
            return queryset.none()
        return queryset.filter(owner=request.user)
    if request.user and request.user.is_authenticated:
        return queryset.filter(Q(owner=request.user) | Q(owner__isnull=True))
    return queryset.filter(owner__isnull=True)


def owner_for(request):
    if request.user and request.user.is_authenticated:
        return request.user
    return None
