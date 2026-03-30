"""Security helpers for admin access tracking and protection."""

from django.conf import settings


def get_admin_path_prefix():
    """Return the normalized admin path prefix, e.g. ``/admin``."""
    admin_path = (getattr(settings, "ADMIN_URL_PATH", "admin/") or "admin/").strip().strip("/")
    return f"/{admin_path}"


def is_admin_request_path(path):
    """Return True when the request path targets the Django admin."""
    admin_prefix = get_admin_path_prefix()
    return path == admin_prefix or path.startswith(f"{admin_prefix}/")


def get_forwarded_for(request):
    """Return the raw X-Forwarded-For header when present."""
    return request.META.get("HTTP_X_FORWARDED_FOR", "")


def get_client_ip(request):
    """Return the best client IP available from forwarded headers or REMOTE_ADDR."""
    forwarded_for = get_forwarded_for(request)
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def record_admin_access_event(
    *,
    event_type,
    request,
    user=None,
    username="",
    email="",
    was_successful=False,
    detail="",
):
    """Persist an admin access event without forcing callers to import the model."""
    from .models import AdminAccessLog

    resolved_username = username or (user.get_username() if user else "")
    resolved_email = email or (getattr(user, "email", "") if user else "")
    request_path = getattr(request, "path", "")[:255] if request else ""
    user_agent = ""
    if request:
        user_agent = (request.META.get("HTTP_USER_AGENT", "") or "")[:255]

    AdminAccessLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        username=resolved_username[:150],
        email=resolved_email[:254],
        ip_address=get_client_ip(request)[:64] if request else "",
        forwarded_for=get_forwarded_for(request)[:255] if request else "",
        user_agent=user_agent,
        path=request_path,
        event_type=event_type,
        was_successful=was_successful,
        detail=(detail or "")[:255],
    )


def record_site_access_event(
    *,
    event_type,
    request,
    user=None,
    username="",
    email="",
    was_successful=False,
    detail="",
):
    """Persist a site-wide auth event without forcing callers to import the model."""
    from .models import SiteAccessLog

    resolved_username = username or (user.get_username() if user else "")
    resolved_email = email or (getattr(user, "email", "") if user else "")
    request_path = getattr(request, "path", "")[:255] if request else ""
    user_agent = ""
    if request:
        user_agent = (request.META.get("HTTP_USER_AGENT", "") or "")[:255]

    SiteAccessLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        username=resolved_username[:150],
        email=resolved_email[:254],
        ip_address=get_client_ip(request)[:64] if request else "",
        forwarded_for=get_forwarded_for(request)[:255] if request else "",
        user_agent=user_agent,
        path=request_path,
        event_type=event_type,
        was_successful=was_successful,
        detail=(detail or "")[:255],
    )
