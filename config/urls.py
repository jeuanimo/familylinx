"""
FamilyLinx URL Configuration

Root URL routing for the FamilyLinx application. Routes are organized by function:

URL Structure:
    /                   - Home dashboard (redirects based on auth state)
    /admin/             - Django admin interface
    /api/               - REST API endpoints (see families/api/urls.py)
    /api/auth/token/    - JWT token authentication for API clients
    /families/          - Family space management (see families/urls.py)
    /u/                 - User profiles and messaging (see accounts/urls.py)
    /accounts/          - Authentication (django-allauth: login, signup, etc.)

API Authentication:
    - Browser sessions: Django session auth (CSRF required)
    - Mobile/API clients: JWT tokens via /api/auth/token/
    - Token refresh: /api/auth/token/refresh/

Static/Media Files:
    Development: Served by Django via MEDIA_URL
    Production: Should be served by nginx/CDN

For more information see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
import sys
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.http import HttpResponse

from . import views

urlpatterns = [
    # Home / Dashboard - shows landing page or dashboard based on auth
    path("", views.home, name="home"),
    
    # Django Admin - staff/superuser only
    path("admin/", admin.site.urls),
    
    # REST API - family tree CRUD, relationships, persons
    path("api/", include("families.api.urls")),
    
    # JWT Authentication - for mobile apps and API clients
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    
    # Health check endpoint for load balancers/monitoring
    path("health/", lambda request: HttpResponse("ok")),
    
    # Family Spaces - family tree, posts, events, albums, chat
    path("families/", include("families.urls")),
    
    # User Profiles & Direct Messaging
    path("u/", include("accounts.urls")),
    
    # Authentication via django-allauth (login, signup, password reset, social auth)
    path("accounts/", include("allauth.urls")),
]

# Serve media files (user uploads) in development
# Production should use nginx/CDN
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
