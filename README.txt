================================================================================
FAMILYLINX PROJECT - SECURITY & DEVELOPMENT GUIDELINES
================================================================================

PROJECT OVERVIEW:
-----------------
Django-based web application following OWASP Top 10 security standards and
secure coding practices for AI-assisted development.

SECURITY REQUIREMENTS (OWASP Top 10):
--------------------------------------

1. BROKEN ACCESS CONTROL
   - Implement proper authentication and authorization
   - Use Django's built-in permission system
   - Apply @login_required and permission_required decorators
   - Validate user permissions on every request
   - Principle of least privilege

2. CRYPTOGRAPHIC FAILURES
   - NEVER store sensitive data in plain text
   - Use Django's built-in password hashing (PBKDF2)
   - Encrypt sensitive data at rest and in transit
   - Use HTTPS in production (set SECURE_SSL_REDIRECT = True)
   - Secure session cookies (SESSION_COOKIE_SECURE = True)
   - Set CSRF_COOKIE_SECURE = True in production

3. INJECTION ATTACKS
   - ALWAYS use Django ORM (parameterized queries)
   - NEVER concatenate user input into raw SQL
   - Use .values() or .only() to limit query exposure
   - Validate and sanitize ALL user inputs
   - Use Django forms with proper validation

4. INSECURE DESIGN
   - Apply security by design principles
   - Implement rate limiting for API endpoints
   - Use Django's middleware for security headers
   - Plan for security from the start, not as an afterthought

5. SECURITY MISCONFIGURATION
   - Set DEBUG = False in production
   - Keep SECRET_KEY secure (use environment variables)
   - Set ALLOWED_HOSTS appropriately
   - Remove unnecessary apps from INSTALLED_APPS
   - Configure security middleware properly:
     * SecurityMiddleware
     * CsrfViewMiddleware
     * XFrameOptionsMiddleware
   - Regular dependency updates

6. VULNERABLE AND OUTDATED COMPONENTS
   - Keep Django and all packages updated
   - Run: pip list --outdated regularly
   - Review security advisories
   - Use requirements.txt for dependency tracking

7. IDENTIFICATION AND AUTHENTICATION FAILURES
   - Use Django's authentication system
   - Implement strong password requirements
   - Add password complexity validation
   - Implement account lockout after failed attempts
   - Use multi-factor authentication where appropriate
   - Secure password reset mechanisms

8. SOFTWARE AND DATA INTEGRITY FAILURES
   - Verify all dependencies (check package signatures)
   - Use pip freeze > requirements.txt
   - Implement proper logging
   - Validate deserialized data
   - Use Django's signed cookies when needed

9. SECURITY LOGGING AND MONITORING FAILURES
   - Log all authentication attempts
   - Log access control failures
   - Monitor for suspicious activities
   - NEVER log sensitive data (passwords, tokens, etc.)
   - Configure Django logging properly
   - Regular log reviews

10. SERVER-SIDE REQUEST FORGERY (SSRF)
    - Validate and sanitize all URLs
    - Use allowlists for external requests
    - Implement network segmentation
    - Validate redirect URLs

DJANGO-SPECIFIC SECURITY SETTINGS:
-----------------------------------

Development Settings (settings.py):
- DEBUG = True (dev only)
- SECRET_KEY = 'secure-random-key'
- ALLOWED_HOSTS = []

Production Settings Required:
- DEBUG = False
- SECRET_KEY from environment variable
- ALLOWED_HOSTS = ['yourdomain.com']
- SECURE_SSL_REDIRECT = True
- SESSION_COOKIE_SECURE = True
- CSRF_COOKIE_SECURE = True
- SECURE_BROWSER_XSS_FILTER = True
- SECURE_CONTENT_TYPE_NOSNIFF = True
- X_FRAME_OPTIONS = 'DENY'
- SECURE_HSTS_SECONDS = 31536000
- SECURE_HSTS_INCLUDE_SUBDOMAINS = True
- SECURE_HSTS_PRELOAD = True

SECURE CODING PRACTICES:
------------------------

1. Input Validation:
   - Validate ALL user inputs
   - Use Django forms and serializers
   - Implement server-side validation (never trust client-side)
   - Whitelist acceptable inputs

2. Output Encoding:
   - Django templates auto-escape by default
   - Use |safe filter ONLY when absolutely necessary
   - Be cautious with mark_safe()

3. Error Handling:
   - Use custom error pages (404, 500)
   - NEVER expose stack traces in production
   - Log errors securely
   - Provide user-friendly error messages

4. File Uploads:
   - Validate file types and sizes
   - Use FileField with validators
   - Store uploads outside web root when possible
   - Scan uploads for malware if applicable

5. API Security:
   - Use Django REST Framework properly
   - Implement authentication (Token, JWT)
   - Apply rate limiting
   - Use proper CORS configuration
   - Validate all request data

MOBILE / API NOTES (Quick Reference)
------------------------------------
- JWT endpoints: `/api/auth/token/`, `/api/auth/token/refresh/` (Bearer tokens for mobile clients).
- CORS: configured in `config/settings.py` via `django-cors-headers`; update `CORS_ALLOWED_ORIGINS` for your domains.
- Tree API (mobile-friendly): `/api/families/<id>/tree/?person_id=me&depth_up=3&depth_down=3&include_spouses=1`.
- Line export: `/api/families/<id>/export/line/` with `line`, `mode`, `include_spouses`, `parent_hint_id`, `depth_up`, `depth_down`.
- Clone branch into new space: `POST /api/families/<id>/export/line/create-space/` (caller becomes OWNER of the new space).
- Media URLs returned are absolute to ease mobile use.

See `docs/mobile_api.md` and `docs/line_export.md` for more detail.

REACT FRONTEND SECURITY (if applicable):
----------------------------------------
- Sanitize user inputs before rendering
- Use Content Security Policy (CSP)
- Avoid dangerouslySetInnerHTML
- Validate data received from API
- Store tokens securely (httpOnly cookies preferred)
- Implement XSS protection

AI DEVELOPMENT GUIDELINES:
--------------------------
- Always request security context at session start
- Follow documented security patterns
- Never bypass security controls for convenience
- Ask for clarification when security implications are unclear
- Implement defense in depth
- Code review all AI-generated code

DEVELOPMENT WORKFLOW:
--------------------
1. Activate virtual environment: source venv/bin/activate
2. Install dependencies: pip install -r requirements.txt
3. Run migrations: python manage.py migrate
4. Create superuser: python manage.py createsuperuser
5. Run server: python manage.py runserver
6. Run tests: python manage.py test
7. Check security: python manage.py check --deploy

PRE-DEPLOYMENT CHECKLIST:
-------------------------
[ ] DEBUG = False
[ ] SECRET_KEY from environment
[ ] ALLOWED_HOSTS configured
[ ] All security middleware enabled
[ ] SSL/TLS certificates configured
[ ] Database credentials secured
[ ] Static files collected
[ ] Migrations applied
[ ] Security headers configured
[ ] CORS properly configured
[ ] Rate limiting implemented
[ ] Logging configured
[ ] Error pages customized
[ ] Dependencies updated
[ ] Security audit completed

REFERENCES:
-----------
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- Django Security: https://docs.djangoproject.com/en/stable/topics/security/
- Security Documents: See /docs folder for detailed guides

================================================================================
IMPORTANT: Review this document at the start of each development session
================================================================================
