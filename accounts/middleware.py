"""
Accounts App - Middleware

Custom middleware for user activity tracking and request blocking.
"""

import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone


class UserActivityMiddleware:
    """
    Middleware to track user's last activity for online status.
    
    Updates the user's profile last_activity timestamp on each request,
    but throttled to avoid excessive database writes.
    """
    
    # Only update activity once per this many seconds
    UPDATE_INTERVAL_SECONDS = 60
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Only track authenticated users
        if request.user.is_authenticated:
            self._update_user_activity(request)
        
        return response
    
    def _update_user_activity(self, request):
        """
        Update user's last activity timestamp.
        
        Uses session to throttle updates - only writes to DB once per minute.
        """
        now = timezone.now()
        
        # Check if we've recently updated (throttle writes)
        last_update = request.session.get('_last_activity_update')
        if last_update:
            from datetime import datetime
            try:
                last_update_time = datetime.fromisoformat(last_update)
                # Make timezone aware if needed
                if timezone.is_naive(last_update_time):
                    last_update_time = timezone.make_aware(last_update_time)
                
                # Skip if updated recently
                delta = (now - last_update_time).total_seconds()
                if delta < self.UPDATE_INTERVAL_SECONDS:
                    return
            except (ValueError, TypeError):
                pass
        
        # Update the user's profile
        try:
            profile = request.user.profile
            profile.last_activity = now
            profile.save(update_fields=['last_activity'])
            
            # Store update time in session
            request.session['_last_activity_update'] = now.isoformat()
        except Exception:
            # Profile might not exist yet
            pass


class SecurityBlockerMiddleware:
    """
    Block common bot/scanner attack patterns.
    
    Returns 403/429 for requests matching known attack signatures:
    - WordPress/PHP/framework exploit paths
    - Common vulnerability scanners and exploit clients
    - SQLi/XSS/path traversal style query strings
    - Excessive anonymous requests from a single IP
    """

    logger = logging.getLogger("familylinx.security.blocker")

    # Blocked path patterns (case-insensitive)
    BLOCKED_PATHS = [
        '/wp-admin', '/wp-login', '/wp-content', '/wp-includes',
        '/wordpress', '/xmlrpc.php', '/wp-config',
        '.php', '.asp', '.aspx', '.jsp', '.cgi',
        '/admin.php', '/administrator',
        '/phpmyadmin', '/pma', '/myadmin',
        '/.env', '/.git', '/.svn', '/.htaccess',
        '/config.yml', '/config.json', '/database.yml',
        '/shell', '/cmd', '/eval',
        '/etc/passwd', '/proc/self',
        '/vendor/phpunit', '/phpunit/', '/boaform',
        '/actuator', '/jenkins', '/hudson',
        '/cgi-bin', '/server-status', '/console/',
        '/w00tw00t', '/api/jsonws/invoke',
        '/autodiscover/autodiscover.xml',
        '/owa/', '/.aws/', '/_profiler/',
        '../', '..%2f', '%2e%2e',
    ]

    # Blocked user-agent patterns
    BLOCKED_AGENTS = [
        'sqlmap', 'nikto', 'nmap', 'masscan',
        'zgrab', 'gobuster', 'dirbuster', 'wfuzz',
        'hydra', 'burp', 'nessus', 'qualys',
        'acunetix', 'arachni', 'w3af', 'jaeles',
        'nuclei', 'httpx', 'projectdiscovery',
        'metasploit', 'censysinspect', 'expanse',
        'zmeu', 'dirsearch', 'bbot', 'netsparker',
    ]

    QUERY_SIGNATURES = [
        'union select', 'select%20', 'sleep(', 'benchmark(',
        'information_schema', 'load_file(', 'into outfile',
        '<script', '%3cscript', 'onerror=', 'alert(',
        '../', '..%2f', '%2e%2e', '/etc/passwd',
        'cmd=', 'wget ', 'curl ', 'powershell',
        'base64_', 'eval(', '${jndi:', '%24%7bjndi',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "SECURITY_BLOCKER_ENABLED", True):
            return self.get_response(request)

        limited = self._check_rate_limit(request)
        if limited is not None:
            return limited

        path_lower = request.path.lower()
        for blocked in self.BLOCKED_PATHS:
            if blocked in path_lower:
                return self._deny_request(
                    request,
                    reason="blocked_path",
                    detail=blocked,
                )

        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        for blocked in self.BLOCKED_AGENTS:
            if blocked in user_agent:
                return self._deny_request(
                    request,
                    reason="blocked_user_agent",
                    detail=blocked,
                )

        query_string = request.META.get('QUERY_STRING', '').lower()
        suspicious_matches = [pattern for pattern in self.QUERY_SIGNATURES if pattern in query_string]
        if suspicious_matches:
            return self._deny_request(
                request,
                reason="blocked_query_signature",
                detail=", ".join(suspicious_matches[:3]),
            )

        sql_patterns = ['union', 'select', 'drop', 'insert', 'delete', '--', '/*', '*/']
        suspicious_count = sum(1 for pattern in sql_patterns if pattern in query_string)
        if suspicious_count >= 2:
            return self._deny_request(
                request,
                reason="blocked_query_sql_keywords",
                detail=f"count={suspicious_count}",
            )

        return self.get_response(request)

    def _check_rate_limit(self, request):
        if not getattr(settings, "SECURITY_BLOCKER_RATE_LIMIT_ENABLED", True):
            return None
        request_user = getattr(request, "user", None)
        if getattr(request_user, "is_authenticated", False) and not getattr(
            settings,
            "SECURITY_BLOCKER_RATE_LIMIT_AUTHENTICATED",
            False,
        ):
            return None

        window_seconds = max(
            1,
            int(getattr(settings, "SECURITY_BLOCKER_RATE_LIMIT_WINDOW_SECONDS", 60)),
        )
        max_requests = max(
            1,
            int(getattr(settings, "SECURITY_BLOCKER_MAX_REQUESTS_PER_WINDOW", 240)),
        )

        client_ip = self._get_client_ip(request)
        bucket = int(time.time() // window_seconds)
        cache_key = f"security_blocker:ip:{client_ip}:{bucket}"
        request_count = cache.get(cache_key)
        if request_count is None:
            cache.set(cache_key, 1, timeout=window_seconds)
            request_count = 1
        else:
            try:
                request_count = cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=window_seconds)
                request_count = 1

        if request_count > max_requests:
            return self._deny_request(
                request,
                reason="rate_limit",
                detail=f"count={request_count}, window={window_seconds}s, limit={max_requests}",
                status=429,
            )
        return None

    def _deny_request(self, request, reason, detail, status=403):
        self._log_block(request, reason=reason, detail=detail, status=status)
        if status == 429:
            return HttpResponse("Too Many Requests", status=status)
        return HttpResponseForbidden("Forbidden")

    def _log_block(self, request, reason, detail, status):
        query = request.META.get("QUERY_STRING", "")
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:200] or "-"
        self.logger.warning(
            (
                "Blocked request status=%s reason=%s detail=%s ip=%s method=%s "
                "path=%s query=%s user_agent=%s"
            ),
            status,
            reason,
            detail,
            self._get_client_ip(request),
            request.method,
            request.path,
            query[:200] or "-",
            user_agent,
        )

    def _get_client_ip(self, request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")
