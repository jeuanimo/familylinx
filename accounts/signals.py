"""Signal handlers for account security and audit logging."""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .models import AdminAccessLog, SiteAccessLog
from .security import is_admin_request_path, record_admin_access_event, record_site_access_event


@receiver(user_logged_in)
def log_admin_login_success(sender, request, user, **kwargs):
    """Record successful Django admin logins."""
    if request is None or not is_admin_request_path(request.path):
        return
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        return

    record_admin_access_event(
        event_type=AdminAccessLog.EventType.LOGIN_SUCCESS,
        request=request,
        user=user,
        was_successful=True,
        detail="admin_login_success",
    )


@receiver(user_logged_in)
def log_site_login_success(sender, request, user, **kwargs):
    """Record successful logins across the entire site."""
    if request is None:
        return

    record_site_access_event(
        event_type=SiteAccessLog.EventType.LOGIN_SUCCESS,
        request=request,
        user=user,
        was_successful=True,
        detail="site_login_success",
    )


@receiver(user_login_failed)
def log_admin_login_failure(sender, credentials, request, **kwargs):
    """Record failed login attempts that target the Django admin."""
    if request is None or not is_admin_request_path(request.path):
        return

    credentials = credentials or {}
    username = (
        credentials.get("username")
        or credentials.get("login")
        or credentials.get("email")
        or ""
    )

    record_admin_access_event(
        event_type=AdminAccessLog.EventType.LOGIN_FAILED,
        request=request,
        username=username,
        email=credentials.get("email", ""),
        was_successful=False,
        detail="admin_login_failed",
    )


@receiver(user_login_failed)
def log_site_login_failure(sender, credentials, request, **kwargs):
    """Record failed logins across the entire site."""
    if request is None:
        return

    credentials = credentials or {}
    username = (
        credentials.get("username")
        or credentials.get("login")
        or credentials.get("email")
        or ""
    )

    record_site_access_event(
        event_type=SiteAccessLog.EventType.LOGIN_FAILED,
        request=request,
        username=username,
        email=credentials.get("email", ""),
        was_successful=False,
        detail="site_login_failed",
    )
