"""
Accounts App - Middleware

Custom middleware for user activity tracking and online status.
"""

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
    
    Returns 403 for requests matching known attack signatures:
    - WordPress admin paths
    - PHP file requests
    - Common vulnerability scanners
    - SQL injection attempts in URLs
    """
    
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
    ]
    
    # Blocked user-agent patterns
    BLOCKED_AGENTS = [
        'sqlmap', 'nikto', 'nmap', 'masscan',
        'zgrab', 'gobuster', 'dirbuster', 'wfuzz',
        'hydra', 'burp', 'nessus', 'qualys',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check path
        path_lower = request.path.lower()
        for blocked in self.BLOCKED_PATHS:
            if blocked in path_lower:
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("Forbidden")
        
        # Check user agent
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        for blocked in self.BLOCKED_AGENTS:
            if blocked in user_agent:
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("Forbidden")
        
        # Check for SQL injection patterns in query string
        query_string = request.META.get('QUERY_STRING', '').lower()
        sql_patterns = ['union', 'select', 'drop', 'insert', '--', '/*', '*/']
        suspicious_count = sum(1 for p in sql_patterns if p in query_string)
        if suspicious_count >= 2:  # Multiple SQL keywords = likely attack
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Forbidden")
        
        return self.get_response(request)
